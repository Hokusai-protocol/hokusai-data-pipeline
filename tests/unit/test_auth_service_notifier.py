"""Unit tests for auth-service contribution acceptance notifications."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import Mock

import httpx
import pytest

from src.api.schemas.contribution import LifecycleReasonCode, LifecycleUpdatePayload, RowCounts
from src.api.schemas.token_mint import TokenMintResult
from src.api.services.auth_service_notifier import AuthServiceNotifier, WalletResolution
from src.api.services.contribution_service import StoredContributionRecord
from src.events.schemas import MintRequest, MintRequestContributor, MintRequestEvaluation


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


def _mint_request() -> MintRequest:
    return MintRequest(
        message_id="mint-msg-1",
        timestamp="2026-06-04T12:00:00+00:00",
        model_id="30",
        model_id_uint="99001",
        eval_id="eval-123",
        benchmark_spec_id="spec-test-v1",
        dataset_hash="0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        attestation_hash="0x" + "a" * 64,
        idempotency_key="0x" + "b" * 64,
        total_samples=3,
        evaluation=MintRequestEvaluation(
            metric_name="accuracy",
            metric_family="proportion",
            baseline_score_bps=7000,
            new_score_bps=8000,
            max_cost_usd_micro=100,
            actual_cost_usd_micro=50,
        ),
        contributors=[
            MintRequestContributor(
                wallet_address="0x742d35cc6634c0532925a3b844bc9e7595f62341",
                weight_bps=7000,
                submission_id="sub-1",
                contribution_batch_id="batch-1",
            ),
            MintRequestContributor(
                wallet_address="0x6c3e007f281f6948b37c511a11e43c8026d2f069",
                weight_bps=3000,
                submission_id="sub-2",
            ),
        ],
    )


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
    # HOK-2256: must hit the deployed /api/v1 route (bare /internal/... 404s).
    assert post_mock.call_args.args[0] == (
        "https://auth.service.local/api/v1/internal/data-submissions/accepted"
    )
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


def test_notify_reward_entitlement_posts_payload_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notifier = AuthServiceNotifier(
        auth_service_url="https://auth.service.local",
        internal_token="secret-token",
        dry_run=False,
    )
    response = Mock(status_code=201, text="")
    post_mock = Mock(return_value=response)
    monkeypatch.setattr("src.api.services.auth_service_notifier.httpx.post", post_mock)

    delivered, error = notifier.notify_reward_entitlement(
        mint_request=_mint_request(),
        status="pending",
    )

    assert delivered is True
    assert error is None
    call_kwargs = post_mock.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer secret-token"
    assert (
        call_kwargs["headers"]["Idempotency-Key"]
        == f"{_mint_request().idempotency_key}:reward_entitlement:pending"
    )
    assert call_kwargs["json"]["contributors"][0]["submissionId"] == "sub-1"
    assert call_kwargs["json"]["contributors"][0]["weightBps"] == 7000
    assert call_kwargs["json"]["contributors"][1]["submissionId"] == "sub-2"


def test_notify_reward_entitlement_dry_run_skips_http_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notifier = AuthServiceNotifier(
        auth_service_url="https://auth.service.local",
        internal_token="",
        dry_run=True,
    )
    post_mock = Mock()
    monkeypatch.setattr("src.api.services.auth_service_notifier.httpx.post", post_mock)

    delivered, error = notifier.notify_reward_entitlement(
        mint_request=_mint_request(),
        status="pending",
    )

    assert delivered is True
    assert error is None
    post_mock.assert_not_called()


def test_notify_reward_entitlement_retries_and_returns_false(
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

    delivered, error = notifier.notify_reward_entitlement(
        mint_request=_mint_request(),
        status="pending",
    )

    assert delivered is False
    assert error == "503: downstream unavailable"
    assert post_mock.call_count == 2


def test_notify_reward_entitlement_includes_claimable_vesting(
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

    delivered, error = notifier.notify_reward_entitlement(
        mint_request=_mint_request(),
        status="claimable",
        mint_result=TokenMintResult.model_validate(
            {
                "status": "success",
                "audit_ref": "audit-1",
                "timestamp": datetime.now(timezone.utc),
                "vesting": {
                    "claimable_amount": "25",
                    "vault_address": "0xvault",
                },
            }
        ),
    )

    assert delivered is True
    assert error is None
    assert post_mock.call_args.kwargs["json"]["vesting"]["claimable_amount"] == "25"


def _notifier() -> AuthServiceNotifier:
    return AuthServiceNotifier(
        auth_service_url="https://auth.service.local",
        internal_token="secret-token",
        dry_run=False,
    )


def test_resolve_wallet_verified_200(monkeypatch: pytest.MonkeyPatch) -> None:
    get_mock = Mock(
        return_value=Mock(
            status_code=200,
            json=Mock(
                return_value={
                    "wallet_address": "0xABC",
                    "verified_at": "2026-06-17T00:00:00Z",
                    "has_verified_wallet": True,
                }
            ),
        )
    )
    monkeypatch.setattr("src.api.services.auth_service_notifier.httpx.get", get_mock)

    result = _notifier().resolve_wallet(user_id="11111111-1111-1111-1111-111111111111")

    assert result == WalletResolution(
        resolved=True, has_verified_wallet=True, wallet_address="0xABC"
    )
    # user_id is a PATH param under the required /api/v1 prefix
    assert get_mock.call_args.args[0] == (
        "https://auth.service.local/api/v1/internal/users/"
        "11111111-1111-1111-1111-111111111111/wallet"
    )
    assert get_mock.call_args.kwargs["headers"]["Authorization"] == "Bearer secret-token"


def test_resolve_wallet_unverified_200_routes_to_escrow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_mock = Mock(
        return_value=Mock(
            status_code=200,
            json=Mock(
                return_value={
                    "wallet_address": None,
                    "verified_at": None,
                    "has_verified_wallet": False,
                }
            ),
        )
    )
    monkeypatch.setattr("src.api.services.auth_service_notifier.httpx.get", get_mock)

    result = _notifier().resolve_wallet(user_id="11111111-1111-1111-1111-111111111111")

    # definitive "no verified wallet" -> escrow path (HOK-2246), not an error/drop
    assert result.resolved is True
    assert result.has_verified_wallet is False
    assert result.wallet_address is None


def test_resolve_wallet_unresolved_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    get_mock = Mock(return_value=Mock(status_code=404, text="missing"))
    monkeypatch.setattr("src.api.services.auth_service_notifier.httpx.get", get_mock)

    result = _notifier().resolve_wallet(user_id="11111111-1111-1111-1111-111111111111")

    assert result == WalletResolution(
        resolved=False, has_verified_wallet=False, wallet_address=None
    )
    assert get_mock.call_count == 1


def test_resolve_wallet_unresolved_on_403(monkeypatch: pytest.MonkeyPatch) -> None:
    get_mock = Mock(return_value=Mock(status_code=403, text="forbidden"))
    monkeypatch.setattr("src.api.services.auth_service_notifier.httpx.get", get_mock)

    result = _notifier().resolve_wallet(user_id="11111111-1111-1111-1111-111111111111")

    assert result.resolved is False
    assert get_mock.call_count == 1


def test_resolve_wallet_dry_run_skips_http(monkeypatch: pytest.MonkeyPatch) -> None:
    notifier = AuthServiceNotifier(
        auth_service_url="https://auth.service.local",
        internal_token="secret-token",
        dry_run=True,
    )
    get_mock = Mock()
    monkeypatch.setattr("src.api.services.auth_service_notifier.httpx.get", get_mock)

    result = notifier.resolve_wallet(user_id="11111111-1111-1111-1111-111111111111")

    assert result.resolved is False
    assert get_mock.call_count == 0


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
