"""Click CLI entrypoint for reproducible ML evaluations."""

from __future__ import annotations

import importlib
import json
import random
from pathlib import Path
from typing import Any

import click

from src.cli.attestation import create_attestation, log_attestation
from src.cli.output_formatters import format_output
from src.cli.resume import ResumeDecision, resolve_resume_decision

DEFAULT_ESTIMATED_COST_USD = 0.10
DEFAULT_MODEL_TYPE = "classifier"


class EvaluationValidationError(Exception):
    """Raised when pre-flight validation fails."""


class EvaluationRuntimeError(Exception):
    """Raised when runtime evaluation execution fails."""


def _load_mlflow() -> Any:
    """Load MLflow lazily so CLI startup remains fast."""
    # MLflow authentication is expected via environment configuration such as
    # MLFLOW_TRACKING_TOKEN / Authorization passthrough used across this repository.
    try:
        return importlib.import_module("mlflow")
    except ImportError as exc:
        raise EvaluationRuntimeError(
            "mlflow is required for hoku eval. Install ML dependencies before running this command."
        ) from exc


def _load_mlflow_client() -> Any:
    """Load MLflow client lazily."""
    try:
        module = importlib.import_module("mlflow.tracking")
        return module.MlflowClient()
    except ImportError as exc:
        raise EvaluationRuntimeError(
            "mlflow is required for hoku eval. Install ML dependencies before running this command."
        ) from exc


def _set_seed(seed: int | None) -> None:
    """Set deterministic random seeds for supported libraries."""
    if seed is None:
        return

    random.seed(seed)
    try:
        numpy_module = importlib.import_module("numpy")
    except ImportError:
        return
    numpy_module.random.seed(seed)


def _looks_like_path(eval_spec: str) -> bool:
    """Return whether eval spec is likely a local path."""
    return any(token in eval_spec for token in ("/", "\\", ".json", ".csv", ".yaml", ".yml"))


def _estimate_cost_usd(eval_spec: str) -> float:
    """Estimate evaluation cost using lightweight heuristics."""
    path = Path(eval_spec)
    if path.exists() and path.is_file():
        suffix = path.suffix.lower()
        if suffix == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    return round(max(1, len(payload)) * 0.002, 6)
                if isinstance(payload, dict):
                    return round(max(1, len(payload.keys())) * 0.002, 6)
            except json.JSONDecodeError:
                pass

        line_count = max(1, len(path.read_text(encoding="utf-8").splitlines()))
        return round(line_count * 0.002, 6)

    return DEFAULT_ESTIMATED_COST_USD


def _model_exists(client: Any, model_id: str) -> bool:
    """Validate model availability via MLflow model registry."""
    try:
        versions = client.search_model_versions(f"name='{model_id}'")
        if versions:
            return True
    except Exception:
        versions = []

    if versions:
        return True

    try:
        client.get_registered_model(model_id)
        return True
    except Exception:
        return False


def _validate_provider(provider: str | None) -> bool:
    """Validate provider if provider registry has known providers."""
    if provider is None:
        return True

    try:
        from src.services.providers.provider_registry import ProviderRegistry

        registry = ProviderRegistry()
        available = registry.get_available_providers()
        if not available:
            return True
        return provider in available
    except Exception:
        return True


def _validate_eval_spec(eval_spec: str) -> bool:
    """Validate eval spec path/dataset identifier."""
    path = Path(eval_spec)
    if path.exists():
        return True
    if not eval_spec.strip():
        return False
    return not _looks_like_path(eval_spec)


def _preflight_validate(
    *,
    client: Any,
    model_id: str,
    eval_spec: str,
    provider: str | None,
    max_cost: float | None,
) -> dict[str, Any]:
    """Run pre-flight validation and return plan metadata."""
    model_ok = _model_exists(client, model_id)
    eval_spec_ok = _validate_eval_spec(eval_spec)
    provider_ok = _validate_provider(provider)
    estimated_cost = _estimate_cost_usd(eval_spec)

    errors: list[str] = []
    if not model_ok:
        errors.append(f"Model '{model_id}' not found in MLflow registry.")
    if not eval_spec_ok:
        errors.append(f"Evaluation spec '{eval_spec}' is invalid or missing.")
    if not provider_ok:
        errors.append(f"Provider '{provider}' is not registered.")
    if max_cost is not None and estimated_cost > max_cost:
        errors.append(
            f"Estimated cost ${estimated_cost:.6f} exceeds configured max cost ${max_cost:.6f}."
        )

    return {
        "valid": not errors,
        "errors": errors,
        "estimated_cost_usd": estimated_cost,
        "model_exists": model_ok,
        "eval_spec_exists": eval_spec_ok,
        "provider_available": provider_ok,
    }


def _extract_metrics(result: Any) -> dict[str, Any]:
    """Extract metrics from MLflow evaluation result payload."""
    if hasattr(result, "metrics") and isinstance(result.metrics, dict):
        return result.metrics
    if isinstance(result, dict) and isinstance(result.get("metrics"), dict):
        return result["metrics"]
    return {}


