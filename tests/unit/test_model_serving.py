"""Focused unit coverage for live model serving endpoints.

MLflow auth in production uses SDK env like `MLFLOW_TRACKING_TOKEN`; health
probes are patched here so the tests stay offline-safe.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_contributor_logger
from src.api.endpoints import model_serving
from src.api.endpoints.model_30_adapter import (
    MODEL_30_SCHEMA,
    MODEL_30_VERSION,
    Model30FailurePhase,
    reset_model_30_cache,
    validate_nested_model_30_inputs,
)
from src.api.endpoints.model_registry import ModelRegistryEntry
from src.middleware.auth import require_auth
from src.utils.mlflow_health import MLflowRegistryHealthResult


class FakeContributorLogger:
    """In-memory logger double to avoid database writes in endpoint tests."""

    @staticmethod
    def new_inference_log_id():
        return uuid4()

    def log_inference(self, **_: object) -> None:
        return None


def _minimal_model_30_inputs() -> dict:
    return {
        "task": {
            "description": "Implement password reset flow",
            "task_type": "feature",
        }
    }


def _full_model_30_inputs() -> dict:
    return {
        "task": {
            "description": "Refactor billing webhook retry handling",
            "task_type": "refactor",
            "language": "python",
            "framework": "fastapi",
            "repo_type": "monorepo",
        },
        "routing": {
            "available_models": ["fast-coder-v1", "deep-coder-v2", "db-specialist-v1"],
            "preferred_models": ["deep-coder-v2", "db-specialist-v1"],
            "max_cost_usd": 0.5,
            "max_latency_seconds": 30,
            "prioritize_quality": True,
            "prioritize_speed": False,
        },
        "context": {
            "domain": "payments",
            "repo_size_bucket": "large",
            "requires_tests": True,
            "risk_level": "medium",
            "file_count": 6,
            "estimated_complexity": "medium",
            "security_sensitive": True,
        },
        "workflow": {
            "surface": "wavemill",
            "stages": ["plan", "code", "review"],
            "execution_environment": "ci",
            "human_review_required": True,
        },
        "prediction": {
            "expected_duration_seconds": 1800,
            "expected_cost_usd": 0.45,
            "expected_success_probability": 0.8,
        },
        "outcome": {
            "completed_successfully": False,
            "actual_cost_usd": 0.0,
            "actual_time_seconds": 0.0,
            "retry_count": 0,
            "intervention_required": False,
            "selected_model": "deep-coder-v2",
        },
        "rubric": {
            "quality_score": 0.9,
            "correctness_score": 0.85,
            "human_rating": "strong",
            "benchmark_passed": True,
        },
        "metadata": {
            "external_task_id": "task-123",
            "run_id": "run-456",
            "integration_version": "2026.05",
            "idempotency_key": "idem-789",
        },
    }


def _replace_registry_entry(model_id: str, **changes: object) -> ModelRegistryEntry:
    entry = model_serving.MODEL_CONFIGS[model_id]
    updated = replace(entry, **changes)
    model_serving.MODEL_CONFIGS[model_id] = updated
    return updated


@pytest.fixture()
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(model_serving.router)
    app.dependency_overrides[require_auth] = lambda: {
        "user_id": "test-user",
        "api_key_id": "test-key",
        "scopes": ["model:read", "model:write"],
    }
    app.dependency_overrides[get_contributor_logger] = lambda: FakeContributorLogger()
    return app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_caches() -> None:
    original_entries = dict(model_serving.MODEL_CONFIGS)
    model_serving.serving_service.model_cache.clear()
    reset_model_30_cache()
    yield
    model_serving.MODEL_CONFIGS.clear()
    model_serving.MODEL_CONFIGS.update(original_entries)


def test_get_model_config_model_21_returns_sales_lead_config() -> None:
    config = model_serving.serving_service.get_model_config("21")

    assert config["name"] == "Sales Lead Scoring Model"
    assert config["model_type"] == "sklearn"
    assert config["storage_type"] == "huggingface_private"
    assert config["inference_method"] == "local"


def test_get_model_config_model_30_returns_router_config() -> None:
    config = model_serving.serving_service.get_model_config("30")

    assert config["name"] == "Technical Task Router"
    assert config["model_type"] == "technical_task_router"
    assert config["storage_type"] == "mlflow"
    assert config["inference_method"] == "mlflow_pyfunc"
    assert config["model_version"] == MODEL_30_VERSION
    assert config["schema"] == MODEL_30_SCHEMA
    assert config["model_uri"] == "models:/Technical Task Router/4"


def test_get_model_config_unknown_model_raises_404() -> None:
    with pytest.raises(model_serving.HTTPException) as excinfo:
        model_serving.serving_service.get_model_config("999")

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Model 999 not found"


def test_model_21_info_endpoint_shape_is_stable(client: TestClient) -> None:
    response = client.get("/api/v1/models/21/info")

    assert response.status_code == 200
    assert response.json() == {
        "model_id": "21",
        "name": "Sales Lead Scoring Model",
        "type": "sklearn",
        "storage": "huggingface_private",
        "is_available": True,
        "inference_methods": ["api", "local"],
        "max_batch_size": 100,
    }


def test_model_21_health_endpoint_shape_is_stable(client: TestClient) -> None:
    response = client.get("/api/v1/models/21/health")

    assert response.status_code == 200
    assert response.json() == {
        "model_id": "21",
        "status": "healthy",
        "is_cached": False,
        "storage_type": "huggingface_private",
        "inference_ready": True,
    }


def test_model_30_info_endpoint_returns_mlflow_metadata(client: TestClient) -> None:
    response = client.get("/api/v1/models/30/info")

    assert response.status_code == 200
    assert response.json() == {
        "model_id": "30",
        "name": "Technical Task Router",
        "type": "technical_task_router",
        "storage": "mlflow",
        "is_available": True,
        "inference_methods": ["mlflow_pyfunc"],
        "max_batch_size": 1,
        "model_type": "technical_task_router",
        "storage_type": "mlflow",
        "model_uri": "models:/Technical Task Router/4",
        "model_version": MODEL_30_VERSION,
        "schema": MODEL_30_SCHEMA,
        "description": "MLflow-backed router for nested technical task inputs.",
    }


def test_model_30_health_endpoint_reflects_mlflow_cache(client: TestClient) -> None:
    _replace_registry_entry("30", cache_checker=lambda _: True)
    sdk_result = MLflowRegistryHealthResult(
        status="ok",
        tracking_uri="https://mlflow.test.local:5000",
        latency_ms=12.5,
        sample_model="Technical Task Router",
    )
    with patch(
        "src.api.endpoints.model_serving.check_mlflow_registry_sdk",
        AsyncMock(return_value=sdk_result),
    ):
        response = client.get("/api/v1/models/30/health")

    assert response.status_code == 200
    assert response.json() == {
        "model_id": "30",
        "status": "healthy",
        "is_cached": True,
        "storage_type": "mlflow",
        "inference_ready": True,
        "readiness": {
            "checked": False,
            "model_uri": "models:/Technical Task Router/4",
            "status": "cached",
        },
        "mlflow_sdk": {
            "reachable": True,
            "tracking_uri": "https://mlflow.test.local:5000",
            "latency_ms": 12.5,
            "sample_model": "Technical Task Router",
        },
    }


def test_model_30_health_endpoint_reports_mlflow_sdk_failure(client: TestClient) -> None:
    _replace_registry_entry("30", cache_checker=lambda _: False)
    sdk_result = MLflowRegistryHealthResult(
        status="error",
        tracking_uri="https://mlflow.test.local:5000",
        latency_ms=5000.0,
        error_type="TimeoutError",
        error="MLflow registry SDK probe timed out after 5.0s",
    )

    with patch(
        "src.api.endpoints.model_serving.check_mlflow_registry_sdk",
        AsyncMock(return_value=sdk_result),
    ):
        response = client.get("/api/v1/models/30/health")

    assert response.status_code == 200
    assert response.json()["mlflow_sdk"] == {
        "reachable": False,
        "tracking_uri": "https://mlflow.test.local:5000",
        "latency_ms": 5000.0,
        "sample_model": None,
        "error_type": "TimeoutError",
        "error": "MLflow registry SDK probe timed out after 5.0s",
    }


def test_model_30_predict_minimal_payload_uses_adapter_path(client: TestClient) -> None:
    payload = {"inputs": _minimal_model_30_inputs()}
    normalized_output = {
        "selected_model": "fast-coder-v1",
        "selected_models": ["fast-coder-v1"],
        "confidence": 0.83,
        "rationale": "Budget-friendly choice",
        "estimated_cost_usd": 0.25,
    }

    def validate_mock(raw: dict[str, object]) -> dict[str, object]:
        return raw

    def feature_mock(validated: dict[str, object]) -> dict[str, str]:
        return {"features": "ok"}

    def call_mock(_model_uri: str, _features: object, _timings=None) -> dict[str, str]:
        return {"raw": "output"}

    def normalize_mock(raw_output: object, validated: object) -> dict[str, object]:
        del raw_output, validated
        return normalized_output

    _replace_registry_entry(
        "30",
        input_validator=validate_mock,
        feature_mapper=feature_mock,
        model_caller=call_mock,
        output_normalizer=normalize_mock,
    )

    with patch.object(model_serving.serving_service, "predict_local") as local_predict_mock:
        response = client.post("/api/v1/models/30/predict", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["model_id"] == "30"
    assert body["predictions"] == normalized_output
    assert body["metadata"]["model_uri"] == "models:/Technical Task Router/4"
    assert body["metadata"]["model_version"] == MODEL_30_VERSION
    assert body["metadata"]["schema"] == MODEL_30_SCHEMA
    assert body["metadata"]["inference_method"] == "mlflow_pyfunc"
    assert body["metadata"]["request_id"] == body["inference_log_id"]
    local_predict_mock.assert_not_called()


def test_model_30_predict_full_payload_passes_validated_inputs_to_adapter(
    client: TestClient,
) -> None:
    payload = {"inputs": _full_model_30_inputs()}
    validated_inputs = object()
    normalized_output = {
        "selected_model": "deep-coder-v2",
        "selected_models": ["deep-coder-v2"],
        "confidence": 0.91,
        "rationale": "Preferred high quality route",
        "estimated_cost_usd": 0.42,
    }

    feature_calls: list[object] = []

    def feature_mapper(value: object) -> dict[str, str]:
        feature_calls.append(value)
        return {"features": "ok"}

    _replace_registry_entry(
        "30",
        input_validator=lambda _raw: validated_inputs,
        feature_mapper=feature_mapper,
        model_caller=lambda _model_uri, _features, _timings=None: {"raw": "output"},
        output_normalizer=lambda _raw, _validated: normalized_output,
    )
    response = client.post("/api/v1/models/30/predict", json=payload)

    assert response.status_code == 200
    assert feature_calls == [validated_inputs]


def test_model_30_predict_old_flat_payload_returns_422_and_skips_mlflow(client: TestClient) -> None:
    called = False

    def model_caller(_model_uri: str, _features: object, _timings=None) -> object:
        nonlocal called
        called = True
        return {}

    _replace_registry_entry("30", model_caller=model_caller)
    response = client.post(
        "/api/v1/models/30/predict",
        json={
            "inputs": {
                "schema_version": "technical_task_router_row/v1",
                "task_descriptor": {
                    "task_id": "task-1",
                    "task_type": "feature",
                    "language": "python",
                    "estimated_complexity": "medium",
                },
                "allowed_models": ["fast-coder-v1"],
                "selected_models": ["fast-coder-v1"],
                "max_cost_usd": 0.5,
            }
        },
    )

    assert response.status_code == 422
    assert called is False
    assert "Extra inputs are not permitted" in response.text


def test_model_30_predict_rejects_mixed_nested_and_flat_payload(client: TestClient) -> None:
    called = False

    def model_caller(_model_uri: str, _features: object, _timings=None) -> object:
        nonlocal called
        called = True
        return {}

    _replace_registry_entry("30", model_caller=model_caller)
    response = client.post(
        "/api/v1/models/30/predict",
        json={
            "inputs": {
                **_minimal_model_30_inputs(),
                "allowed_models": ["fast-coder-v1"],
            }
        },
    )

    assert response.status_code == 422
    assert called is False
    assert "Extra inputs are not permitted" in response.text


def test_model_30_predict_missing_task_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/models/30/predict",
        json={
            "inputs": {
                "routing": {"max_cost_usd": 0.5},
            }
        },
    )

    assert response.status_code == 422
    assert "Field required" in response.text


def test_model_30_predict_mlflow_failure_returns_503(client: TestClient, caplog) -> None:
    def failing_model_caller(_model_uri: str, _features: object, _timings=None) -> object:
        raise RuntimeError("registry unavailable")

    _replace_registry_entry(
        "30",
        model_caller=failing_model_caller,
    )
    with caplog.at_level(logging.ERROR):
        response = client.post(
            "/api/v1/models/30/predict",
            json={"inputs": _minimal_model_30_inputs()},
        )

    assert response.status_code == 503
    assert response.json()["detail"].startswith("Technical Task Router MLflow inference failed")
    failure_records = [
        record for record in caplog.records if record.msg == "model_30_inference_failure"
    ]
    assert len(failure_records) == 1
    failure_record = failure_records[0]
    assert failure_record.event_type == "model_30_inference_failure"
    assert failure_record.request_id
    assert failure_record.phase == Model30FailurePhase.PREDICT_CALL.value
    assert failure_record.path_type in {"cold", "warm", "unknown"}
    assert failure_record.exception_class == "RuntimeError"
    assert failure_record.exception_message == "registry unavailable"
    assert failure_record.model_version == MODEL_30_VERSION
    assert failure_record.duration_ms >= 0.0


def test_model_30_predict_response_normalization_failure_returns_503_with_phase(
    client: TestClient, caplog
) -> None:
    _replace_registry_entry(
        "30",
        model_caller=lambda _model_uri, _features, _timings=None: None,
    )
    with caplog.at_level(logging.ERROR):
        response = client.post(
            "/api/v1/models/30/predict",
            json={"inputs": _minimal_model_30_inputs()},
        )

    assert response.status_code == 503
    assert response.json()["detail"].startswith("Technical Task Router MLflow inference failed")
    failure_record = next(
        record for record in caplog.records if record.msg == "model_30_inference_failure"
    )
    assert failure_record.phase == Model30FailurePhase.RESPONSE_NORMALIZATION.value


def test_model_30_predict_mlflow_timeout_returns_504_without_alb_timeout(
    client: TestClient, caplog
) -> None:
    def slow_call(*_: object) -> dict[str, str]:
        time.sleep(0.05)
        return {"selected_model": "fast-coder-v1"}

    original_timeout = model_serving.serving_service.prediction_timeout_seconds
    model_serving.serving_service.prediction_timeout_seconds = 0.01
    try:
        _replace_registry_entry("30", model_caller=slow_call)
        with caplog.at_level(logging.ERROR):
            response = client.post(
                "/api/v1/models/30/predict",
                json={"inputs": _minimal_model_30_inputs()},
            )
    finally:
        model_serving.serving_service.prediction_timeout_seconds = original_timeout

    assert response.status_code == 504
    detail = response.json()["detail"]
    assert "timed out" in detail["error"]
    assert detail["request_id"]
    assert detail["run_id"] is None
    failure_record = next(
        record for record in caplog.records if record.msg == "model_30_inference_failure"
    )
    assert failure_record.phase == Model30FailurePhase.TIMEOUT.value
    assert failure_record.request_id == detail["request_id"]
    assert failure_record.model_version == MODEL_30_VERSION
    assert failure_record.exception_class == "TimeoutError"
    assert failure_record.path_type in {"cold", "warm", "unknown"}
    assert failure_record.duration_ms >= 0.0


def test_model_30_predict_emits_warm_latency_trace(client: TestClient, caplog) -> None:
    payload = {"inputs": _full_model_30_inputs()}
    validated_inputs = validate_nested_model_30_inputs(payload["inputs"])

    def fake_call_mlflow_model_30(
        model_uri: str,
        features: object,
        timings: dict[str, float] | None = None,
    ) -> dict[str, object]:
        del model_uri, features
        if timings is not None:
            timings["artifact_load_ms"] = 0.2
            timings["inference_only_ms"] = 4.5
        return {"raw": "output"}

    _replace_registry_entry(
        "30",
        cache_checker=lambda _: True,
        input_validator=lambda _raw: validated_inputs,
        feature_mapper=lambda _validated: {"features": "ok"},
        model_caller=fake_call_mlflow_model_30,
        output_normalizer=lambda _raw, _validated: {
            "selected_model": "deep-coder-v2",
            "selected_models": ["deep-coder-v2"],
            "confidence": 0.9,
            "rationale": "best match",
            "estimated_cost_usd": 0.42,
        },
    )
    with caplog.at_level(logging.INFO):
        response = client.post("/api/v1/models/30/predict", json=payload)

    assert response.status_code == 200
    trace_record = next(
        record for record in caplog.records if record.msg == "model_30_latency_trace"
    )
    assert trace_record.path_type == "warm"
    assert trace_record.outcome == "success"
    assert trace_record.run_id == "run-456"
    assert trace_record.request_id == response.json()["metadata"]["request_id"]
    assert trace_record.artifact_load_ms == 0.2
    assert trace_record.model_inference_ms == 4.5
    assert trace_record.request_validation_ms >= 0.0
    assert trace_record.model_cache_lookup_ms >= 0.0
    assert trace_record.preprocessor_setup_ms >= 0.0
    assert trace_record.feature_transformation_ms >= 0.0
    assert trace_record.postprocessing_serialization_ms >= 0.0
    assert trace_record.timeout_deadline_boundary_ms >= 0.0


def test_model_30_predict_emits_cold_latency_trace(client: TestClient, caplog) -> None:
    payload = {"inputs": _minimal_model_30_inputs()}

    def fake_call_mlflow_model_30(
        model_uri: str,
        features: object,
        timings: dict[str, float] | None = None,
    ) -> dict[str, object]:
        del model_uri, features
        if timings is not None:
            timings["artifact_load_ms"] = 18.0
            timings["inference_only_ms"] = 3.0
        return {"selected_model": "fast-coder-v1"}

    _replace_registry_entry(
        "30",
        cache_checker=lambda _: False,
        model_caller=fake_call_mlflow_model_30,
    )
    with caplog.at_level(logging.INFO):
        response = client.post("/api/v1/models/30/predict", json=payload)

    assert response.status_code == 200
    trace_record = next(
        record for record in caplog.records if record.msg == "model_30_latency_trace"
    )
    assert trace_record.path_type == "cold"
    assert trace_record.artifact_load_ms == 18.0
    assert trace_record.model_inference_ms == 3.0


def test_model_30_predict_timeout_emits_correlated_trace(client: TestClient, caplog) -> None:
    payload = {"inputs": _full_model_30_inputs()}

    def slow_call(
        model_uri: str,
        features: object,
        timings: dict[str, float] | None = None,
    ) -> dict[str, object]:
        del model_uri, features, timings
        time.sleep(0.05)
        return {"selected_model": "deep-coder-v2"}

    original_timeout = model_serving.serving_service.prediction_timeout_seconds
    model_serving.serving_service.prediction_timeout_seconds = 0.01
    try:
        _replace_registry_entry(
            "30",
            cache_checker=lambda _: False,
            model_caller=slow_call,
        )
        with caplog.at_level(logging.INFO):
            response = client.post("/api/v1/models/30/predict", json=payload)
    finally:
        model_serving.serving_service.prediction_timeout_seconds = original_timeout

    assert response.status_code == 504
    detail = response.json()["detail"]
    trace_record = next(
        record for record in caplog.records if record.msg == "model_30_latency_trace"
    )
    assert trace_record.outcome == "timeout"
    assert trace_record.path_type == "cold"
    assert trace_record.request_id == detail["request_id"]
    assert trace_record.run_id == detail["run_id"] == "run-456"
    assert trace_record.timeout_deadline_boundary_ms > 0.0
    assert trace_record.dominant_phase == "timeout_deadline_boundary"


def test_registry_added_mlflow_model_predicts_without_endpoint_changes(client: TestClient) -> None:
    called_with: dict[str, object] = {}

    def input_validator(raw_inputs: dict[str, object]) -> dict[str, object]:
        return {"validated": raw_inputs}

    def feature_mapper(validated: dict[str, object]) -> dict[str, object]:
        called_with["validated"] = validated
        return {"features": validated}

    def model_caller(
        model_uri: str,
        features: object,
        timings: dict[str, float] | None = None,
    ) -> object:
        called_with["model_uri"] = model_uri
        called_with["features"] = features
        if timings is not None:
            timings["artifact_load_ms"] = 1.0
            timings["inference_only_ms"] = 2.0
        return {"winner": "model-31-coder"}

    def output_normalizer(raw_output: object, validated: dict[str, object]) -> dict[str, object]:
        called_with["raw_output"] = raw_output
        called_with["normalized_validated"] = validated
        return {"selected_model": "model-31-coder", "selected_models": ["model-31-coder"]}

    model_serving.MODEL_CONFIGS["31"] = ModelRegistryEntry(
        name="Hypothetical Router",
        storage_type="mlflow",
        model_type="technical_task_router",
        is_private=False,
        inference_method="mlflow_pyfunc",
        max_batch_size=1,
        supported_inference_methods=("mlflow_pyfunc",),
        model_uri="models:/Hypothetical Router/1",
        model_version="1",
        schema="technical_task_router_inputs/v1",
        input_validator=input_validator,
        feature_mapper=feature_mapper,
        output_normalizer=output_normalizer,
        model_caller=model_caller,
        cache_checker=lambda _uri: True,
    )

    response = client.post("/api/v1/models/31/predict", json={"inputs": _minimal_model_30_inputs()})

    assert response.status_code == 200
    body = response.json()
    assert body["model_id"] == "31"
    assert body["predictions"]["selected_model"] == "model-31-coder"
    assert body["metadata"]["model_uri"] == "models:/Hypothetical Router/1"
    assert called_with["validated"] == {"validated": _minimal_model_30_inputs()}
    assert called_with["features"] == {"features": {"validated": _minimal_model_30_inputs()}}


def test_model_21_info_health_predict_regression(client: TestClient) -> None:
    with patch.object(
        model_serving.serving_service,
        "serve_prediction",
        new=AsyncMock(return_value={"lead_score": 75, "recommendation": "Hot"}),
    ):
        info_response = client.get("/api/v1/models/21/info")
        health_response = client.get("/api/v1/models/21/health")
        predict_response = client.post(
            "/api/v1/models/21/predict",
            json={"inputs": {"company_size": 1000, "engagement_score": 80}},
        )

    assert info_response.status_code == 200
    assert health_response.status_code == 200
    assert predict_response.status_code == 200
    assert predict_response.json()["model_id"] == "21"
    assert predict_response.json()["predictions"]["lead_score"] == 75
