"""Unit tests for auth-service lifecycle notifications and retries."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.models.contribution_lifecycle import ContributionLifecycle
from src.api.schemas.contribution import LifecycleReasonCode, LifecycleUpdatePayload
from src.api.services.contribution_service import ContributionService


class RecordingLifecycleNotifier:
    """Capture lifecycle notifications and optionally simulate failures."""

    def __init__(
        self,
        *,
        results: list[tuple[bool, str | None]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[LifecycleUpdatePayload] = []
        self.results = list(results or [(True, None)])
        self.error = error

    @staticmethod
    def _map_reason_code(cause: str | None) -> LifecycleReasonCode:
        mapping = {
            "schema_validation_failed": LifecycleReasonCode.SCHEMA_VALIDATION_FAILED,
            "duplicate_submission": LifecycleReasonCode.DUPLICATE_SUBMISSION,
            "insufficient_quality": LifecycleReasonCode.INSUFFICIENT_QUALITY,
            "excluded_from_training": LifecycleReasonCode.EXCLUDED_FROM_TRAINING,
        }
        return mapping.get((cause or "").strip().lower(), LifecycleReasonCode.PROCESSING_ERROR)

    def notify_lifecycle_update(
        self,
        payload: LifecycleUpdatePayload,
    ) -> tuple[bool, str | None]:
        self.calls.append(payload)
        if self.error is not None:
            raise self.error
        if self.results:
            return self.results.pop(0)
        return True, None


@pytest.fixture()
def lifecycle_session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ContributionLifecycle.__table__.create(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_processed_state_triggers_delivery_and_persists_callback_status(
    lifecycle_session_factory: sessionmaker,
) -> None:
    notifier = RecordingLifecycleNotifier()
    service = ContributionService(
        lifecycle_session_factory=lifecycle_session_factory,
        notifier=notifier,
    )
    service.create_lifecycle_record(submission_id="batch-123", accepted_row_count=4)

    updated = service.advance_lifecycle_state(
        submission_id="batch-123",
        state="processed",
        accepted_row_count=3,
        rejected_row_count=1,
        processing_metadata={"source": "worker"},
        dataset_version="dataset-v7",
        training_run_id="train-123",
        evaluation_run_id="eval-123",
        estimated_reward_at=datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc),
    )

    assert updated.state == "processed"
    assert len(notifier.calls) == 1
    payload = notifier.calls[0]
    assert payload.row_counts.accepted == 3
    assert payload.row_counts.rejected == 1
    assert payload.row_counts.total == 4
    assert payload.dataset_version == "dataset-v7"
    assert payload.training_run_id == "train-123"
    assert payload.event_version == "v1"
    assert payload.estimated_reward_at == datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)

    row = _fetch_row(lifecycle_session_factory, "batch-123")
    assert row.callback_status == "delivered"
    assert row.callback_attempts == 1
    assert row.callback_last_error is None


def test_failed_notifier_marks_row_failed_without_raising(
    lifecycle_session_factory: sessionmaker,
) -> None:
    notifier = RecordingLifecycleNotifier(results=[(False, "503: unavailable")])
    service = ContributionService(
        lifecycle_session_factory=lifecycle_session_factory,
        notifier=notifier,
    )

    result = service.advance_lifecycle_state(
        submission_id="batch-failed",
        state="rejected",
        accepted_row_count=1,
        rejected_row_count=2,
        reason="schema_validation_failed",
    )

    assert result.state == "rejected"
    row = _fetch_row(lifecycle_session_factory, "batch-failed")
    assert row.callback_status == "failed"
    assert row.callback_attempts == 1
    assert row.callback_last_error == "503: unavailable"


def test_non_notifiable_states_do_not_invoke_notifier(
    lifecycle_session_factory: sessionmaker,
) -> None:
    notifier = RecordingLifecycleNotifier()
    service = ContributionService(
        lifecycle_session_factory=lifecycle_session_factory,
        notifier=notifier,
    )

    service.advance_lifecycle_state(submission_id="batch-queued", state="queued")
    service.advance_lifecycle_state(submission_id="batch-processing", state="processing")

    assert notifier.calls == []


def test_retry_failed_callbacks_delivers_and_skips_rows_at_max_attempts(
    lifecycle_session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIFECYCLE_CALLBACK_MAX_ATTEMPTS", "3")
    notifier = RecordingLifecycleNotifier(results=[(True, None)])
    service = ContributionService(
        lifecycle_session_factory=lifecycle_session_factory,
        notifier=notifier,
    )
    service.advance_lifecycle_state(
        submission_id="retry-me",
        state="excluded",
        accepted_row_count=2,
        rejected_row_count=0,
        reason="excluded_from_training",
    )
    service.advance_lifecycle_state(
        submission_id="skip-me",
        state="processed",
        accepted_row_count=2,
        rejected_row_count=0,
    )

    _update_callback_state(
        lifecycle_session_factory,
        "retry-me",
        callback_status="failed",
        callback_attempts=1,
        callback_last_error="503: unavailable",
    )
    _update_callback_state(
        lifecycle_session_factory,
        "skip-me",
        callback_status="failed",
        callback_attempts=3,
        callback_last_error="503: unavailable",
    )
    notifier.calls.clear()

    delivered = service.retry_failed_callbacks(limit=10)

    assert delivered == 1
    assert [payload.submission_id for payload in notifier.calls] == ["retry-me"]
    assert _fetch_row(lifecycle_session_factory, "retry-me").callback_status == "delivered"
    assert _fetch_row(lifecycle_session_factory, "skip-me").callback_status == "failed"


def _fetch_row(
    lifecycle_session_factory: sessionmaker,
    submission_id: str,
) -> ContributionLifecycle:
    session = lifecycle_session_factory()
    try:
        return (
            session.query(ContributionLifecycle)
            .filter(ContributionLifecycle.submission_id == submission_id)
            .one()
        )
    finally:
        session.close()


def _update_callback_state(
    lifecycle_session_factory: sessionmaker,
    submission_id: str,
    **updates: Any,
) -> None:
    session = lifecycle_session_factory()
    try:
        row = (
            session.query(ContributionLifecycle)
            .filter(ContributionLifecycle.submission_id == submission_id)
            .one()
        )
        for field, value in updates.items():
            setattr(row, field, value)
        session.commit()
    finally:
        session.close()