def _emit(output_format: str, payload: dict[str, Any]) -> None:
    """Emit formatted CLI output."""
    click.echo(format_output(output_format, payload))


def _build_evaluate_kwargs(
    *,
    model_id: str,
    eval_spec: str,
    provider: str | None,
    seed: int | None,
    temperature: float | None,
) -> dict[str, Any]:
    """Build mlflow.evaluate kwargs with optional evaluator config."""
    evaluator_config: dict[str, Any] = {}
    if provider is not None:
        evaluator_config["provider"] = provider
    if seed is not None:
        evaluator_config["seed"] = seed
    if temperature is not None:
        evaluator_config["temperature"] = temperature

    evaluate_kwargs: dict[str, Any] = {
        "model": f"models:/{model_id}",
        "data": eval_spec,
        "model_type": DEFAULT_MODEL_TYPE,
    }
    if evaluator_config:
        evaluate_kwargs["evaluator_config"] = evaluator_config
    return evaluate_kwargs


def _log_run_inputs(
    *,
    mlflow_module: Any,
    model_id: str,
    eval_spec: str,
    provider: str | None,
    seed: int | None,
    temperature: float | None,
    max_cost: float | None,
) -> None:
    """Log evaluation inputs to MLflow for reproducibility."""
    mlflow_module.set_tag("hoku_eval.model_id", model_id)
    mlflow_module.set_tag("hoku_eval.eval_spec", eval_spec)
    mlflow_module.set_tag("hoku_eval.seed", "none" if seed is None else str(seed))
    mlflow_module.set_tag("hoku_eval.status", "running")

    mlflow_module.log_param("model_id", model_id)
    mlflow_module.log_param("eval_spec", eval_spec)
    if provider is not None:
        mlflow_module.log_param("provider", provider)
    if seed is not None:
        mlflow_module.log_param("seed", seed)
    if temperature is not None:
        mlflow_module.log_param("temperature", temperature)
    if max_cost is not None:
        mlflow_module.log_param("max_cost", max_cost)


def _run_evaluation(  # noqa: C901
    *,
    model_id: str,
    eval_spec: str,
    provider: str | None,
    seed: int | None,
    temperature: float | None,
    max_cost: float | None,
    resume: str | None,
    attest: bool,
) -> dict[str, Any]:
    """Execute evaluation and return structured result payload."""
    mlflow = _load_mlflow()
    client = _load_mlflow_client()

    preflight = _preflight_validate(
        client=client,
        model_id=model_id,
        eval_spec=eval_spec,
        provider=provider,
        max_cost=max_cost,
    )
    if not preflight["valid"]:
        raise EvaluationValidationError("; ".join(preflight["errors"]))

    resume_decision: ResumeDecision = resolve_resume_decision(
        client=client,
        model_id=model_id,
        eval_spec=eval_spec,
        seed=seed,
        resume=resume,
    )
    if resume_decision.mode == "skip":
        return {
            "status": "skipped",
            "run_id": resume_decision.run_id,
            "message": resume_decision.message,
            "cost_usd": preflight["estimated_cost_usd"],
            "metrics": {},
        }

    _set_seed(seed)

    run_ctx = (
        mlflow.start_run(run_id=resume_decision.run_id)
        if resume_decision.mode == "resume" and resume_decision.run_id
        else mlflow.start_run(run_name=f"hoku_eval:{model_id}")
    )

    with run_ctx as run:
        run_id = run.info.run_id
        _log_run_inputs(
            mlflow_module=mlflow,
            model_id=model_id,
            eval_spec=eval_spec,
            provider=provider,
            seed=seed,
            temperature=temperature,
            max_cost=max_cost,
        )

        estimated_cost = preflight["estimated_cost_usd"]
        if max_cost is not None and estimated_cost > max_cost:
            mlflow.set_tag("hoku_eval.status", "aborted")
            raise EvaluationValidationError(
                f"Estimated cost ${estimated_cost:.6f} exceeds configured max cost ${max_cost:.6f}."
            )

        evaluate_kwargs = _build_evaluate_kwargs(
            model_id=model_id,
            eval_spec=eval_spec,
            provider=provider,
            seed=seed,
            temperature=temperature,
        )

        try:
            result = mlflow.evaluate(**evaluate_kwargs)
        except Exception as exc:
            mlflow.set_tag("hoku_eval.status", "failed")
            raise EvaluationRuntimeError(str(exc)) from exc

        metrics = _extract_metrics(result)
        for metric_name, metric_value in metrics.items():
            if isinstance(metric_value, (int, float)):
                mlflow.log_metric(metric_name, float(metric_value))

        actual_cost = float(metrics.get("cost_usd", estimated_cost))
        if max_cost is not None and actual_cost > max_cost:
            mlflow.set_tag("hoku_eval.status", "aborted")
            raise EvaluationRuntimeError(
                f"Runtime cost ${actual_cost:.6f} exceeds configured max cost ${max_cost:.6f}."
            )

        attestation_hash: str | None = None
        if attest:
            attestation_hash, attestation_payload = create_attestation(
                model_id=model_id,
                eval_spec=eval_spec,
                provider=provider,
                seed=seed,
                temperature=temperature,
                results=metrics,
            )
            log_attestation(
                mlflow_module=mlflow,
                run_id=run_id,
                attestation_hash=attestation_hash,
                payload=attestation_payload,
            )

        mlflow.set_tag("hoku_eval.status", "completed")

        return {
            "status": "success",
            "run_id": run_id,
            "message": resume_decision.message,
            "resumed": resume_decision.mode == "resume",
            "provider": provider,
            "seed": seed,
            "temperature": temperature,
            "cost_usd": actual_cost,
            "metrics": metrics,
            "attestation_hash": attestation_hash,
        }


