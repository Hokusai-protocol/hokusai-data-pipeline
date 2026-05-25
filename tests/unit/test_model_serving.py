"""Focused unit coverage for live model serving endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_contributor_logger
from src.api.endpoints import model_serving
from src.middleware.auth import require_auth

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "schema" / "examples"


class FakeContributorLogger:
    """In-memory logger double to avoid database writes in endpoint tests."""

    @staticmethod
    def new_inference_log_id():
        return uuid4()

    def log_inference(self, **_: object) -> None:
        return None


def _load_example(filename: str) -> dict:
    return json.loads((EXAMPLES_DIR / filename).read_text(encoding="utf-8"))


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
    assert config["schema"] == "technical_task_router_row/v1"


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
    assert body["schema"] == "technical_task_router_row/v1"


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


def test_model_30_predict_success_fixture(client: TestClient) -> None:
    payload = {"inputs": _load_example("technical_task_router_row.success.v1.json")}

    response = client.post("/api/v1/models/30/predict", json=payload)

    assert response.status_code == 200
    body = response.json()
    predictions = body["predictions"]
    allowed_models = set(payload["inputs"]["allowed_models"])
    selected_models = predictions["selected_models"]

    assert body["model_id"] == "30"
    assert predictions["status"] == "success"
    assert selected_models
    assert set(selected_models).issubset(allowed_models)
    assert predictions["actual_cost_usd"] <= predictions["max_cost_usd"]
    assert predictions["schema_version"] == "technical_task_router_row/v1"


def test_model_30_predict_over_budget_fixture(client: TestClient) -> None:
    payload = {"inputs": _load_example("technical_task_router_row.over_budget.v1.json")}

    response = client.post("/api/v1/models/30/predict", json=payload)

    assert response.status_code == 200
    predictions = response.json()["predictions"]
    assert predictions["status"] == "over_budget"
    assert predictions["selected_models"] == []
    assert predictions["actual_cost_usd"] == 0.0


def test_model_30_predict_disallowed_fixture_does_not_select_unapproved_model(
    client: TestClient,
) -> None:
    payload = {"inputs": _load_example("technical_task_router_row.disallowed_model.v1.json")}

    response = client.post("/api/v1/models/30/predict", json=payload)

    assert response.status_code == 200
    predictions = response.json()["predictions"]
    assert set(predictions["selected_models"]).issubset(set(payload["inputs"]["allowed_models"]))


def test_model_30_predict_invalid_payload_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/models/30/predict",
        json={
            "inputs": {
                "schema_version": "technical_task_router_row/v1",
                "row_id": "bad-row",
                "benchmark_spec_id": "bench",
                "eval_id": "eval",
                "model_id": "technical-task-router-challenger",
                "task_descriptor": {
                    "task_id": "task-1",
                    "task_type": "code_debugging",
                    "language": "python",
                    "estimated_complexity": "medium",
                },
                "allowed_models": ["fast-coder-v1"],
                "selected_models": [],
                "max_cost_usd": 0,
                "actual_cost_usd": 0,
                "completed_successfully": False,
                "scorer_ref": "technical_task_router.success_under_budget/v1",
                "observed_at": "2026-05-12T12:00:00Z",
            }
        },
    )

    assert response.status_code == 422
    assert "greater than 0" in response.text


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
