"""Optional integration coverage for live model 30 MLflow serving.

This test expects the environment to provide MLflow auth, typically through
`MLFLOW_TRACKING_TOKEN` and the same mTLS settings used by the API container.
"""

from __future__ import annotations

import logging
import os
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_contributor_logger
from src.api.endpoints import model_serving
from src.api.endpoints.model_30_adapter import (
    get_model_30_uri,
    model_30_inputs_to_features,
    normalize_model_30_output,
    validate_nested_model_30_inputs,
)
from src.middleware.auth import require_auth

RUN_INTEGRATION = os.getenv("MODEL_30_INTEGRATION_TEST") == "1"
TRACKING_READY = bool(os.getenv("MLFLOW_TRACKING_URI"))


class FakeContributorLogger:
    @staticmethod
    def new_inference_log_id():
        return uuid4()

    def log_inference(self, **_: object) -> None:
        return None


@pytest.mark.skipif(
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


def test_model_30_predict_emits_single_latency_trace_record(caplog) -> None:
    app = FastAPI()
    app.include_router(model_serving.router)
    app.dependency_overrides[require_auth] = lambda: {
        "user_id": "integration-user",
        "api_key_id": "integration-key",
        "scopes": ["model:write"],
    }
    app.dependency_overrides[get_contributor_logger] = lambda: FakeContributorLogger()
    client = TestClient(app)

    with (
        patch("src.api.endpoints.model_serving.is_model_30_cached", return_value=True),
        patch(
            "src.api.endpoints.model_serving.call_mlflow_model_30",
            side_effect=lambda _uri, _features, timings=None: (
                timings.update({"artifact_load_ms": 0.1, "inference_only_ms": 2.0})
                or {"selected_model": "fast-coder-v1", "confidence": 0.8}
            ),
        ),
        caplog.at_level(logging.INFO),
    ):
        response = client.post(
            "/api/v1/models/30/predict",
            json={
                "inputs": {
                    "task": {
                        "description": "Instrument the warm path",
                        "task_type": "feature",
                    },
                    "metadata": {"run_id": "integration-run-123"},
                }
            },
        )

    assert response.status_code == 200
    trace_records = [record for record in caplog.records if record.msg == "model_30_latency_trace"]
    assert len(trace_records) == 1
    trace_record = trace_records[0]
    assert trace_record.event == "model_30_latency_trace"
    assert trace_record.path_type == "warm"
    assert trace_record.outcome == "success"
    assert trace_record.run_id == "integration-run-123"
    assert trace_record.request_id == response.json()["metadata"]["request_id"]
    assert trace_record.request_validation_ms >= 0.0
    assert trace_record.model_cache_lookup_ms >= 0.0
    assert trace_record.artifact_load_ms == 0.1
    assert trace_record.preprocessor_setup_ms >= 0.0
    assert trace_record.feature_transformation_ms >= 0.0
    assert trace_record.model_inference_ms == 2.0
    assert trace_record.postprocessing_serialization_ms >= 0.0
    assert trace_record.timeout_deadline_boundary_ms >= 0.0
