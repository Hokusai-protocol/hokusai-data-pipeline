"""Unit coverage for the contributions endpoint and service."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_contribution_service
from src.api.endpoints import contributions
from src.api.endpoints.model_registry_entries import MODEL_CONFIGS
from src.api.schemas.contribution import ContributionAcceptedResponse, ContributionRequest
from src.api.services.contribution_service import (
    ContributionAcceptance,
    ContributionConflictError,
    ContributionService,
    StoredContributionRecord,
)
from src.middleware.auth import require_auth


class InMemoryContributionStore:
    """Small in-memory store for service tests."""

    def __init__(self) -> None:
        self.records: dict[tuple[str, str], StoredContributionRecord] = {}

    def get(self, *, model_id: str, submission_id: str) -> StoredContributionRecord | None:
        return self.records.get((model_id, submission_id))

    def create(self, *, record: StoredContributionRecord) -> StoredContributionRecord:
        self.records[(record.model_id, record.submission_id)] = record
        return record


class FakeContributionService:
    """Route test double that captures requests and returns canned responses."""

    def __init__(self) -> None:
        self.max_body_bytes = 512
        self.calls: list[dict[str, Any]] = []

    def accept_contribution(
        self,
        *,
        model_id: str,
        request: ContributionRequest,
        idempotency_key: str | None,
        auth: dict[str, Any],
    ) -> ContributionAcceptance:
        self.calls.append(
            {
                "model_id": model_id,
                "request": request,
                "idempotency_key": idempotency_key,
                "auth": auth,
            }
        )
        return ContributionAcceptance(
            response=ContributionAcceptedResponse(
                accepted=True,
                modelId=model_id,
                submissionId=idempotency_key or "generated-id",
                jobId="job-123",
                jobIds=["job-123"],
                rowsAccepted=len(request.rows),
                submittedRows=len(request.rows),
                tokenReward=0,
                idempotentReplay=False,
            ),
            status_code=201,
        )


@pytest.fixture()
def app() -> FastAPI:
    app = FastAPI()
    fake_service = FakeContributionService()
    app.include_router(contributions.router)
    app.dependency_overrides[require_auth] = lambda: {
        "user_id": "test-user",
        "api_key_id": "test-key",
        "service_id": "test-service",
        "scopes": ["model:write"],
    }
    app.dependency_overrides[get_contribution_service] = lambda: fake_service
    app.state.fake_contribution_service = fake_service
    return app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def restore_registry() -> None:
    original_entries = dict(MODEL_CONFIGS)
    yield
    MODEL_CONFIGS.clear()
    MODEL_CONFIGS.update(original_entries)


def test_valid_wavemill_payload_returns_accepted_response(client: TestClient, app: FastAPI) -> None:
    response = client.post(
        "/api/v1/models/30/contributions",
        headers={"Idempotency-Key": "batch-123"},
        json={
            "rows": [{"task_id": "row-1"}, {"task_id": "row-2"}],
            "metadata": {"idempotency_key": "metadata-key"},
        },
    )

    assert response.status_code == 201
    assert response.json()["submittedRows"] == 2
    assert response.json()["submissionId"] == "batch-123"
    assert response.json()["jobIds"] == ["job-123"]
    call = app.state.fake_contribution_service.calls[0]
    assert call["model_id"] == "30"
    assert call["idempotency_key"] == "batch-123"


def test_valid_site_payload_returns_accepted_response(client: TestClient) -> None:
    response = client.post(
        "/api/v1/models/30/contributions",
        json={
            "modelId": "30",
            "benchmarkSpecId": None,
            "rows": [{"task_id": "row-1"}],
            "schemaVersion": None,
            "templateId": None,
        },
    )

    assert response.status_code == 201
    assert response.json()["modelId"] == "30"
    assert response.json()["rowsAccepted"] == 1


def test_mismatched_site_model_id_returns_400(client: TestClient) -> None:
    client.app.dependency_overrides[get_contribution_service] = lambda: ContributionService(
        store=InMemoryContributionStore()
    )
    response = client.post(
        "/api/v1/models/30/contributions",
        json={"modelId": "31", "rows": [{"task_id": "row-1"}]},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "model_id_mismatch"


def test_missing_rows_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/models/30/contributions", json={"metadata": {}})

    assert response.status_code == 422


def test_empty_rows_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/models/30/contributions", json={"rows": []})

    assert response.status_code == 422


def test_non_object_row_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/models/30/contributions", json={"rows": ["not-an-object"]})

    assert response.status_code == 422


def test_unknown_model_id_returns_structured_404(client: TestClient) -> None:
    client.app.dependency_overrides[get_contribution_service] = lambda: ContributionService(
        store=InMemoryContributionStore()
    )
    response = client.post(
        "/api/v1/models/999/contributions",
        json={"rows": [{"task_id": "row-1"}]},
    )

    assert response.status_code == 404
    assert response.json() == {"error": "model_not_found", "model_id": "999"}


def test_missing_auth_returns_401() -> None:
    app = FastAPI()
    app.include_router(contributions.router)
    app.dependency_overrides[get_contribution_service] = lambda: FakeContributionService()
    client = TestClient(app)

    response = client.post("/api/v1/models/30/contributions", json={"rows": [{"task_id": "row-1"}]})

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_oversized_content_length_returns_413(client: TestClient) -> None:
    response = client.post(
        "/api/v1/models/30/contributions",
        headers={"Content-Length": "9999"},
        json={"rows": [{"task_id": "row-1"}]},
    )

    assert response.status_code == 413
    assert response.json()["error"] == "payload_too_large"


def test_service_returns_idempotent_replay_for_same_key_and_body() -> None:
    store = InMemoryContributionStore()
    service = ContributionService(store=store)
    payload = ContributionRequest.model_validate(
        {
            "rows": [{"task_id": "row-1"}],
            "metadata": {"idempotency_key": "batch-123"},
        }
    )
    auth = {"user_id": "user-1", "api_key_id": "key-1", "service_id": "svc-1"}

    first = service.accept_contribution(
        model_id="30",
        request=payload,
        idempotency_key=None,
        auth=auth,
    )
    second = service.accept_contribution(
        model_id="30",
        request=payload,
        idempotency_key=None,
        auth=auth,
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.response.submission_id == "batch-123"
    assert len(store.records) == 1


def test_service_rejects_duplicate_key_with_different_body() -> None:
    store = InMemoryContributionStore()
    service = ContributionService(store=store)
    auth = {"user_id": "user-1", "api_key_id": "key-1", "service_id": "svc-1"}
    first = ContributionRequest.model_validate(
        {
            "rows": [{"task_id": "row-1"}],
            "metadata": {"idempotency_key": "batch-123"},
        }
    )
    second = ContributionRequest.model_validate(
        {
            "rows": [{"task_id": "row-2"}],
            "metadata": {"idempotency_key": "batch-123"},
        }
    )

    service.accept_contribution(model_id="30", request=first, idempotency_key=None, auth=auth)
    with pytest.raises(ContributionConflictError):
        service.accept_contribution(model_id="30", request=second, idempotency_key=None, auth=auth)


def test_service_supports_registered_models_added_during_tests() -> None:
    MODEL_CONFIGS["31"] = replace(
        MODEL_CONFIGS["30"],
        name="Alternate Router",
    )
    service = ContributionService(store=InMemoryContributionStore())

    response = service.accept_contribution(
        model_id="31",
        request=ContributionRequest.model_validate({"rows": [{"task_id": "row-1"}]}),
        idempotency_key="batch-123",
        auth={"user_id": "user-1"},
    )

    assert response.response.model_id == "31"
    assert response.status_code == 201
