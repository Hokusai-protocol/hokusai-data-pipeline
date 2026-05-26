"""Optional integration coverage for live model 30 MLflow serving.

This test expects the environment to provide MLflow auth, typically through
`MLFLOW_TRACKING_TOKEN` and the same mTLS settings used by the API container.
"""

from __future__ import annotations

import os

import pytest

from src.api.endpoints.model_30_adapter import (
    get_model_30_uri,
    model_30_inputs_to_features,
    normalize_model_30_output,
    validate_nested_model_30_inputs,
)

RUN_INTEGRATION = os.getenv("MODEL_30_INTEGRATION_TEST") == "1"
TRACKING_READY = bool(os.getenv("MLFLOW_TRACKING_URI"))

pytestmark = pytest.mark.skipif(
    not RUN_INTEGRATION or not TRACKING_READY,
    reason="MODEL_30_INTEGRATION_TEST=1 and MLFLOW_TRACKING_URI are required",
)


def test_live_model_30_mlflow_prediction_round_trip() -> None:
    mlflow = pytest.importorskip("mlflow")

    payload = {
        "task": {
            "description": "Refactor webhook retry handling in a FastAPI service",
            "task_type": "refactor",
            "language": "python",
            "framework": "fastapi",
            "repo_type": "monorepo",
        },
        "routing": {
            "available_models": ["fast-coder-v1", "deep-coder-v2"],
            "preferred_models": ["deep-coder-v2"],
            "max_cost_usd": 0.5,
            "prioritize_quality": True,
        },
        "context": {
            "domain": "payments",
            "estimated_complexity": "medium",
            "requires_tests": True,
        },
        "workflow": {
            "surface": "wavemill",
            "stages": ["plan", "code", "review"],
        },
        "metadata": {
            "external_task_id": "integration-smoke-task",
            "run_id": "integration-smoke-run",
        },
    }

    validated_inputs = validate_nested_model_30_inputs(payload)
    features = model_30_inputs_to_features(validated_inputs)
    raw_output = mlflow.pyfunc.load_model(get_model_30_uri()).predict(features)
    normalized = normalize_model_30_output(raw_output, validated_inputs)

    assert normalized["selected_model"]
    assert normalized["selected_models"]
    assert isinstance(normalized["confidence"], float)
    assert isinstance(normalized["estimated_cost_usd"], float)
