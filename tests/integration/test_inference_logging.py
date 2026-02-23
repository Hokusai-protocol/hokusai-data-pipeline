"""Integration tests for inference usage logging and deferred outcomes."""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_contributor_logger
from src.api.endpoints import model_serving
from src.api.routes.outcomes import router as outcomes_router
from src.middleware.auth import require_auth


class InMemoryContributorLogger:
    """Test double that mimics the contributor logger contract."""

    def __init__(self) -> None:
        self.rows: dict[UUID, dict[str, object]] = {}

    def new_inference_log_id(self) -> UUID:
        return uuid4()

    def log_inference(
        self,
        api_token_id: str,
        model_name: str,
        model_version: str,
        input_payload: dict,
        output_payload: dict | None,
        trace_metadata: dict | None,
        inference_log_id: UUID | None = None,
    ) -> UUID:
        log_id = inference_log_id or uuid4()
        self.rows[log_id] = {
            "api_token_id": api_token_id,
            "model_name": model_name,
            "model_version": model_version,
            "input_payload": input_payload,
            "output_payload": output_payload,
            "trace_metadata": trace_metadata,
            "outcome_score": None,
            "outcome_type": None,
        }
        return log_id

    def record_outcome(
        self,
        inference_log_id: UUID,
        api_token_id: str,
        outcome_score: float,
        outcome_type: str,
    ) -> None:
        if inference_log_id not in self.rows:
            from src.api.services.contributor_logger import InferenceLogNotFoundError

            raise InferenceLogNotFoundError(str(inference_log_id))

        row = self.rows[inference_log_id]
        if row["api_token_id"] != api_token_id:
            from src.api.services.contributor_logger import InferenceLogOwnershipError

            raise InferenceLogOwnershipError(str(inference_log_id))

        row["outcome_score"] = outcome_score
        row["outcome_type"] = outcome_type


def test_predict_and_record_outcome_flow() -> None:
    app = FastAPI()
    app.include_router(model_serving.router)
    app.include_router(outcomes_router)

    in_memory_logger = InMemoryContributorLogger()

    app.dependency_overrides[get_contributor_logger] = lambda: in_memory_logger
    app.dependency_overrides[require_auth] = lambda: {
        "user_id": "user-1",
        "api_key_id": "key-123",
        "scopes": ["model:read"],
    }

    with patch("src.api.endpoints.model_serving.serving_service.serve_prediction") as mock_predict:
        mock_predict.return_value = {"result": "ok"}
        client = TestClient(app)

        predict_response = client.post(
            "/api/v1/models/21/predict",
            json={"inputs": {"text": "hello"}, "options": {"model_version": "42"}},
        )

    assert predict_response.status_code == 200
    predict_data = predict_response.json()
    assert "inference_log_id" in predict_data
    inference_log_id = UUID(predict_data["inference_log_id"])
    assert inference_log_id in in_memory_logger.rows
    assert in_memory_logger.rows[inference_log_id]["api_token_id"] == "key-123"
    assert in_memory_logger.rows[inference_log_id]["model_version"] == "42"
    assert in_memory_logger.rows[inference_log_id]["trace_metadata"]["latency_ms"] >= 0

    outcome_response = client.post(
        "/api/v1/outcomes",
        json={
            "inference_log_id": str(inference_log_id),
            "outcome_score": 0.85,
            "outcome_type": "engagement",
        },
    )
    assert outcome_response.status_code == 200
    assert in_memory_logger.rows[inference_log_id]["outcome_score"] == 0.85
    assert in_memory_logger.rows[inference_log_id]["outcome_type"] == "engagement"


def test_outcome_returns_404_for_unknown_log_id() -> None:
    app = FastAPI()
    app.include_router(outcomes_router)

    in_memory_logger = InMemoryContributorLogger()
    app.dependency_overrides[get_contributor_logger] = lambda: in_memory_logger
    app.dependency_overrides[require_auth] = lambda: {
        "user_id": "user-1",
        "api_key_id": "key-123",
    }
    client = TestClient(app)

    response = client.post(
        "/api/v1/outcomes",
        json={
            "inference_log_id": str(uuid4()),
            "outcome_score": 0.7,
            "outcome_type": "reply_rate",
        },
    )
    assert response.status_code == 404


def test_outcome_returns_403_for_other_token_owner() -> None:
    app = FastAPI()
    app.include_router(outcomes_router)

    in_memory_logger = InMemoryContributorLogger()
    owned_log_id = in_memory_logger.log_inference(
        api_token_id="owner-key",
        model_name="Model A",
        model_version="1",
        input_payload={"x": 1},
        output_payload={"y": 2},
        trace_metadata={"latency_ms": 2},
    )

    app.dependency_overrides[get_contributor_logger] = lambda: in_memory_logger
    app.dependency_overrides[require_auth] = lambda: {
        "user_id": "user-1",
        "api_key_id": "other-key",
    }

    client = TestClient(app)
    response = client.post(
        "/api/v1/outcomes",
        json={
            "inference_log_id": str(owned_log_id),
            "outcome_score": 0.8,
            "outcome_type": "engagement",
        },
    )
    assert response.status_code == 403
