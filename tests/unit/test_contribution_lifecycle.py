"""Unit tests for contribution lifecycle persistence and transitions."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.models.contribution_lifecycle import ContributionLifecycle
from src.api.schemas.contribution import ContributionRequest
from src.api.services.contribution_service import (
    ContributionLifecycleStateError,
    ContributionService,
    StoredContributionRecord,
)


class InMemoryContributionStore:
    """Small in-memory store for accepted contribution batches."""

    def __init__(self) -> None:
        self.records: dict[tuple[str, str], StoredContributionRecord] = {}

    def get(self, *, model_id: str, submission_id: str) -> StoredContributionRecord | None:
        return self.records.get((model_id, submission_id))

    def create(self, *, record: StoredContributionRecord) -> StoredContributionRecord:
        self.records[(record.model_id, record.submission_id)] = record
        return record


class RecordingNotifier:
    """Capture notifier calls so fail-open behavior can be asserted."""

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


@pytest.fixture()
def lifecycle_session_factory() -> sessionmaker:
    """Return a shared in-memory SQLite session factory with only the lifecycle table."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ContributionLifecycle.__table__.create(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _make_request(*, rows: int = 1, key: str = "batch-123") -> ContributionRequest:
    return ContributionRequest.model_validate(
        {
            "rows": [{"task_id": f"row-{index}"} for index in range(rows)],
            "metadata": {"idempotency_key": key},
        }
    )


def test_acceptance_creates_lifecycle_record(lifecycle_session_factory: sessionmaker) -> None:
    service = ContributionService(
        store=InMemoryContributionStore(),
        lifecycle_session_factory=lifecycle_session_factory,
    )

    accepted = service.accept_contribution(
        model_id="30",
        request=_make_request(rows=2),
        idempotency_key=None,
        auth={"user_id": "user-1", "api_key_id": "key-1", "service_id": "svc-1"},
    )
    lifecycle = service.get_lifecycle_state("batch-123")

    assert accepted.status_code == 201
    assert lifecycle is not None
    assert lifecycle.state == "received"
    assert lifecycle.accepted_row_count == 2
    assert lifecycle.rejected_row_count == 0


def test_advance_lifecycle_transitions_and_run_refs(
    lifecycle_session_factory: sessionmaker,
) -> None:
    service = ContributionService(lifecycle_session_factory=lifecycle_session_factory)
    service.create_lifecycle_record(submission_id="batch-123", accepted_row_count=4)

    service.advance_lifecycle_state(submission_id="batch-123", state="queued")
    service.advance_lifecycle_state(submission_id="batch-123", state="processing")
    updated = service.advance_lifecycle_state(
        submission_id="batch-123",
        state="included_in_training",
        accepted_row_count=4,
        rejected_row_count=1,
        processing_metadata={"dataset_id": "dataset-1"},
        training_run_id="train-1",
        evaluation_run_id="eval-1",
    )

    assert updated.state == "included_in_training"
    assert updated.accepted_row_count == 4
    assert updated.rejected_row_count == 1
    assert updated.processing_metadata == {"dataset_id": "dataset-1"}
    assert updated.training_run_id == "train-1"
    assert updated.evaluation_run_id == "eval-1"


def test_rejection_stores_counts_and_reason(lifecycle_session_factory: sessionmaker) -> None:
    service = ContributionService(lifecycle_session_factory=lifecycle_session_factory)

    rejected = service.advance_lifecycle_state(
        submission_id="batch-rejected",
        state="rejected",
        accepted_row_count=3,
        rejected_row_count=7,
        reason="schema_validation_failed",
    )

    assert rejected.state == "rejected"
    assert rejected.accepted_row_count == 3
    assert rejected.rejected_row_count == 7
    assert rejected.reason == "schema_validation_failed"


def test_invalid_state_raises_and_leaves_row_unchanged(
    lifecycle_session_factory: sessionmaker,
) -> None:
    service = ContributionService(lifecycle_session_factory=lifecycle_session_factory)
    service.create_lifecycle_record(submission_id="batch-123", accepted_row_count=1)

    with pytest.raises(ContributionLifecycleStateError):
        service.advance_lifecycle_state(submission_id="batch-123", state="bad-state")

    lifecycle = service.get_lifecycle_state("batch-123")
    assert lifecycle is not None
    assert lifecycle.state == "received"
    assert lifecycle.accepted_row_count == 1
    assert lifecycle.rejected_row_count == 0


def test_duplicate_transition_is_idempotent_with_absolute_counts(
    lifecycle_session_factory: sessionmaker,
) -> None:
    service = ContributionService(lifecycle_session_factory=lifecycle_session_factory)

    first = service.advance_lifecycle_state(
        submission_id="batch-123",
        state="processed",
        accepted_row_count=8,
        rejected_row_count=2,
    )
    second = service.advance_lifecycle_state(
        submission_id="batch-123",
        state="processed",
        accepted_row_count=8,
        rejected_row_count=2,
    )

    assert first.accepted_row_count == 8
    assert first.rejected_row_count == 2
    assert second.accepted_row_count == 8
    assert second.rejected_row_count == 2


def test_acceptance_without_lifecycle_db_is_fail_open(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    service = ContributionService(store=InMemoryContributionStore())
    monkeypatch.setattr(service, "_resolve_database_url", lambda: None)

    accepted = service.accept_contribution(
        model_id="30",
        request=_make_request(),
        idempotency_key=None,
        auth={"user_id": "user-1", "api_key_id": "key-1", "service_id": "svc-1"},
    )

    assert accepted.status_code == 201
    assert "Lifecycle persistence unavailable during acceptance" in caplog.text


def test_lifecycle_write_exception_is_fail_open_and_notifier_still_runs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("ERROR")
    store = InMemoryContributionStore()
    notifier = RecordingNotifier()

    def broken_session_factory() -> Any:
        raise RuntimeError("db unavailable")

    service = ContributionService(
        store=store,
        notifier=notifier,
        lifecycle_session_factory=broken_session_factory,
    )

    accepted = service.accept_contribution(
        model_id="30",
        request=_make_request(),
        idempotency_key=None,
        auth={"user_id": "user-1", "api_key_id": "key-1", "service_id": "svc-1"},
    )

    assert accepted.status_code == 201
    assert len(notifier.calls) == 1
    assert ("30", "batch-123") in store.records
    assert "Failed to persist contribution lifecycle state during acceptance" in caplog.text
