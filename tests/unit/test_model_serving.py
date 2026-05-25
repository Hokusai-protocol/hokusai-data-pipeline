"""Focused unit coverage for live model serving endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_contributor_logger
from src.api.endpoints import model_serving
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
def clear_model_cache() -> None:
    model_serving.serving_service.model_cache.clear()


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
    assert config["inference_method"] == "local"
    assert config["model_version"] == "v1"
    assert config["schema"] == "technical_task_router_inputs/v1"


def test_get_model_config_unknown_model_raises_404() -> None:
    with pytest.raises(model_serving.HTTPException) as excinfo:
        model_serving.serving_service.get_model_config("999")

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Model 999 not found"


def test_model_21_info_endpoint_shape_is_stable(client: TestClient) -> None:
    response = client.get("/api/v1/models/21/info")

    assert response.status_code == 200
    body = response.json()
    assert body == {
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


def test_model_30_info_endpoint_returns_router_metadata(client: TestClient) -> None:
    response = client.get("/api/v1/models/30/info")

    assert response.status_code == 200
    body = response.json()
    assert body["model_id"] == "30"
    assert body["name"] == "Technical Task Router"
    assert body["type"] == "technical_task_router"
    assert body["storage"] == "in_process"
    assert body["inference_methods"] == ["local"]
    assert body["model_version"] == "v1"
    assert body["schema"] == "technical_task_router_inputs/v1"


def test_model_30_health_endpoint_is_ready(client: TestClient) -> None:
    response = client.get("/api/v1/models/30/health")

    assert response.status_code == 200
    assert response.json() == {
        "model_id": "30",
        "status": "healthy",
        "is_cached": False,
        "storage_type": "in_process",
        "inference_ready": True,
    }


def test_model_30_predict_minimal_payload_succeeds(client: TestClient) -> None:
    payload = {"inputs": _minimal_model_30_inputs()}

    response = client.post("/api/v1/models/30/predict", json=payload)

    assert response.status_code == 200
    body = response.json()
    predictions = body["predictions"]

    assert body["model_id"] == "30"
    assert predictions["status"] == "success"
    assert predictions["selected_models"]
    assert predictions["actual_cost_usd"] <= predictions["max_cost_usd"]
    assert predictions["task"] == payload["inputs"]["task"]


def test_model_30_predict_full_payload_accepts_all_groups(client: TestClient) -> None:
    payload = {"inputs": _full_model_30_inputs()}

    response = client.post("/api/v1/models/30/predict", json=payload)

    assert response.status_code == 200
    predictions = response.json()["predictions"]
    assert predictions["status"] == "success"
    assert predictions["task"] == payload["inputs"]["task"]
    assert len(predictions["selected_models"]) == 1
    assert predictions["selected_models"][0] in payload["inputs"]["routing"]["preferred_models"]
    assert predictions["max_cost_usd"] == payload["inputs"]["routing"]["max_cost_usd"]


def test_model_30_predict_over_budget_with_nested_budget(client: TestClient) -> None:
    payload = {
        "inputs": {
            **_minimal_model_30_inputs(),
            "routing": {"max_cost_usd": 0.01},
        }
    }

    response = client.post("/api/v1/models/30/predict", json=payload)

    assert response.status_code == 200
    predictions = response.json()["predictions"]
    assert predictions["status"] == "over_budget"
    assert predictions["selected_models"] == []
    assert predictions["actual_cost_usd"] == 0.0
    assert predictions["max_cost_usd"] == 0.01


def test_model_30_predict_available_model_constraint_is_respected(client: TestClient) -> None:
    payload = {
        "inputs": {
            **_minimal_model_30_inputs(),
            "routing": {"available_models": ["db-specialist-v1", "deep-coder-v2"]},
        }
    }

    response = client.post("/api/v1/models/30/predict", json=payload)

    assert response.status_code == 200
    predictions = response.json()["predictions"]
    assert set(predictions["selected_models"]).issubset(
        set(payload["inputs"]["routing"]["available_models"])
    )


def test_model_30_predict_allows_optional_groups_to_be_null(client: TestClient) -> None:
    payload = {
        "inputs": {
            **_minimal_model_30_inputs(),
            "routing": None,
            "context": None,
            "workflow": None,
            "prediction": None,
            "outcome": None,
            "rubric": None,
            "metadata": None,
        }
    }

    response = client.post("/api/v1/models/30/predict", json=payload)

    assert response.status_code == 200
    assert response.json()["predictions"]["status"] == "success"


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


def test_model_30_predict_old_flat_payload_returns_422(client: TestClient) -> None:
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
                "max_cost_usd": 0.5,
            }
        },
    )

    assert response.status_code == 422
    assert "Extra inputs are not permitted" in response.text


def test_model_30_predict_rejects_mixed_nested_and_flat_payload(client: TestClient) -> None:
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
    assert "Extra inputs are not permitted" in response.text


def test_model_30_predict_rejects_stray_nested_field(client: TestClient) -> None:
    response = client.post(
        "/api/v1/models/30/predict",
        json={
            "inputs": {
                "task": {
                    "description": "Implement password reset flow",
                    "task_type": "feature",
                    "priority": "high",
                }
            }
        },
    )

    assert response.status_code == 422
    assert "Extra inputs are not permitted" in response.text


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
