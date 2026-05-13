"""Unit tests for DeltaOne -> token mint orchestration."""

from __future__ import annotations

# Auth-hook note: this suite uses fake MLflow clients and patched webhook/mint
# calls only; no live MLflow requests are made.
# Production MLflow auth relies on Authorization / MLFLOW_TRACKING_TOKEN env wiring.
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import fakeredis
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from src.api.schemas.token_mint import TokenMintResult
from src.evaluation.deltaone_evaluator import DeltaOneDecision
from src.evaluation.deltaone_mint_orchestrator import DeltaOneMintOrchestrator
from src.events.publishers.mint_request_publisher import QUEUE_NAME, MintRequestPublisher

_CONTRIBUTORS_TAG = json.dumps(
    [{"wallet_address": "0x742d35cc6634c0532925a3b844bc9e7595f62341", "weight_bps": 10000}]
)


class _FakeMlflowClient:
    def __init__(
        self,
        run_metrics: dict[str, float],
        initial_tags: dict[str, str] | None = None,
    ) -> None:
        self._run_metrics = run_metrics
        self.tags = dict(initial_tags or {})

    def get_run(self, _run_id: str):
        return SimpleNamespace(
            data=SimpleNamespace(
                metrics=self._run_metrics,
                tags=self.tags,
            )
        )

    def set_tag(self, _run_id: str, key: str, value: str) -> None:
        self.tags[key] = value


def _accepted_decision() -> DeltaOneDecision:
    return DeltaOneDecision(
        accepted=True,
        reason="accepted",
        run_id="run-candidate",
        baseline_run_id="run-baseline",
        model_id="model-a",
        dataset_hash="sha256:" + "a" * 64,
        metric_name="accuracy",
        delta_percentage_points=1.5,
        ci95_low_percentage_points=0.9,
        ci95_high_percentage_points=2.1,
        n_current=1000,
        n_baseline=1000,
        evaluated_at=datetime.now(timezone.utc),
    )


def _default_tags() -> dict[str, str]:
    return {
        "hokusai.eval_id": "eval-123",
        "hokusai.benchmark_spec_id": "spec-123",
        "hokusai.model_id_uint": "123",
        "hokusai.contributors": _CONTRIBUTORS_TAG,
    }


def test_acceptance_publish_success_advances_canonical_score(monkeypatch) -> None:
    decision = _accepted_decision()
    evaluator = Mock()
    evaluator.evaluate.return_value = decision
    evaluator.delta_threshold_pp = 1.0

    mint_hook = Mock()
    mint_hook.mint.return_value = TokenMintResult(
        status="success",
        audit_ref="audit-1",
        timestamp=datetime.now(timezone.utc),
    )

    redis_client = fakeredis.FakeRedis(decode_responses=True)
    client = _FakeMlflowClient(run_metrics={"accuracy": 0.92}, initial_tags=_default_tags())
    dispatch_mock = Mock(return_value=[])
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        dispatch_mock,
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=MintRequestPublisher(redis_client=redis_client),
    )

    outcome = orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert outcome.status == "success"
    assert outcome.canonical_score_advanced is True
    assert redis_client.llen(QUEUE_NAME) == 1
    assert client.tags["hokusai.canonical_score"] == "0.92"
    assert client.tags["hokusai.canonical_score_run_id"] == "run-candidate"
    assert client.tags["hokusai.mint.status"] == "published"
    assert client.tags["hokusai.mint.legacy_status"] == "success"
    mint_hook.mint.assert_called_once()
    assert (
        mint_hook.mint.call_args.kwargs["idempotency_key"]
        == outcome.acceptance_event.idempotency_key
    )
    assert dispatch_mock.call_count == 2
    assert dispatch_mock.call_args_list[0].kwargs["event_type"] == "deltaone.achieved"
    assert dispatch_mock.call_args_list[1].kwargs["event_type"] == "deltaone.minted"


def test_publish_failure_does_not_advance_canonical_score(monkeypatch) -> None:
    decision = _accepted_decision()
    evaluator = Mock()
    evaluator.evaluate.return_value = decision
    evaluator.delta_threshold_pp = 1.0

    mint_hook = Mock()
    broken_redis = Mock()
    broken_redis.lpush.side_effect = RedisConnectionError("redis unavailable")

    client = _FakeMlflowClient(run_metrics={"accuracy": 0.92}, initial_tags=_default_tags())
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(return_value=[]),
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=MintRequestPublisher(redis_client=broken_redis),
    )

    with pytest.raises(RedisConnectionError):
        orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert "hokusai.canonical_score" not in client.tags
    assert client.tags["hokusai.mint.status"] == "requested"
    mint_hook.mint.assert_not_called()


def test_secondary_dry_run_does_not_block_primary_success(monkeypatch) -> None:
    decision = _accepted_decision()
    evaluator = Mock()
    evaluator.evaluate.return_value = decision
    evaluator.delta_threshold_pp = 1.0

    mint_hook = Mock()
    mint_hook.mint.return_value = TokenMintResult(
        status="dry_run",
        audit_ref="audit-dry-run",
        timestamp=datetime.now(timezone.utc),
    )

    redis_client = fakeredis.FakeRedis(decode_responses=True)
    client = _FakeMlflowClient(run_metrics={"accuracy": 0.92}, initial_tags=_default_tags())
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(return_value=[]),
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=MintRequestPublisher(redis_client=redis_client),
    )

    outcome = orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert outcome.status == "success"
    assert outcome.canonical_score_advanced is True
    assert outcome.mint_result is not None
    assert outcome.mint_result.status == "dry_run"
    assert redis_client.llen(QUEUE_NAME) == 1
    assert client.tags["hokusai.mint.status"] == "published"
    assert client.tags["hokusai.mint.legacy_status"] == "dry_run"


