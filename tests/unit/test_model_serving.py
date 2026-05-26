"""Focused unit coverage for live model serving endpoints."""

from __future__ import annotations

import logging
import time
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
    reset_model_30_cache,
)
from src.middleware.auth import require_auth


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
    model_serving.serving_service.model_cache.clear()
    reset_model_30_cache()


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
    with patch("src.api.endpoints.model_serving.is_model_30_cached", return_value=True):
        response = client.get("/api/v1/models/30/health")

    assert response.status_code == 200
    assert response.json() == {
        "model_id": "30",
        "status": "healthy",
        "is_cached": True,
        "storage_type": "mlflow",
        "inference_ready": True,
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

    with (
        patch(
            "src.api.endpoints.model_serving.validate_nested_model_30_inputs",
            side_effect=lambda raw: raw,
        ) as validate_mock,
        patch(
            "src.api.endpoints.model_serving.model_30_inputs_to_features",
            return_value={"features": "ok"},
        ) as feature_mock,
        patch(
            "src.api.endpoints.model_serving.call_mlflow_model_30",
            return_value={"raw": "output"},
        ) as call_mock,
        patch(
            "src.api.endpoints.model_serving.normalize_model_30_output",
            return_value=normalized_output,
        ) as normalize_mock,
        patch.object(model_serving.serving_service, "predict_local") as local_predict_mock,
    ):
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
    validate_mock.assert_called_once_with(payload["inputs"])
    feature_mock.assert_called_once_with(payload["inputs"])
    assert call_mock.call_count == 1
    assert call_mock.call_args.args[:2] == ("models:/Technical Task Router/4", {"features": "ok"})
    assert isinstance(call_mock.call_args.args[2], dict)
    normalize_mock.assert_called_once_with({"raw": "output"}, payload["inputs"])
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

    with (
        patch(
            "src.api.endpoints.model_serving.validate_nested_model_30_inputs",
            return_value=validated_inputs,
        ),
        patch(
            "src.api.endpoints.model_serving.model_30_inputs_to_features",
            return_value={"features": "ok"},
        ) as feature_mock,
        patch(
            "src.api.endpoints.model_serving.call_mlflow_model_30",
            return_value={"raw": "output"},
        ),
        patch(
            "src.api.endpoints.model_serving.normalize_model_30_output",
            return_value=normalized_output,
        ),
    ):
        response = client.post("/api/v1/models/30/predict", json=payload)

    assert response.status_code == 200
    feature_mock.assert_called_once_with(validated_inputs)


def test_model_30_predict_old_flat_payload_returns_422_and_skips_mlflow(client: TestClient) -> None:
    with patch("src.api.endpoints.model_serving.call_mlflow_model_30") as call_mock:
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
    call_mock.assert_not_called()
    assert "Extra inputs are not permitted" in response.text


def test_model_30_predict_rejects_mixed_nested_and_flat_payload(client: TestClient) -> None:
    with patch("src.api.endpoints.model_serving.call_mlflow_model_30") as call_mock:
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
    call_mock.assert_not_called()
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


def test_model_30_predict_mlflow_failure_returns_503(client: TestClient) -> None:
    with patch(
        "src.api.endpoints.model_serving.call_mlflow_model_30",
        side_effect=RuntimeError("registry unavailable"),
    ):
        response = client.post(
            "/api/v1/models/30/predict",
            json={"inputs": _minimal_model_30_inputs()},
        )

    assert response.status_code == 503
    assert response.json()["detail"].startswith("Model 30 MLflow inference failed")


def test_model_30_predict_mlflow_timeout_returns_504_without_alb_timeout(
    client: TestClient,
) -> None:
    def slow_call(*_: object) -> dict[str, str]:
        time.sleep(0.05)
        return {"selected_model": "fast-coder-v1"}

    original_timeout = model_serving.serving_service.prediction_timeout_seconds
    model_serving.serving_service.prediction_timeout_seconds = 0.01
    try:
        with patch(
            "src.api.endpoints.model_serving.call_mlflow_model_30",
            side_effect=slow_call,
        ):
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


def test_model_30_predict_emits_warm_latency_trace(client: TestClient, caplog) -> None:
    payload = {"inputs": _full_model_30_inputs()}
    validated_inputs = model_serving.validate_nested_model_30_inputs(payload["inputs"])

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

    with (
        patch("src.api.endpoints.model_serving.is_model_30_cached", return_value=True),
        patch(
            "src.api.endpoints.model_serving.validate_nested_model_30_inputs",
            return_value=validated_inputs,
        ),
        patch(
            "src.api.endpoints.model_serving.model_30_inputs_to_features",
            return_value={"features": "ok"},
        ),
        patch(
            "src.api.endpoints.model_serving.call_mlflow_model_30",
            side_effect=fake_call_mlflow_model_30,
        ),
        patch(
            "src.api.endpoints.model_serving.normalize_model_30_output",
            return_value={
                "selected_model": "deep-coder-v2",
                "selected_models": ["deep-coder-v2"],
                "confidence": 0.9,
                "rationale": "best match",
                "estimated_cost_usd": 0.42,
            },
        ),
        caplog.at_level(logging.INFO),
    ):
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

    with (
        patch("src.api.endpoints.model_serving.is_model_30_cached", return_value=False),
        patch(
            "src.api.endpoints.model_serving.call_mlflow_model_30",
            side_effect=fake_call_mlflow_model_30,
        ),
        caplog.at_level(logging.INFO),
    ):
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
        with (
            patch("src.api.endpoints.model_serving.is_model_30_cached", return_value=False),
            patch(
                "src.api.endpoints.model_serving.call_mlflow_model_30",
                side_effect=slow_call,
            ),
            caplog.at_level(logging.INFO),
        ):
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
