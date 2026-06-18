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
from src.cli.attestation import AttestationState
from src.evaluation.deltaone_evaluator import DeltaOneDecision
from src.evaluation.deltaone_mint_orchestrator import DeltaOneMintOrchestrator
from src.evaluation.tags import (
    PER_ROW_ARTIFACT_URI_TAG,
    WEIGHT_COMMITMENT_BASELINE_TAG,
    WEIGHT_COMMITMENT_CANDIDATE_TAG,
)
from src.events.publishers.mint_request_publisher import QUEUE_NAME, MintRequestPublisher

_CONTRIBUTORS_TAG = json.dumps(
    [{"wallet_address": "0x742d35cc6634c0532925a3b844bc9e7595f62341", "weight_bps": 10000}]
)
_BASELINE_COMMITMENT = "0x" + "12" * 32
_CANDIDATE_COMMITMENT = "0x" + "34" * 32


class _FakeRewardNotifier:
    def __init__(self, fail_statuses: set[str] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_statuses = fail_statuses or set()

    def notify_reward_entitlement(self, *, mint_request, status, mint_result=None):
        self.calls.append(
            {"mint_request": mint_request, "status": status, "mint_result": mint_result}
        )
        if status in self.fail_statuses:
            return False, f"{status} failed"
        return True, None


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
        WEIGHT_COMMITMENT_BASELINE_TAG: _BASELINE_COMMITMENT,
        WEIGHT_COMMITMENT_CANDIDATE_TAG: _CANDIDATE_COMMITMENT,
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
        reward_entitlement_notifier=_FakeRewardNotifier(),
    )

    outcome = orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert outcome.status == "success"
    assert outcome.canonical_score_advanced is True
    assert redis_client.llen(QUEUE_NAME) == 1
    assert client.tags["hokusai.canonical_score"] == "0.92"
    assert client.tags["hokusai.canonical_score_run_id"] == "run-candidate"
    assert client.tags["hokusai.mint.status"] == "published"
    assert client.tags["hokusai.mint.legacy_status"] == "success"
    payload = json.loads(redis_client.lindex(QUEUE_NAME, 0))
    assert payload["totalSamples"] == 1000
    assert payload["evaluation"]["sample_size_candidate"] == 1000
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
        reward_entitlement_notifier=_FakeRewardNotifier(),
    )

    with pytest.raises(RedisConnectionError):
        orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert "hokusai.canonical_score" not in client.tags
    assert client.tags["hokusai.mint.status"] == "requested"
    mint_hook.mint.assert_not_called()


@pytest.mark.parametrize("n_current", [0, -1, None, True])
def test_invalid_candidate_sample_size_aborts_publish_and_canonical_advance(
    monkeypatch, n_current
) -> None:
    decision = _accepted_decision()
    decision.n_current = n_current
    evaluator = Mock()
    evaluator.evaluate.return_value = decision
    evaluator.delta_threshold_pp = 1.0

    mint_hook = Mock()
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
        reward_entitlement_notifier=_FakeRewardNotifier(),
    )

    with pytest.raises(ValueError, match="totalSamples"):
        orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert redis_client.llen(QUEUE_NAME) == 0
    assert "hokusai.canonical_score" not in client.tags
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
        reward_entitlement_notifier=_FakeRewardNotifier(),
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
        reward_entitlement_notifier=_FakeRewardNotifier(),
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
        reward_entitlement_notifier=_FakeRewardNotifier(),
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
        reward_entitlement_notifier=_FakeRewardNotifier(),
    )

    outcome = orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert outcome.status == "not_eligible"
    assert outcome.mint_result is None
    mint_hook.mint.assert_not_called()
    dispatch_mock.assert_not_called()


def test_reward_entitlement_pending_sent_after_publish(monkeypatch) -> None:
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
    notifier = _FakeRewardNotifier()
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(return_value=[]),
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=MintRequestPublisher(redis_client=redis_client),
        reward_entitlement_notifier=notifier,
    )

    orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert notifier.calls[0]["status"] == "pending"


def test_reward_entitlement_failure_does_not_block_publish(monkeypatch) -> None:
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
    notifier = _FakeRewardNotifier(fail_statuses={"pending"})
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(return_value=[]),
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=MintRequestPublisher(redis_client=redis_client),
        reward_entitlement_notifier=notifier,
    )

    outcome = orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert outcome.status == "success"
    assert redis_client.llen(QUEUE_NAME) == 1
    assert client.tags["hokusai.canonical_score"] == "0.92"


def test_claimable_reward_entitlement_sent_when_vesting_present(monkeypatch) -> None:
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
            "vesting": {"claimable_amount": "25"},
        }
    )
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    client = _FakeMlflowClient(run_metrics={"accuracy": 0.92}, initial_tags=_default_tags())
    notifier = _FakeRewardNotifier()
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(return_value=[]),
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=MintRequestPublisher(redis_client=redis_client),
        reward_entitlement_notifier=notifier,
    )

    orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert [call["status"] for call in notifier.calls] == ["pending", "claimable"]


def test_missing_attestation_state_blocks_publish_when_required(monkeypatch) -> None:
    decision = _accepted_decision()
    evaluator = Mock()
    evaluator.evaluate.return_value = decision
    evaluator.delta_threshold_pp = 1.0
    mint_hook = Mock()
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    client = _FakeMlflowClient(run_metrics={"accuracy": 0.92}, initial_tags=_default_tags())
    monkeypatch.setenv("MINT_REQUIRE_ATTESTER_SIGNATURE", "true")
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(return_value=[]),
    )
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.load_attestation_state",
        Mock(return_value=None),
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=MintRequestPublisher(redis_client=redis_client),
        reward_entitlement_notifier=_FakeRewardNotifier(),
    )

    with pytest.raises(ValueError, match="verified attester signatures are required"):
        orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert redis_client.llen(QUEUE_NAME) == 0


