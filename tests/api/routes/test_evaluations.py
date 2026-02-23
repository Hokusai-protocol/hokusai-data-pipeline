"""Tests for evaluation API routes."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_evaluation_service
from src.api.routes.evaluations import router
from src.api.schemas.evaluations import (
    EvaluationJobStatus,
    EvaluationManifestResponse,
    EvaluationResponse,
    EvaluationStatusResponse,
)
from src.middleware.auth import require_auth


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _request_body() -> dict:
    return {
        "config": {
            "eval_type": "openai",
            "dataset_reference": "datasets/bench-v1",
            "parameters": {"dataset_size": 10, "max_tokens": 1000},
        }
    }


def test_trigger_evaluation_returns_202_and_dispatches_background_task():
    app = _build_app()
    service = Mock()
    job_id = uuid4()
    created_at = datetime.now(timezone.utc)
    service.create_evaluation.return_value = EvaluationResponse(
        job_id=job_id,
        status=EvaluationJobStatus.queued,
        estimated_cost=0.02,
        queue_position=1,
        created_at=created_at,
    )

    async def mock_auth():
        return {"user_id": "test-user"}

    app.dependency_overrides[require_auth] = mock_auth
    app.dependency_overrides[get_evaluation_service] = lambda: service

    client = TestClient(app)
    response = client.post(
        f"/api/v1/models/{uuid4()}/evaluate",
        json=_request_body(),
        headers={"Idempotency-Key": "route-key"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_id"] == str(job_id)
    service.create_evaluation.assert_called_once()
    service.execute_evaluation_job.assert_called_once_with(str(job_id))


def test_trigger_evaluation_requires_authentication():
    client = TestClient(_build_app())
    response = client.post(
        f"/api/v1/models/{uuid4()}/evaluate",
        json=_request_body(),
        headers={"Idempotency-Key": "route-key"},
    )

    assert response.status_code == 401


def test_get_status_endpoint():
    app = _build_app()
    service = Mock()
    job_id = uuid4()
    service.get_status.return_value = EvaluationStatusResponse(
        job_id=job_id,
        status=EvaluationJobStatus.running,
        progress_percentage=55.0,
        queue_position=None,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        error_details=None,
    )

    async def mock_auth():
        return {"user_id": "test-user"}

    app.dependency_overrides[require_auth] = mock_auth
    app.dependency_overrides[get_evaluation_service] = lambda: service

    client = TestClient(app)
    response = client.get(f"/api/v1/evaluations/{job_id}/status")

    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_get_manifest_endpoint():
    app = _build_app()
    service = Mock()
    job_id = uuid4()
    now = datetime.now(timezone.utc)
    service.get_manifest.return_value = EvaluationManifestResponse(
        job_id=job_id,
        model_id="my-model",
        eval_type="openai",
        results_summary={"status": "completed"},
        metrics={"accuracy": 0.9},
        artifact_urls=["s3://bucket/path"],
        created_at=now,
        completed_at=now,
    )

    async def mock_auth():
        return {"user_id": "test-user"}

    app.dependency_overrides[require_auth] = mock_auth
    app.dependency_overrides[get_evaluation_service] = lambda: service

    client = TestClient(app)
    response = client.get(f"/api/v1/evaluations/{job_id}/manifest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == str(job_id)
    assert payload["model_id"] == "my-model"


def test_trigger_evaluation_requires_idempotency_key_header():
    app = _build_app()

    async def mock_auth():
        return {"user_id": "test-user"}

    app.dependency_overrides[require_auth] = mock_auth
    app.dependency_overrides[get_evaluation_service] = lambda: Mock()

    client = TestClient(app)
    response = client.post(
        f"/api/v1/models/{uuid4()}/evaluate",
        json=_request_body(),
    )

    assert response.status_code == 422
