"""Dispatch BenchmarkSpec-backed custom evals through existing MLflow paths."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.evaluation.schema import MetricFamily
from src.evaluation.spec_translation import RuntimeAdapterSpec, translate_benchmark_spec
from src.evaluation.tags import (
    ACTUAL_COST_TAG,
    DATASET_HASH_TAG,
    DATASET_ID_TAG,
    DATASET_NUM_SAMPLES_TAG,
    EVAL_SPEC_ID_TAG,
    FAILURE_REASON_TAG,
    MEASUREMENT_POLICY_TAG,
    MLFLOW_NAME_TAG,
    PRIMARY_METRIC_TAG,
    PROJECTED_COST_TAG,
    SCORER_REF_TAG,
    STATUS_TAG,
)
from src.utils.metric_naming import derive_mlflow_name

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REMOTE_PREFIXES = ("s3://", "gs://", "az://", "kaggle://", "http://", "https://")


class CustomEvalError(Exception):
    """Base exception for custom eval validation failures (pre-flight or spec issues)."""


class CustomEvalRuntimeError(CustomEvalError):
    """Raised when the MLflow evaluate call itself fails at runtime."""


class CostGateExceeded(CustomEvalError):  # noqa: N818
    """Raised when projected cost exceeds the configured cap."""


class ScorerLoadError(CustomEvalError):
    """Raised when a scorer ref cannot be resolved from the registry."""


class DatasetHashUnresolvableError(CustomEvalError):
    """Raised when no sha256 hash can be determined for the dataset."""


@dataclass(frozen=True)
class CostProjection:
    """Result of pre-flight cost projection."""

    projected_usd: float
    cap_usd: float | None
    num_rows: int
    num_genai_scorers: int
    per_call_estimate_usd: float


def is_genai_spec(spec: RuntimeAdapterSpec) -> bool:
    """Return True if any scorer ref implies LLM-judge cost."""
    from src.evaluation.scorers.registry import UnknownScorerError, resolve_scorer

    refs = _all_scorer_refs(spec)
    for ref in refs:
        if ref.startswith("genai:") or ref.startswith("judge:"):
            return True
        try:
            registered = resolve_scorer(ref)
            if registered.metadata.metric_family == MetricFamily.QUALITY:
                return True
        except (UnknownScorerError, Exception):  # noqa: S110
            pass
    return False


def compute_dataset_hash(
    spec_dataset_version: str | None,
    dataset_path: str | None,
) -> str:
    """Return a ``sha256:<hex>`` dataset hash.

    Priority: (1) spec_dataset_version if already in sha256 form;
    (2) SHA-256 of canonical-JSON of dataset rows from local path.
    """
    if spec_dataset_version and _SHA256_RE.match(spec_dataset_version):
        return spec_dataset_version

    if dataset_path:
        p = Path(dataset_path)
        if p.exists() and p.is_file():
            try:
                content = p.read_text(encoding="utf-8")
                rows = json.loads(content)
                if isinstance(rows, list):
                    # Sort rows for determinism across shuffled datasets
                    sorted_rows = sorted(
                        rows,
                        key=lambda r: json.dumps(r, sort_keys=True, separators=(",", ":")),
                    )
                    canonical = json.dumps(sorted_rows, sort_keys=True, separators=(",", ":"))
                else:
                    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"))
                return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            except Exception:  # noqa: S110
                pass

    raise DatasetHashUnresolvableError(
        "Cannot determine dataset hash: dataset_version is not in sha256 form "
        "and no local dataset path is readable."
    )


def project_cost(
    spec: RuntimeAdapterSpec,
    num_rows: int,
    cap_usd: float | None,
) -> CostProjection:
    """Compute O(1) pre-flight cost projection for GenAI scorer runs."""
    from src.evaluation.scorers.registry import UnknownScorerError, resolve_scorer

    policy = spec.measurement_policy or {}
    default_cost = float(os.getenv("HOKUSAI_DEFAULT_JUDGE_COST_USD", "0.01"))
    per_call = float(policy.get("per_call_cost_usd", default_cost))

    refs = _all_scorer_refs(spec)
    num_genai = 0
    for ref in refs:
        if ref.startswith("genai:") or ref.startswith("judge:"):
            num_genai += 1
            continue
        try:
            registered = resolve_scorer(ref)
            if registered.metadata.metric_family == MetricFamily.QUALITY:
                num_genai += 1
        except (UnknownScorerError, Exception):  # noqa: S110
            pass

    projected = num_rows * num_genai * per_call
    return CostProjection(
        projected_usd=projected,
        cap_usd=cap_usd,
        num_rows=num_rows,
        num_genai_scorers=num_genai,
        per_call_estimate_usd=per_call,
    )


def emit_canonical_tags(
    mlflow_module: Any,
    *,
    primary_metric_name: str,
    mlflow_name: str,
    dataset_hash: str,
    scorer_refs: list[str],
    measurement_policy: dict[str, Any] | None,
    benchmark_spec_id: str,
    num_samples: int,
    dataset_id: str,
) -> None:
    """Set the five canonical HEM/DeltaOne tags plus supporting tags on the active run."""
    unique_refs = sorted({r for r in scorer_refs if r})
    scorer_ref_value = ",".join(unique_refs) if unique_refs else "none"
    policy_value = json.dumps(measurement_policy, sort_keys=True) if measurement_policy else "none"

    mlflow_module.set_tag(PRIMARY_METRIC_TAG, primary_metric_name)
    mlflow_module.set_tag(MLFLOW_NAME_TAG, mlflow_name)
    mlflow_module.set_tag(DATASET_HASH_TAG, dataset_hash)
    mlflow_module.set_tag(SCORER_REF_TAG, scorer_ref_value)
    mlflow_module.set_tag(MEASUREMENT_POLICY_TAG, policy_value)
    mlflow_module.set_tag(DATASET_ID_TAG, dataset_id)
    mlflow_module.set_tag(DATASET_NUM_SAMPLES_TAG, str(num_samples))
    mlflow_module.set_tag(EVAL_SPEC_ID_TAG, benchmark_spec_id)


def run_custom_eval(
    *,
    model_id: str,
    benchmark_spec: dict[str, Any],
    benchmark_spec_id: str,
    mlflow_module: Any,
    mlflow_client: Any,
    cli_max_cost: float | None,
    seed: int | None,
    temperature: float | None,
) -> dict[str, Any]:
    """Dispatch a BenchmarkSpec-backed custom eval through MLflow.

    Authentication (MLFLOW_TRACKING_TOKEN / Authorization) is configured on
    the injected mlflow_module before this function is called.

    Pre-MLflow-run aborts (raise before starting a run):
      - spec inactive → CustomEvalError
      - scorer ref unknown → ScorerLoadError
      - dataset hash unresolvable → DatasetHashUnresolvableError

    Post-MLflow-run aborts (tags written before raising):
      - cost gate exceeded → CostGateExceeded
      - mlflow evaluate failure → CustomEvalError("mlflow_evaluate_error: ...")
    """
    # 1. Validate is_active (pre-run abort)
    if not benchmark_spec.get("is_active", True):
        raise CustomEvalError("spec_not_found_or_inactive")

    # 2. Translate spec (pre-run abort)
    runtime_spec = translate_benchmark_spec(benchmark_spec)

    # 3. Validate scorers (pre-run abort)
    all_refs = _all_scorer_refs(runtime_spec)
    _validate_scorers(all_refs)

    # 4. Compute dataset hash (pre-run abort)
    dataset_reference = benchmark_spec.get("dataset_reference", "")
    local_path = dataset_reference if not _is_remote(dataset_reference) else None
    dataset_hash = compute_dataset_hash(
        spec_dataset_version=benchmark_spec.get("dataset_version"),
        dataset_path=local_path,
    )

    # 5. Dataset metadata
    dataset_id = dataset_reference or benchmark_spec.get("dataset_id", "")
    num_samples = _count_rows(local_path) or 0

    # 6. Determine cost cap (spec policy takes priority over CLI flag)
    policy = runtime_spec.measurement_policy or {}
    spec_cap = policy.get("max_cost_usd")
    cap_usd = float(spec_cap) if spec_cap is not None else cli_max_cost

    # 7. Start MLflow run
    with mlflow_module.start_run(
        run_name=f"hokusai_custom_eval:{model_id}:{benchmark_spec_id}"
    ) as run:
        run_id = run.info.run_id

        # 8. Set canonical tags + running status
        primary_metric_name = runtime_spec.primary_metric.name
        mlflow_name_val = derive_mlflow_name(primary_metric_name)
        emit_canonical_tags(
            mlflow_module,
            primary_metric_name=primary_metric_name,
            mlflow_name=mlflow_name_val,
            dataset_hash=dataset_hash,
            scorer_refs=all_refs,
            measurement_policy=runtime_spec.measurement_policy,
            benchmark_spec_id=benchmark_spec_id,
            num_samples=num_samples,
            dataset_id=dataset_id,
        )
        mlflow_module.set_tag(STATUS_TAG, "running")

        # 9. Cost gate (GenAI specs only)
        genai = is_genai_spec(runtime_spec)
        if genai and cap_usd is not None:
            projection = project_cost(runtime_spec, num_samples, cap_usd)
            if projection.projected_usd > cap_usd:
                mlflow_module.set_tag(STATUS_TAG, "failed")
                mlflow_module.set_tag(FAILURE_REASON_TAG, "cost_gate_exceeded")
                mlflow_module.set_tag(PROJECTED_COST_TAG, f"{projection.projected_usd:.6f}")
                raise CostGateExceeded(
                    f"Projected cost ${projection.projected_usd:.4f} exceeds cap "
                    f"${cap_usd:.4f} "
                    f"({projection.num_rows} rows × {projection.num_genai_scorers} GenAI scorers "
                    f"× ${projection.per_call_estimate_usd:.4f}/call)"
                )

        # 10. Dispatch to the appropriate MLflow evaluate path
        try:
            if genai:
                result = _dispatch_genai(
                    mlflow_module=mlflow_module,
                    model_id=model_id,
                    dataset_reference=dataset_reference,
                    runtime_spec=runtime_spec,
                )
            else:
                result = _dispatch_deterministic(
                    mlflow_module=mlflow_module,
                    model_id=model_id,
                    dataset_reference=dataset_reference,
                    runtime_spec=runtime_spec,
                )
        except (CostGateExceeded, CustomEvalError):
            raise
        except Exception as exc:
            mlflow_module.set_tag(STATUS_TAG, "failed")
            mlflow_module.set_tag(FAILURE_REASON_TAG, "mlflow_evaluate_error")
            raise CustomEvalRuntimeError(f"mlflow_evaluate_error: {exc}") from exc

        # 11. Log metrics and mark success
        metrics = _extract_metrics(result)
        for metric_name, metric_value in metrics.items():
            if isinstance(metric_value, (int, float)):
                mlflow_module.log_metric(metric_name, float(metric_value))

        actual_cost = _find_cost_metric(metrics)
        if actual_cost is not None:
            mlflow_module.set_tag(ACTUAL_COST_TAG, f"{actual_cost:.6f}")

        mlflow_module.set_tag(STATUS_TAG, "succeeded")

        return {
            "status": "success",
            "run_id": run_id,
            "metrics": metrics,
            "benchmark_spec_id": benchmark_spec_id,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _all_scorer_refs(spec: RuntimeAdapterSpec) -> list[str]:
    refs: list[str] = []
    if spec.primary_metric.scorer_ref:
        refs.append(spec.primary_metric.scorer_ref)
    for m in spec.secondary_metrics:
        if m.scorer_ref:
            refs.append(m.scorer_ref)
    return refs


def _validate_scorers(refs: list[str]) -> None:
    """Raise ScorerLoadError for any unknown non-prefixed scorer ref."""
    from src.evaluation.scorers.registry import UnknownScorerError, resolve_scorer

    for ref in refs:
        if ref.startswith("genai:") or ref.startswith("judge:"):
            continue
        try:
            resolve_scorer(ref)
        except UnknownScorerError as exc:
            raise ScorerLoadError(f"scorer_load_failed: {exc}") from exc


def _is_remote(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _REMOTE_PREFIXES)


def _count_rows(local_path: str | None) -> int | None:
    if not local_path:
        return None
    p = Path(local_path)
    if not p.exists() or not p.is_file():
        return None
    suffix = p.suffix.lower()
    try:
        if suffix == ".json":
            payload = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return len(payload)
        elif suffix in (".csv", ".tsv"):
            lines = p.read_text(encoding="utf-8").splitlines()
            return max(0, len(lines) - 1)
    except Exception:  # noqa: S110
        pass
    return None


def _dispatch_genai(
    *,
    mlflow_module: Any,
    model_id: str,
    dataset_reference: str,
    runtime_spec: RuntimeAdapterSpec,
) -> Any:
    """Route to mlflow.genai.evaluate for LLM-judge specs."""
    from src.evaluation.scorers.registry import UnknownScorerError, resolve_scorer

    try:
        mlflow_genai = importlib.import_module("mlflow.genai")
    except ImportError as exc:
        raise CustomEvalRuntimeError("mlflow_genai_unavailable") from exc

    scorer_callables: list[Any] = []
    for ref in _all_scorer_refs(runtime_spec):
        if ref.startswith("genai:") or ref.startswith("judge:"):
            continue
        try:
            registered = resolve_scorer(ref)
            scorer_callables.append(registered.callable_)
        except UnknownScorerError:
            pass

    return mlflow_genai.evaluate(
        data=dataset_reference,
        scorers=scorer_callables,
        model_id=model_id,
    )


def _dispatch_deterministic(
    *,
    mlflow_module: Any,
    model_id: str,
    dataset_reference: str,
    runtime_spec: RuntimeAdapterSpec,
) -> Any:
    """Route to mlflow.evaluate for deterministic specs."""
    policy = runtime_spec.measurement_policy or {}
    model_type = (
        runtime_spec.unit_of_analysis or policy.get("mlflow_evaluate_model_type") or "classifier"
    )
    return mlflow_module.evaluate(
        model=f"models:/{model_id}",
        data=dataset_reference,
        model_type=model_type,
    )


def _extract_metrics(result: Any) -> dict[str, Any]:
    if hasattr(result, "metrics") and isinstance(result.metrics, dict):
        return result.metrics
    if isinstance(result, dict) and isinstance(result.get("metrics"), dict):
        return result["metrics"]
    return {}


def _find_cost_metric(metrics: dict[str, Any]) -> float | None:
    for key in ("total_token_cost", "cost_usd"):
        if key in metrics and isinstance(metrics[key], (int, float)):
            return float(metrics[key])
    for key, value in metrics.items():
        if "cost" in key.lower() and isinstance(value, (int, float)):
            return float(value)
    return None