def test_secondary_failure_is_recorded_without_rolling_back_publish(monkeypatch) -> None:
    decision = _accepted_decision()
    evaluator = Mock()
    evaluator.evaluate.return_value = decision
    evaluator.delta_threshold_pp = 1.0

    mint_hook = Mock()
    mint_hook.mint.side_effect = RuntimeError("legacy hook exploded")

    redis_client = fakeredis.FakeRedis(decode_responses=True)
    client = _FakeMlflowClient(run_metrics={"accuracy": 0.92}, initial_tags=_default_tags())
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(return_value=[]),
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=MintRequestPublisher(redis_client=redis_client),
    )

    outcome = orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert outcome.status == "success"
    assert outcome.canonical_score_advanced is True
    assert outcome.mint_result is not None
    assert outcome.mint_result.status == "failed"
    assert outcome.mint_result.error == "legacy hook exploded"
    assert redis_client.llen(QUEUE_NAME) == 1
    assert client.tags["hokusai.mint.status"] == "published"
    assert client.tags["hokusai.mint.legacy_status"] == "failed"
    assert client.tags["hokusai.canonical_score"] == "0.92"


def test_vesting_details_flow_to_tags_and_webhook(monkeypatch) -> None:
    decision = _accepted_decision()
    evaluator = Mock()
    evaluator.evaluate.return_value = decision
    evaluator.delta_threshold_pp = 1.0

    mint_hook = Mock()
    mint_hook.mint.return_value = TokenMintResult.model_validate(
        {
            "status": "success",
            "audit_ref": "audit-1",
            "timestamp": datetime.now(timezone.utc),
            "vesting": {
                "liquid_amount": "100",
                "vested_amount": "900",
                "vault_address": "0xvault",
                "schedule_id": "schedule-1",
                "claimable_amount": "25",
                "vesting_config": {"enabled": True, "immediateUnlockBps": 1000},
            },
        }
    )

    redis_client = fakeredis.FakeRedis(decode_responses=True)
    client = _FakeMlflowClient(run_metrics={"accuracy": 0.92}, initial_tags=_default_tags())
    dispatch_mock = Mock(return_value=[])
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        dispatch_mock,
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=MintRequestPublisher(redis_client=redis_client),
    )

    outcome = orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert outcome.mint_result is not None
    assert client.tags["hokusai.mint.vesting.liquid_amount"] == "100"
    assert client.tags["hokusai.mint.vesting.vested_amount"] == "900"
    assert client.tags["hokusai.mint.vesting.vault_address"] == "0xvault"
    assert client.tags["hokusai.mint.vesting.schedule_id"] == "schedule-1"
    assert client.tags["hokusai.mint.vesting.claimable_amount"] == "25"
    assert (
        client.tags["hokusai.mint.vesting.config_json"]
        == '{"enabled":true,"immediateUnlockBps":1000}'
    )

    minted_payload = dispatch_mock.call_args_list[1].kwargs["payload"]
    assert minted_payload["vesting"] == {
        "liquid_amount": "100",
        "vested_amount": "900",
        "vault_address": "0xvault",
        "schedule_id": "schedule-1",
        "claimable_amount": "25",
        "vesting_config": {"enabled": True, "immediateUnlockBps": 1000},
    }


def test_legacy_results_emit_no_vesting_tags_or_payload(monkeypatch) -> None:
    decision = _accepted_decision()
    evaluator = Mock()
    evaluator.evaluate.return_value = decision
    evaluator.delta_threshold_pp = 1.0

    mint_hook = Mock()
    mint_hook.mint.return_value = TokenMintResult(
        status="success",
        audit_ref="audit-1",
        timestamp=datetime.now(timezone.utc),
    )

    redis_client = fakeredis.FakeRedis(decode_responses=True)
    client = _FakeMlflowClient(run_metrics={"accuracy": 0.92}, initial_tags=_default_tags())
    dispatch_mock = Mock(return_value=[])
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        dispatch_mock,
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=MintRequestPublisher(redis_client=redis_client),
    )

    orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert not any(key.startswith("hokusai.mint.vesting.") for key in client.tags)
    minted_payload = dispatch_mock.call_args_list[1].kwargs["payload"]
    assert "vesting" not in minted_payload


def test_rejection_skips_mint(monkeypatch) -> None:
    decision = _accepted_decision()
    decision.accepted = False
    decision.reason = "delta_below_threshold"

    evaluator = Mock()
    evaluator.evaluate.return_value = decision
    evaluator.delta_threshold_pp = 1.0
    mint_hook = Mock()

    client = _FakeMlflowClient(run_metrics={"accuracy": 0.85})
    dispatch_mock = Mock(return_value=[])
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        dispatch_mock,
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
    )

    outcome = orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert outcome.status == "not_eligible"
    assert outcome.mint_result is None
    mint_hook.mint.assert_not_called()
    dispatch_mock.assert_not_called()