def test_valid_attestation_state_publishes_sorted_signatures(monkeypatch) -> None:
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
    sig_a = "0x" + ("1" * 128) + "1b"
    sig_b = "0x" + ("2" * 128) + "1b"
    # Conftest globally mocks read_current_model_head -> "0x9a"*32 at publish time;
    # AttestationState.baseline_commitment must match that for the post-attach drift
    # check to pass.
    onchain_baseline = "0x" + "9a" * 32
    monkeypatch.setenv("MINT_REQUIRE_ATTESTER_SIGNATURE", "true")
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(return_value=[]),
    )
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.load_attestation_state",
        Mock(
            return_value=AttestationState(
                digest_hex="0x" + "0" * 64,
                baseline_commitment=onchain_baseline,
                built_at="2026-06-11T00:00:00+00:00",
                signatures=[sig_b, sig_a],
            )
        ),
    )
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator._verify_attestation_state",
        Mock(return_value=[sig_a, sig_b]),
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=MintRequestPublisher(redis_client=redis_client),
        reward_entitlement_notifier=_FakeRewardNotifier(),
    )

    monkeypatch.setattr("src.eip712.compute_digest", Mock(return_value=bytes.fromhex("00" * 32)))
    outcome = orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert outcome.status == "success"
    payload = json.loads(redis_client.lindex(QUEUE_NAME, 0))
    assert payload["attester_signatures"] == [sig_a, sig_b]


def test_post_attach_baseline_drift_blocks_publish(monkeypatch, caplog) -> None:
    decision = _accepted_decision()
    evaluator = Mock()
    evaluator.evaluate.return_value = decision
    evaluator.delta_threshold_pp = 1.0
    mint_hook = Mock()
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    client = _FakeMlflowClient(run_metrics={"accuracy": 0.92}, initial_tags=_default_tags())
    sig = "0x" + ("1" * 128) + "1b"
    # AttestationState was built/attached against an old baseline; the conftest fixture
    # returns a different on-chain head at publish time, so the drift check must fire.
    stale_baseline = "0x" + "11" * 32
    monkeypatch.setenv("MINT_REQUIRE_ATTESTER_SIGNATURE", "true")
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(return_value=[]),
    )
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.load_attestation_state",
        Mock(
            return_value=AttestationState(
                digest_hex="0x" + "0" * 64,
                baseline_commitment=stale_baseline,
                built_at="2026-06-11T00:00:00+00:00",
                signatures=[sig],
            )
        ),
    )
    monkeypatch.setattr("src.eip712.compute_digest", Mock(return_value=bytes.fromhex("00" * 32)))

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
        mint_request_publisher=MintRequestPublisher(redis_client=redis_client),
        reward_entitlement_notifier=_FakeRewardNotifier(),
    )

    with caplog.at_level("ERROR"):
        with pytest.raises(ValueError, match="baseline drifted between attach and publish"):
            orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert any(
        "mint_authorization_baseline_drift_post_attach" in record.getMessage()
        for record in caplog.records
    )
    assert redis_client.llen(QUEUE_NAME) == 0


def _per_row_orchestrator() -> DeltaOneMintOrchestrator:
    return DeltaOneMintOrchestrator(
        evaluator=Mock(),
        mint_hook=Mock(),
        mlflow_client=_FakeMlflowClient(
            run_metrics={},
            initial_tags={PER_ROW_ARTIFACT_URI_TAG: "runs:/run-baseline/attribution"},
        ),
        mint_request_publisher=MintRequestPublisher(
            redis_client=fakeredis.FakeRedis(decode_responses=True)
        ),
        reward_entitlement_notifier=_FakeRewardNotifier(),
    )


def test_load_attribution_report_builds_from_per_row_when_no_report_tag(monkeypatch) -> None:
    import pandas as pd

    from src.evaluation import deltaone_mint_orchestrator as orch_mod

    candidate_frame = pd.DataFrame(
        [
            {
                "row_id": "r0",
                "completed_successfully": True,
                "neighbor_provenance": json.dumps(
                    [{"training_row_index": 0, "weight": 1.0, "account_id": "user-a"}]
                ),
            }
        ]
    )
    baseline_frame = pd.DataFrame(
        [{"row_id": "r0", "completed_successfully": False, "neighbor_provenance": "[]"}]
    )

    def _fake_read(uri: str):
        return candidate_frame if "candidate" in uri else baseline_frame

    monkeypatch.setattr(orch_mod, "_read_per_row_artifact", _fake_read)

    orchestrator = _per_row_orchestrator()
    report = orchestrator._load_attribution_report(
        {PER_ROW_ARTIFACT_URI_TAG: "runs:/run-candidate/attribution"},
        "run-candidate",
        baseline_run_id="run-baseline",
        model_id="model-a",
    )

    assert report is not None
    assert [c["account_id"] for c in report["contributors"]] == ["user-a"]
    assert report["candidate_run_id"] == "run-candidate"
    assert report["baseline_run_id"] == "run-baseline"


def test_load_attribution_report_returns_none_without_per_row_tags(monkeypatch) -> None:
    from src.evaluation import deltaone_mint_orchestrator as orch_mod

    monkeypatch.setattr(
        orch_mod,
        "_read_per_row_artifact",
        lambda _uri: pytest.fail("should not read when candidate has no per-row tag"),
    )

    orchestrator = _per_row_orchestrator()
    report = orchestrator._load_attribution_report(
        {},  # candidate run has neither a report tag nor a per-row tag
        "run-candidate",
        baseline_run_id="run-baseline",
        model_id="model-a",
    )

    assert report is None
