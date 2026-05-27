"""Optional integration coverage for live model 30 MLflow serving.

This test expects the environment to provide MLflow auth, typically through
`MLFLOW_TRACKING_TOKEN` and the same mTLS settings used by the API container.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
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
from src.utils.mlflow_health import MLflowRegistryHealthResult

TRACKING_READY = bool(os.getenv("MLFLOW_TRACKING_URI"))
FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "test_fixtures"


class FakeContributorLogger:
    @staticmethod
    def new_inference_log_id():
        return uuid4()

    def log_inference(self, **_: object) -> None:
        return None


@pytest.fixture(autouse=True)
def restore_model_configs():
    original_entries = dict(model_serving.MODEL_CONFIGS)
    yield
    model_serving.MODEL_CONFIGS.clear()
    model_serving.MODEL_CONFIGS.update(original_entries)


def _replace_registry_entry(model_id: str, **changes: object) -> None:
    model_serving.MODEL_CONFIGS[model_id] = replace(
        model_serving.MODEL_CONFIGS[model_id],
        **changes,
    )


@pytest.mark.skipif(not TRACKING_READY, reason="MLFLOW_TRACKING_URI is required")
@pytest.mark.live_mlflow
def test_live_model_30_mlflow_prediction_round_trip() -> None:
    mlflow = pytest.importorskip("mlflow")
    payload = _load_json_fixture("model_30_curated_payload.json")
    normalized = _load_predict_and_normalize_model_30(payload, mlflow_module=mlflow)

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

    _replace_registry_entry(
        "30",
        cache_checker=lambda _uri: True,
        model_caller=lambda _uri, _features, timings=None: (
            timings.update({"artifact_load_ms": 0.1, "inference_only_ms": 2.0})
            or {"selected_model": "fast-coder-v1", "confidence": 0.8}
        ),
    )
    with caplog.at_level(logging.INFO):
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


def test_model_30_health_reports_not_ready_until_cached() -> None:
    app = FastAPI()
    app.include_router(model_serving.router)
    app.dependency_overrides[require_auth] = lambda: {
        "user_id": "integration-user",
        "api_key_id": "integration-key",
        "scopes": ["model:read"],
    }
    client = TestClient(app)

    _replace_registry_entry("30", cache_checker=lambda _uri: False)
    sdk_result = MLflowRegistryHealthResult(
        status="ok",
        tracking_uri="https://mlflow:5000",
        latency_ms=8.4,
        sample_model="Technical Task Router",
    )
    with patch(
        "src.api.endpoints.model_serving.check_mlflow_registry_sdk",
        AsyncMock(return_value=sdk_result),
    ):
        response = client.get("/api/v1/models/30/health")

    assert response.status_code == 200
    body = response.json()
    assert body["is_cached"] is False
    assert body["inference_ready"] is False
    assert body["readiness"]["checked"] is False
    assert body["readiness"]["status"] == "not_cached"
    assert body["mlflow_sdk"]["reachable"] is True


def test_model_30_health_warmup_runs_minimal_prediction() -> None:
    app = FastAPI()
    app.include_router(model_serving.router)
    app.dependency_overrides[require_auth] = lambda: {
        "user_id": "integration-user",
        "api_key_id": "integration-key",
        "scopes": ["model:read"],
    }
    client = TestClient(app)

    cache_states = [False, True]

    def _is_cached(_uri: str) -> bool:
        return cache_states.pop(0) if cache_states else True

    call_count = 0

    def model_caller(_uri, _features, timings=None):
        nonlocal call_count
        call_count += 1
        return timings.update({"artifact_load_ms": 1.5, "inference_only_ms": 0.5}) or {
            "selected_model": "fast-coder-v1",
            "confidence": 0.8,
        }

    _replace_registry_entry("30", cache_checker=_is_cached, model_caller=model_caller)
    sdk_result = MLflowRegistryHealthResult(
        status="ok",
        tracking_uri="https://mlflow:5000",
        latency_ms=9.1,
        sample_model="Technical Task Router",
    )
    with patch(
        "src.api.endpoints.model_serving.check_mlflow_registry_sdk",
        AsyncMock(return_value=sdk_result),
    ):
        response = client.get("/api/v1/models/30/health?warmup=true")

    assert response.status_code == 200
    body = response.json()
    assert body["is_cached"] is True
    assert body["inference_ready"] is True
    assert body["readiness"]["checked"] is True
    assert body["readiness"]["status"] == "ready"
    assert body["readiness"]["selected_model"] == "fast-coder-v1"
    assert body["mlflow_sdk"]["reachable"] is True
    assert call_count == 1


def test_model_30_live_path_rejects_mocked_load_model() -> None:
    payload = _load_json_fixture("model_30_curated_payload.json")
    fake_mlflow = SimpleNamespace(pyfunc=SimpleNamespace(load_model=lambda _uri: MagicMock()))

    with pytest.raises(
        AssertionError,
        match="load_model returned a mock; live_mlflow bypass did not engage",
    ):
        _load_predict_and_normalize_model_30(payload, mlflow_module=fake_mlflow)


def test_model_30_live_path_rejects_not_implemented_predict() -> None:
    payload = _load_json_fixture("model_30_curated_payload.json")

    def _predict(_features):
        raise NotImplementedError("predict not implemented")

    fake_model = SimpleNamespace(predict=_predict)
    fake_mlflow = SimpleNamespace(pyfunc=SimpleNamespace(load_model=lambda _uri: fake_model))

    with pytest.raises(AssertionError, match="predict\\(\\) raised NotImplementedError"):
        _load_predict_and_normalize_model_30(payload, mlflow_module=fake_mlflow)


def test_model_30_live_path_rejects_non_normalizable_output() -> None:
    payload = _load_json_fixture("model_30_curated_payload.json")
    fake_model = SimpleNamespace(predict=lambda _features: [])
    fake_mlflow = SimpleNamespace(pyfunc=SimpleNamespace(load_model=lambda _uri: fake_model))

    with pytest.raises(ValueError, match="empty"):
        _load_predict_and_normalize_model_30(payload, mlflow_module=fake_mlflow)


def _load_predict_and_normalize_model_30(
    payload: dict[str, object], *, mlflow_module: object
) -> dict[str, object]:
    validated_inputs = validate_nested_model_30_inputs(payload)
    features = model_30_inputs_to_features(validated_inputs)
    loaded_model = mlflow_module.pyfunc.load_model(get_model_30_uri())

    assert not isinstance(
        loaded_model, MagicMock
    ), "load_model returned a mock; live_mlflow bypass did not engage"

    try:
        raw_output = loaded_model.predict(features)
    except NotImplementedError as exc:
        raise AssertionError(f"predict() raised NotImplementedError: {exc}") from exc

    return normalize_model_30_output(raw_output, validated_inputs)


def _load_json_fixture(filename: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))