def _handle_dry_run(
    *,
    output: str,
    model_id: str,
    eval_spec: str,
    provider: str | None,
    seed: int | None,
    temperature: float | None,
    max_cost: float | None,
    resume: str | None,
    attest: bool,
) -> int:
    """Run dry-run validation and return process exit code."""
    client = _load_mlflow_client()
    preflight = _preflight_validate(
        client=client,
        model_id=model_id,
        eval_spec=eval_spec,
        provider=provider,
        max_cost=max_cost,
    )

    payload = {
        "status": "valid" if preflight["valid"] else "invalid",
        "dry_run": True,
        "plan": {
            "model_id": model_id,
            "eval_spec": eval_spec,
            "provider": provider,
            "seed": seed,
            "temperature": temperature,
            "max_cost": max_cost,
            "resume": resume,
            "attest": attest,
            "estimated_cost_usd": preflight["estimated_cost_usd"],
        },
        "validation": {
            "model_exists": preflight["model_exists"],
            "eval_spec_exists": preflight["eval_spec_exists"],
            "provider_available": preflight["provider_available"],
            "errors": preflight["errors"],
        },
    }
    _emit(output, payload)
    return 0 if preflight["valid"] else 1


@click.group(name="hoku")
def cli() -> None:
    """Hokusai reproducible evaluation CLI."""


@cli.group(name="eval")
def eval_group() -> None:
    """Manage evaluation commands."""


@eval_group.command(name="run")
@click.argument("model_id")
@click.argument("eval_spec")
@click.option("--provider", type=str, default=None, help="Model provider override.")
@click.option("--seed", type=int, default=None, help="Deterministic random seed.")
@click.option("--temperature", type=float, default=None, help="Model temperature override.")
@click.option(
    "--max-cost",
    type=float,
    default=None,
    help="Maximum allowed evaluation cost in USD.",
)
@click.option("--dry-run", is_flag=True, default=False, help="Validate inputs without executing.")
@click.option(
    "--resume",
    type=str,
    default=None,
    help="Resume run id or 'auto' to discover matching runs.",
)
@click.option("--attest", is_flag=True, default=False, help="Generate and log attestation hash.")
@click.option(
    "--output",
    "output_format",
    type=click.Choice(["json", "ci", "human"]),
    default="human",
    show_default=True,
    help="Output format.",
)
def run_command(
    model_id: str,
    eval_spec: str,
    provider: str | None,
    seed: int | None,
    temperature: float | None,
    max_cost: float | None,
    dry_run: bool,
    resume: str | None,
    attest: bool,
    output_format: str,
) -> None:
    """Run an MLflow-backed evaluation for MODEL_ID against EVAL_SPEC."""
    if max_cost is not None and max_cost <= 0:
        payload = {
            "status": "invalid",
            "message": "--max-cost must be greater than 0.",
        }
        _emit(output_format, payload)
        raise SystemExit(1)

    normalized_resume = resume
    if normalized_resume and normalized_resume.lower() in {"true", "yes"}:
        normalized_resume = "auto"

    try:
        if dry_run:
            code = _handle_dry_run(
                output=output_format,
                model_id=model_id,
                eval_spec=eval_spec,
                provider=provider,
                seed=seed,
                temperature=temperature,
                max_cost=max_cost,
                resume=normalized_resume,
                attest=attest,
            )
            raise SystemExit(code)

        payload = _run_evaluation(
            model_id=model_id,
            eval_spec=eval_spec,
            provider=provider,
            seed=seed,
            temperature=temperature,
            max_cost=max_cost,
            resume=normalized_resume,
            attest=attest,
        )
        _emit(output_format, payload)
        raise SystemExit(0)
    except EvaluationValidationError as exc:
        _emit(
            output_format,
            {
                "status": "invalid",
                "message": str(exc),
            },
        )
        raise SystemExit(1) from exc
    except EvaluationRuntimeError as exc:
        _emit(
            output_format,
            {
                "status": "error",
                "message": str(exc),
            },
        )
        raise SystemExit(2) from exc
    except SystemExit:
        raise
    except Exception as exc:
        _emit(
            output_format,
            {
                "status": "error",
                "message": f"Unexpected error: {exc}",
            },
        )
        raise SystemExit(2) from exc


main = cli


if __name__ == "__main__":
    cli()
