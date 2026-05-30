"""Register, promote, and smoke test the Model 30 Technical Task Router.

MLflow authentication follows the SDK environment, including
``MLFLOW_TRACKING_TOKEN`` when the registry requires bearer auth. Production API
smoke tests pass the API key through an Authorization header.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import mlflow
import mlflow.pyfunc
import requests
from mlflow import MlflowClient

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.model_30.register_technical_task_router import MODEL_NAME, register_model  # noqa: E402

OBJECTIVES: tuple[str, ...] = ("lowest_cost", "fastest_completion", "highest_reliability")
PUBLIC_MODEL_ID_PATTERN = re.compile(r"^(claude-|gpt-|deepseek-)")
FORBIDDEN_MODEL_IDS = ("deep-coder-v2", "fast-coder-v1", "<synthetic>")


def register_promote_and_smoke(args: argparse.Namespace) -> dict[str, Any]:
    """Run the full HOK-1917 registration and promotion flow."""
    if args.tracking_uri:
        mlflow.set_tracking_uri(args.tracking_uri)

    registration = _register_or_resolve_model(args)
    model_uri = registration["registered_model_uri"]
    client = MlflowClient()
    previous_alias = _alias_target(client, MODEL_NAME, args.alias)

    local_smoke = _smoke_mlflow_model(model_uri)
    promotion: dict[str, Any] = {"alias": args.alias, "skipped": args.no_promote}
    if not args.no_promote:
        version = registration.get("registered_model_version")
        if not version:
            raise ValueError("Cannot promote without a registered model version")
        client.set_registered_model_alias(MODEL_NAME, args.alias, version)
        promotion.update(
            {
                "model_name": MODEL_NAME,
                "version": version,
                "model_uri": f"models:/{MODEL_NAME}@{args.alias}",
                "previous_alias_target": previous_alias,
                "rollback_command": _rollback_command(args.alias, previous_alias),
            }
        )

    production_smoke = None
    if args.production_smoke:
        api_key = args.api_key or os.getenv("HOKUSAI_API_KEY") or os.getenv("API_KEY")
        if not api_key:
            raise ValueError("--production-smoke requires --api-key, HOKUSAI_API_KEY, or API_KEY")
        production_smoke = _smoke_production_api(
            args.production_api_url,
            api_key=api_key,
            timeout_seconds=args.production_timeout_seconds,
        )

    return {
        "registration": registration,
        "promotion": promotion,
        "local_smoke": local_smoke,
        "production_smoke": production_smoke,
        "serving_environment": {
            "MODEL_30_MLFLOW_URI": f"models:/{MODEL_NAME}@{args.alias}",
        },
    }


def _register_or_resolve_model(args: argparse.Namespace) -> dict[str, Any]:
    if args.model_uri:
        version = _version_from_model_uri(args.model_uri)
        return {
            "registered_model_name": MODEL_NAME,
            "registered_model_version": version,
            "registered_model_uri": args.model_uri,
            "skipped_registration": True,
        }

    if not args.router_dataset:
        raise ValueError("--router-dataset is required unless --model-uri is provided")

    return register_model(
        SimpleNamespace(
            router_dataset=args.router_dataset,
            holdout_dataset=args.holdout_dataset,
            evaluation_objectives=args.evaluation_objectives,
            tracking_uri=args.tracking_uri,
            experiment_name=args.experiment_name,
            run_name=args.run_name,
            k_neighbors=args.k_neighbors,
            smoke=True,
        )
    )


def _smoke_mlflow_model(model_uri: str) -> list[dict[str, Any]]:
    model = mlflow.pyfunc.load_model(model_uri)
    results = []
    for objective in OBJECTIVES:
        prediction = model.predict(_features_for_objective(objective))
        raw = prediction.iloc[0].to_dict()
        _assert_strategy_payload(raw, source=f"mlflow:{objective}")
        results.append(
            {
                "objective": objective,
                "recommended_strategy": raw["recommended_strategy"],
                "nearest_neighbors": raw.get("nearest_neighbors"),
            }
        )
    return results


def _smoke_production_api(
    production_api_url: str,
    *,
    api_key: str,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    results = []
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    for objective in OBJECTIVES:
        response = requests.post(
            production_api_url,
            headers=headers,
            json={"inputs": _api_inputs_for_objective(objective)},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        predictions = body.get("predictions")
        if not isinstance(predictions, dict):
            raise ValueError(f"Production response missing predictions for {objective}")
        _assert_strategy_payload(predictions, source=f"production:{objective}")
        results.append(
            {
                "objective": objective,
                "status_code": response.status_code,
                "request_id": body.get("metadata", {}).get("request_id"),
                "predictions": predictions,
            }
        )
    return results


def _features_for_objective(objective: str) -> Any:
    import pandas as pd

    return pd.DataFrame(
        [
            {
                "task_type": "feature",
                "language": "python",
                "framework": "fastapi",
                "repo_type": "monorepo",
                "domain": "backend",
                "complexity": "medium",
                "description_length_bucket": "medium",
                "files_touched_bucket": "6_15",
                "available_planner_models": ["claude-sonnet-4-6", "gpt-5.4"],
                "available_coder_models": ["claude-sonnet-4-6", "gpt-5.4"],
                "available_reviewer_models": ["claude-sonnet-4-6", "gpt-5.4"],
                "max_cost_usd": 25.0,
                "prioritize_quality": objective == "highest_reliability",
                "prioritize_speed": objective == "fastest_completion",
                "risk_level": "medium",
                "requires_tests": True,
                "security_sensitive": False,
                "repo_size_bucket": "large",
                "surface": "hokusai-production-smoke",
                "workflow_stages": ["plan", "code", "review"],
                "routing_objective": objective,
                "is_greenfield": False,
                "is_migration": False,
                "cross_service": False,
                "ui_heavy": False,
            }
        ]
    )


def _api_inputs_for_objective(objective: str) -> dict[str, Any]:
    return {
        "task": {
            "description": "Refactor billing webhook retry handling with tests",
            "task_type": "refactor",
            "language": "python",
            "framework": "fastapi",
            "repo_type": "monorepo",
        },
        "routing": {
            "available_models": ["claude-sonnet-4-6", "gpt-5.4"],
            "max_cost_usd": 25,
            "objective": objective,
            "prioritize_quality": objective == "highest_reliability",
            "prioritize_speed": objective == "fastest_completion",
        },
        "workflow": {"surface": "hokusai-production-smoke", "stages": ["plan", "code", "review"]},
        "context": {
            "domain": "backend",
            "repo_size_bucket": "large",
            "requires_tests": True,
            "risk_level": "medium",
            "file_count": 6,
            "estimated_complexity": "medium",
            "security_sensitive": False,
        },
        "metadata": {"run_id": f"hok-1917-{objective}"},
    }


def _assert_strategy_payload(payload: dict[str, Any], *, source: str) -> None:
    for key in ("recommended_strategy", "tradeoffs", "nearest_neighbors"):
        if key not in payload:
            raise ValueError(f"{source} response missing {key}")
    strategy = payload["recommended_strategy"]
    if not isinstance(strategy, dict):
        raise ValueError(f"{source} recommended_strategy is not an object")
    model_ids = _collect_model_ids(payload)
    if not model_ids:
        raise ValueError(f"{source} response did not include any routed model IDs")
    forbidden = sorted(set(model_ids) & set(FORBIDDEN_MODEL_IDS))
    malformed = sorted(
        {model_id for model_id in model_ids if not PUBLIC_MODEL_ID_PATTERN.match(model_id)}
    )
    if forbidden or malformed:
        raise ValueError(
            f"{source} response contained invalid model IDs "
            f"(forbidden={forbidden}, malformed={malformed})"
        )


def _collect_model_ids(value: Any) -> list[str]:
    if isinstance(value, dict):
        collected: list[str] = []
        for key, nested in value.items():
            if key in {"planner_model", "coder_model", "reviewer_model"} and nested:
                collected.append(str(nested))
            else:
                collected.extend(_collect_model_ids(nested))
        return collected
    if isinstance(value, list):
        collected = []
        for item in value:
            collected.extend(_collect_model_ids(item))
        return collected
    return []


def _alias_target(client: MlflowClient, model_name: str, alias: str) -> dict[str, str] | None:
    try:
        version = client.get_model_version_by_alias(model_name, alias)
    except Exception:
        return None
    return {
        "name": version.name,
        "version": version.version,
        "run_id": version.run_id,
    }


def _rollback_command(alias: str, previous_alias: dict[str, str] | None) -> str | None:
    if previous_alias is None:
        return None
    return (
        "python scripts/model_30/promote_technical_task_router.py "
        f"--model-uri 'models:/{MODEL_NAME}/{previous_alias['version']}' "
        f"--alias {alias} --no-production-smoke"
    )


def _version_from_model_uri(model_uri: str) -> str | None:
    if "@" in model_uri:
        return None
    parts = model_uri.rstrip("/").split("/")
    return parts[-1] if parts and parts[-1].isdigit() else None


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--router-dataset")
    parser.add_argument("--holdout-dataset")
    parser.add_argument("--evaluation-objectives", default="all")
    parser.add_argument("--model-uri", help="Existing registered model URI to promote.")
    parser.add_argument("--tracking-uri", default=os.getenv("MLFLOW_TRACKING_URI"))
    parser.add_argument("--experiment-name")
    parser.add_argument("--run-name", default="technical-task-router-v2-production")
    parser.add_argument("--k-neighbors", type=int, default=40)
    parser.add_argument("--alias", default="production")
    parser.add_argument("--no-promote", action="store_true")
    parser.add_argument("--production-smoke", action="store_true")
    parser.add_argument("--no-production-smoke", dest="production_smoke", action="store_false")
    parser.set_defaults(production_smoke=False)
    parser.add_argument(
        "--production-api-url",
        default="https://api.hokus.ai/api/v1/models/30/predict",
    )
    parser.add_argument("--api-key")
    parser.add_argument("--production-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--output-report")
    return parser.parse_args()


def main() -> None:
    """Run the promotion workflow."""
    args = parse_args()
    report = register_promote_and_smoke(args)
    report_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output_report:
        output_path = Path(args.output_report).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_text, encoding="utf-8")
    print(report_text, end="")  # noqa: T201


if __name__ == "__main__":
    main()
