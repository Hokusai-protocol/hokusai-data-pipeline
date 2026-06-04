"""Unit tests for auth-service contribution acceptance notifications."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import Mock

import httpx
import pytest

from src.api.schemas.contribution import LifecycleReasonCode, LifecycleUpdatePayload, RowCounts
from src.api.services.auth_service_notifier import AuthServiceNotifier
from src.api.services.contribution_service import StoredContributionRecord


def _record() -> StoredContributionRecord:
    return StoredContributionRecord(
        submission_id="batch-123",
        model_id="30",
        idempotency_key="idem-123",
        body_hash="abc123",
        rows=[{"task_id": "row-1"}, {"task_id": "row-2"}],
        metadata={},
        response_payload={"accepted": True},
        created_at="2026-06-04T12:00:00+00:00",
    )


def _auth() -> dict[str, str]:
    return {
        "user_id": "11111111-1111-1111-1111-111111111111",
        "api_key_id": "22222222-2222-2222-2222-222222222222",
        "service_id": "svc-1",
    }


def test_notifier_posts_payload_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    notifier = AuthServiceNotifier(
        auth_service_url="https://auth.service.local",
        internal_token="secret-token",
        dry_run=False,
    )
    response = Mock(status_code=201, text="")
    post_mock = Mock(return_value=response)
    monkeypatch.setattr("src.api.services.auth_service_notifier.httpx.post", post_mock)

    notifier.notify_accepted(record=_record(), auth=_auth(), storage_ref="s3://bucket/key")

    assert post_mock.call_count == 1
    call_kwargs = post_mock.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer secret-token"
    assert call_kwargs["headers"]["Idempotency-Key"] == "idem-123"
    assert call_kwargs["json"] == {
        "submissionId": "batch-123",
        "jobId": "batch-123",
        "modelId": "30",
        "rowsAccepted": 2,
        "idempotencyKey": "idem-123",
        "body_hash": "abc123",
        "storageRef": "s3://bucket/key",
        "timestamp": "2026-06-04T12:00:00+00:00",
        "source": "hokusai_data_pipeline",
        "endpoint": "/api/v1/models/30/contributions",
        "user_id": "11111111-1111-1111-1111-111111111111",
        "api_key_id": "22222222-2222-2222-2222-222222222222",
        "service_id": "svc-1",
    }


def test_notifier_treats_conflict_as_non_retryable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("WARNING")
    notifier = AuthServiceNotifier(
        auth_service_url="https://auth.service.local",
        internal_token="secret-token",
        dry_run=False,
    )
    response = Mock(status_code=409, text="conflict")
    post_mock = Mock(return_value=response)
    monkeypatch.setattr("src.api.services.auth_service_notifier.httpx.post", post_mock)

    notifier.notify_accepted(record=_record(), auth=_auth())

    assert post_mock.call_count == 1
    logs = [json.loads(record.getMessage()) for record in caplog.records]
    assert any(item["event"] == "auth_submission_notification_conflict" for item in logs)


def test_notifier_retries_retryable_failures(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("WARNING")
    notifier = AuthServiceNotifier(
        auth_service_url="https://auth.service.local",
        internal_token="secret-token",
        dry_run=False,
        retry_attempts=2,
    )
    post_mock = Mock(side_effect=httpx.TimeoutException("request timed out"))
    monkeypatch.setattr("src.api.services.auth_service_notifier.httpx.post", post_mock)

    notifier.notify_accepted(record=_record(), auth=_auth())

    assert post_mock.call_count == 2
    logs = [json.loads(record.getMessage()) for record in caplog.records]
    retry_logs = [
        item for item in logs if item["event"] == "auth_submission_notification_request_error"
    ]
    assert len(retry_logs) == 2
    assert any(item["event"] == "auth_submission_notification_retry_exhausted" for item in logs)


def test_notifier_dry_run_skips_http_call(monkeypatch: pytest.MonkeyPatch) -> None:
    notifier = AuthServiceNotifier(
        auth_service_url="https://auth.service.local",
        internal_token="",
        dry_run=True,
    )
    post_mock = Mock()
    monkeypatch.setattr("src.api.services.auth_service_notifier.httpx.post", post_mock)

    notifier.notify_accepted(record=_record(), auth=_auth())

    post_mock.assert_not_called()


def test_from_env_dry_run_when_flag_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOKUSAI_AUTH_SERVICE_URL", "https://auth.example.com")
    monkeypatch.setenv("HOKUSAI_AUTH_INTERNAL_TOKEN", "secret")
    monkeypatch.setenv("CONTRIBUTION_AUTH_CALLBACK_ENABLED", "false")

    notifier = AuthServiceNotifier.from_env()

    assert notifier.dry_run is True


def test_from_env_not_dry_run_when_flag_enabled_with_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOKUSAI_AUTH_SERVICE_URL", "https://auth.example.com")
    monkeypatch.setenv("HOKUSAI_AUTH_INTERNAL_TOKEN", "secret")
    monkeypatch.setenv("CONTRIBUTION_AUTH_CALLBACK_ENABLED", "true")

    notifier = AuthServiceNotifier.from_env()

    assert notifier.dry_run is False


def test_notify_lifecycle_update_returns_true_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notifier = AuthServiceNotifier(
        auth_service_url="https://auth.service.local",
        internal_token="secret-token",
        dry_run=False,
    )
    response = Mock(status_code=200, text="")
    post_mock = Mock(return_value=response)
    monkeypatch.setattr("src.api.services.auth_service_notifier.httpx.post", post_mock)

    delivered, error = notifier.notify_lifecycle_update(_lifecycle_payload())

    assert delivered is True
    assert error is None
    assert post_mock.call_args.kwargs["headers"]["Idempotency-Key"] == "batch-123:processed:v1"


def test_notify_lifecycle_update_returns_false_on_retryable_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notifier = AuthServiceNotifier(
        auth_service_url="https://auth.service.local",
        internal_token="secret-token",
        dry_run=False,
        retry_attempts=2,
    )
    response = Mock(status_code=503, text="downstream unavailable")
    post_mock = Mock(return_value=response)
    monkeypatch.setattr("src.api.services.auth_service_notifier.httpx.post", post_mock)

    delivered, error = notifier.notify_lifecycle_update(_lifecycle_payload())

    assert delivered is False
    assert error == "503: downstream unavailable"
    assert post_mock.call_count == 2


def test_notify_lifecycle_update_dry_run_skips_http_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notifier = AuthServiceNotifier(
        auth_service_url="https://auth.service.local",
        internal_token="",
        dry_run=True,
    )
    post_mock = Mock()
    monkeypatch.setattr("src.api.services.auth_service_notifier.httpx.post", post_mock)

    delivered, error = notifier.notify_lifecycle_update(_lifecycle_payload())

    assert delivered is True
    assert error is None
    post_mock.assert_not_called()


@pytest.mark.parametrize(
    ("cause", "expected"),
    [
        ("schema_validation_failed", LifecycleReasonCode.SCHEMA_VALIDATION_FAILED),
        ("duplicate_submission", LifecycleReasonCode.DUPLICATE_SUBMISSION),
        ("insufficient_quality", LifecycleReasonCode.INSUFFICIENT_QUALITY),
        ("excluded_from_training", LifecycleReasonCode.EXCLUDED_FROM_TRAINING),
        ("something_else", LifecycleReasonCode.PROCESSING_ERROR),
        (None, LifecycleReasonCode.PROCESSING_ERROR),
    ],
)
def test_map_reason_code(cause: str | None, expected: LifecycleReasonCode) -> None:
    assert AuthServiceNotifier._map_reason_code(cause) == expected


def _lifecycle_payload() -> LifecycleUpdatePayload:
    return LifecycleUpdatePayload(
        submission_id="batch-123",
        status="processed",
        row_counts=RowCounts(accepted=2, rejected=1, total=3),
        dataset_version="dataset-v1",
        training_run_id="train-123",
        evaluation_run_id="eval-123",
        estimated_reward_at=datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc),
        reason_code=LifecycleReasonCode.PROCESSING_ERROR,
    )
