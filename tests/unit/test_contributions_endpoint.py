"""Unit coverage for the contributions endpoint and service."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_contribution_service
from src.api.endpoints import contributions
from src.api.endpoints.model_registry_entries import MODEL_CONFIGS
from src.api.schemas.contribution import ContributionAcceptedResponse, ContributionRequest
from src.api.services.auth_service_notifier import AuthServiceNotifier
from src.api.services.contribution_service import (
    ContributionAcceptance,
    ContributionConflictError,
    ContributionLifecycleRecord,
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
        self.lifecycle_record: ContributionLifecycleRecord | None = ContributionLifecycleRecord(
            submission_id="batch-123",
            state="processed",
            accepted_row_count=2,
            rejected_row_count=0,
            reason=None,
            processing_metadata={"source": "test"},
            training_run_id="train-123",
            evaluation_run_id="eval-123",
            created_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
            updated_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
        )

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

    def get_lifecycle_state(self, submission_id: str) -> ContributionLifecycleRecord | None:
        self.calls.append({"lifecycle_submission_id": submission_id})
        return self.lifecycle_record


class RecordingNotifier:
    """Capture accepted-submission notifications for assertions."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def notify_accepted(
        self,
        *,
        record: StoredContributionRecord,
        auth: dict[str, Any],
        storage_ref: str | None = None,
    ) -> None:
        self.calls.append({"record": record, "auth": auth, "storage_ref": storage_ref})


class RaisingNotifier:
    """Simulate downstream notifier failure."""

    def notify_accepted(
        self,
        *,
        record: StoredContributionRecord,
        auth: dict[str, Any],
        storage_ref: str | None = None,
    ) -> None:
        raise RuntimeError("auth-service unavailable")


VALID_AUTH = {
    "user_id": "11111111-1111-1111-1111-111111111111",
    "api_key_id": "22222222-2222-2222-2222-222222222222",
    "service_id": "svc-1",
}


@pytest.fixture()
def app() -> FastAPI:
    app = FastAPI()
    fake_service = FakeContributionService()
    app.include_router(contributions.router)
    app.include_router(contributions.lifecycle_router)
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
    app.include_router(contributions.lifecycle_router)
    app.dependency_overrides[get_contribution_service] = lambda: FakeContributionService()
    client = TestClient(app)

    response = client.post("/api/v1/models/30/contributions", json={"rows": [{"task_id": "row-1"}]})

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_get_lifecycle_returns_200(client: TestClient, app: FastAPI) -> None:
    response = client.get("/api/v1/contributions/batch-123/lifecycle")

    assert response.status_code == 200
    assert response.json()["submission_id"] == "batch-123"
    assert response.json()["state"] == "processed"
    assert response.json()["metadata"] == {"source": "test"}
    assert app.state.fake_contribution_service.calls[-1] == {"lifecycle_submission_id": "batch-123"}


def test_get_lifecycle_returns_404_when_unknown(client: TestClient, app: FastAPI) -> None:
    app.state.fake_contribution_service.lifecycle_record = None

    response = client.get("/api/v1/contributions/missing-batch/lifecycle")

    assert response.status_code == 404
    assert response.json() == {
        "error": "lifecycle_not_found",
        "submission_id": "missing-batch",
    }


def test_get_lifecycle_requires_auth() -> None:
    app = FastAPI()
    app.include_router(contributions.router)
    app.include_router(contributions.lifecycle_router)
    app.dependency_overrides[get_contribution_service] = lambda: FakeContributionService()
    client = TestClient(app)

    response = client.get("/api/v1/contributions/batch-123/lifecycle")

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


def test_service_notifies_auth_on_new_submission() -> None:
    store = InMemoryContributionStore()
    notifier = RecordingNotifier()
    service = ContributionService(store=store, notifier=notifier)
    payload = ContributionRequest.model_validate(
        {
            "rows": [{"task_id": "row-1"}, {"task_id": "row-2"}],
            "metadata": {"idempotency_key": "batch-123"},
        }
    )

    accepted = service.accept_contribution(
        model_id="30",
        request=payload,
        idempotency_key=None,
        auth=VALID_AUTH,
    )

    assert accepted.status_code == 201
    assert len(notifier.calls) == 1
    call = notifier.calls[0]
    assert call["record"].submission_id == "batch-123"
    assert call["record"].model_id == "30"
    assert call["record"].body_hash
    assert call["record"].idempotency_key == "batch-123"
    assert call["auth"] == VALID_AUTH
    assert call["storage_ref"] is None


def test_service_does_not_notify_auth_on_idempotent_replay() -> None:
    store = InMemoryContributionStore()
    notifier = RecordingNotifier()
    service = ContributionService(store=store, notifier=notifier)
    payload = ContributionRequest.model_validate(
        {
            "rows": [{"task_id": "row-1"}],
            "metadata": {"idempotency_key": "batch-123"},
        }
    )

    first = service.accept_contribution(
        model_id="30",
        request=payload,
        idempotency_key=None,
        auth=VALID_AUTH,
    )
    second = service.accept_contribution(
        model_id="30",
        request=payload,
        idempotency_key=None,
        auth=VALID_AUTH,
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert len(notifier.calls) == 1


def test_service_continues_when_notifier_raises(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("ERROR")
    store = InMemoryContributionStore()
    service = ContributionService(store=store, notifier=RaisingNotifier())
    payload = ContributionRequest.model_validate(
        {
            "rows": [{"task_id": "row-1"}],
            "metadata": {"idempotency_key": "batch-123"},
        }
    )

    accepted = service.accept_contribution(
        model_id="30",
        request=payload,
        idempotency_key=None,
        auth=VALID_AUTH,
    )

    assert accepted.status_code == 201
    assert ("30", "batch-123") in store.records
    assert "Failed to notify auth service for accepted contribution" in caplog.text


def test_notifier_skipped_when_uuid_fields_invalid(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("WARNING")
    notifier = AuthServiceNotifier(
        auth_service_url="https://auth.service.local",
        internal_token="",
        dry_run=True,
    )
    post_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "src.api.services.auth_service_notifier.httpx.post",
        lambda *args, **kwargs: post_calls.append({"args": args, "kwargs": kwargs}),
    )
    record = StoredContributionRecord(
        submission_id="batch-123",
        model_id="30",
        idempotency_key="batch-123",
        body_hash="abc123",
        rows=[{"task_id": "row-1"}],
        metadata={},
        response_payload={"accepted": True},
        created_at="2026-06-04T12:00:00+00:00",
    )

    notifier.notify_accepted(
        record=record,
        auth={"user_id": "not-a-uuid", "api_key_id": "still-not-a-uuid", "service_id": "svc-1"},
    )

    assert not post_calls
    parsed_logs = [json.loads(record.getMessage()) for record in caplog.records]
    assert any(
        item["event"] == "auth_submission_notification_skipped_invalid_auth_context"
        and item["field"] == "user_id"
        for item in parsed_logs
    )
