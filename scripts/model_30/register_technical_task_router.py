"""Register the callable Technical Task Router pyfunc model.

This script intentionally uses direct ``mlflow.pyfunc.log_model`` registration
with ``registered_model_name="Technical Task Router"``. It does not use the
artifact-reference helper that produced the non-callable model 30 wrapper.
MLflow authentication is provided by the SDK environment, including
``MLFLOW_TRACKING_TOKEN`` when the registry requires bearer auth.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import mlflow
import mlflow.pyfunc
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.technical_task_router import (  # noqa: E402
    MODEL_NAME,
    ROUTER_DATASET_ARTIFACT,
    TechnicalTaskRouterModel,
)


def _sample_features() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "schema_version": "technical_task_router_inputs/v1",
                "task_descriptor": "{}",
                "task_description": "Refactor billing webhook retry handling",
                "task_type": "refactor",
                "language": "python",
                "framework": "fastapi",
                "repo_type": "monorepo",
                "allowed_models": '["claude-sonnet-4-5-20250929","gpt-5.4"]',
                "preferred_models": '["claude-sonnet-4-5-20250929"]',
                "max_cost_usd": 10.0,
                "domain": "backend",
                "repo_size_bucket": "large",
                "requires_tests": True,
                "risk_level": "medium",
                "file_count": 6,
                "estimated_complexity": "medium",
                "security_sensitive": False,
                "surface": "wavemill",
                "workflow_stages": '["plan","code","review"]',
                "expected_cost_usd": 5.0,
                "expected_success_probability": 0.8,
            }
        ]
    )


def _registered_model_uri(model_name: str, version: str | None) -> str:
    if version:
        return f"models:/{model_name}/{version}"
    return f"models:/{model_name}/latest"


def register_model(args: argparse.Namespace) -> dict[str, Any]:
    """Log and register the callable Technical Task Router model."""
    dataset_path = Path(args.router_dataset).expanduser().resolve()
    if not dataset_path.exists():
        raise FileNotFoundError(f"Router dataset not found: {dataset_path}")

    if args.tracking_uri:
        mlflow.set_tracking_uri(args.tracking_uri)

    experiment_name = args.experiment_name or os.getenv(
        "MODEL_30_EXPERIMENT_NAME",
        "technical-task-router",
    )
    mlflow.set_experiment(experiment_name)

    sample_features = _sample_features()
    local_model = TechnicalTaskRouterModel(k_neighbors=args.k_neighbors)
    local_model.load_context(
        type(
            "Context",
            (),
            {"artifacts": {ROUTER_DATASET_ARTIFACT: str(dataset_path)}},
        )()
    )
    local_model.predict(None, sample_features)

    with mlflow.start_run(run_name=args.run_name) as run:
        mlflow.log_param("model_name", MODEL_NAME)
        mlflow.log_param("router_dataset", str(dataset_path))
        mlflow.log_param("k_neighbors", args.k_neighbors)
        # Do not log a strict signature: the public adapter sends nullable
        # optional columns, and the router normalizes them inside predict().
        model_info = mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=TechnicalTaskRouterModel(k_neighbors=args.k_neighbors),
            artifacts={ROUTER_DATASET_ARTIFACT: str(dataset_path)},
            registered_model_name=MODEL_NAME,
            pip_requirements=[
                "mlflow==3.9.0",
                "pandas",
            ],
        )

    version = getattr(model_info, "registered_model_version", None)
    model_uri = _registered_model_uri(MODEL_NAME, str(version) if version else None)
    result = {
        "run_id": run.info.run_id,
        "artifact_uri": model_info.model_uri,
        "registered_model_name": MODEL_NAME,
        "registered_model_version": str(version) if version else None,
        "registered_model_uri": model_uri,
    }

    if args.smoke:
        loaded = mlflow.pyfunc.load_model(model_uri)
        prediction = loaded.predict(sample_features)
        result["smoke_prediction"] = prediction.to_dict(orient="records")

    return result


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--router-dataset",
        required=True,
        help="Path to the Wavemill hokusai-router-dataset.csv artifact.",
    )
    parser.add_argument("--tracking-uri", default=os.getenv("MLFLOW_TRACKING_URI"))
    parser.add_argument("--experiment-name")
    parser.add_argument("--run-name", default="technical-task-router-callable")
    parser.add_argument("--k-neighbors", type=int, default=40)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Load the registered model URI and call predict after registration.",
    )
    return parser.parse_args()


def main() -> None:
    """Run model registration from the command line."""
    result = register_model(parse_args())
    for key, value in result.items():
        print(f"{key}: {value}")  # noqa: T201


if __name__ == "__main__":
    main()
