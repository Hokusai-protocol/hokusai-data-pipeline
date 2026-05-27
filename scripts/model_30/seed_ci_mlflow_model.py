"""Seed a lightweight MLflow pyfunc model for health-test CI.

Authentication follows the normal MLflow SDK environment, including
`MLFLOW_TRACKING_TOKEN` when the registry requires bearer auth.
"""

from __future__ import annotations

import os
from typing import Any

import mlflow
import mlflow.pyfunc
import pandas as pd

MODEL_NAME = os.getenv("MODEL_30_REGISTERED_MODEL_NAME", "Technical Task Router")
EXPERIMENT_NAME = os.getenv("MODEL_30_EXPERIMENT_NAME", "technical-task-router-ci")


class TechnicalTaskRouterSmokeModel(mlflow.pyfunc.PythonModel):
    """Minimal pyfunc model that matches the model 30 response contract."""

    def predict(
        self: TechnicalTaskRouterSmokeModel,
        context,  # noqa: ANN001
        model_input: Any,
    ) -> pd.DataFrame:
        del context
        rows = len(model_input.index) if hasattr(model_input, "index") else 1
        return pd.DataFrame(
            [
                {
                    "selected_model": "fast-coder-v1",
                    "selected_models": ["fast-coder-v1", "deep-coder-v2"],
                    "confidence": 0.91,
                    "rationale": "Seeded smoke model for MLflow mTLS integration coverage",
                    "estimated_cost_usd": 0.42,
                }
                for _ in range(rows)
            ]
        )


def main() -> None:
    """Register and smoke-load the CI model against the configured MLflow server."""
    tracking_uri = os.environ["MLFLOW_TRACKING_URI"]
    tracking_token = os.getenv("MLFLOW_TRACKING_TOKEN")
    if tracking_token:
        os.environ["MLFLOW_TRACKING_TOKEN"] = tracking_token
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(EXPERIMENT_NAME)

    with mlflow.start_run(run_name="technical-task-router-ci-seed"):
        model_info = mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=TechnicalTaskRouterSmokeModel(),
            registered_model_name=MODEL_NAME,
            pip_requirements=["mlflow==3.9.0", "pandas"],
        )

    latest_uri = f"models:/{MODEL_NAME}/latest"
    loaded = mlflow.pyfunc.load_model(latest_uri)
    sample = pd.DataFrame(
        [
            {
                "task_type": "feature",
                "language": "python",
                "framework": "fastapi",
                "repo_type": "monorepo",
            }
        ]
    )
    loaded.predict(sample)
    version = getattr(model_info, "registered_model_version", None)
    print(f"seeded_model_name={MODEL_NAME}")  # noqa: T201
    print(f"seeded_model_version={version}")  # noqa: T201
    print(f"seeded_model_uri={latest_uri}")  # noqa: T201


if __name__ == "__main__":
    main()
