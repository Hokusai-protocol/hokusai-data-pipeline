"""Integration-style tests for MintRequest end-to-end publishing via process_evaluation_with_spec.

Auth note: tests use fake MLflow clients only; no live MLflow requests are made.
Production auth relies on MLFLOW_TRACKING_TOKEN / Authorization env wiring.

Uses fakeredis for CI safety — no live Redis connection needed.  Simulates a
full evaluation acceptance path and verifies the MintRequest that lands in
hokusai:mint_requests has the correct structure and values.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import fakeredis
import jsonschema
import pytest

from src.api.schemas.token_mint import TokenMintResult
from src.eip712 import BaselineUnavailableError
from src.evaluation.deltaone_evaluator import DeltaOneDecision
from src.evaluation.deltaone_mint_orchestrator import DeltaOneMintOrchestrator
from src.evaluation.event_payload import EventPayloadError, make_idempotency_key
from src.evaluation.reward_cap import BudgetConfig
from src.evaluation.tags import (
    WEIGHT_COMMITMENT_BASELINE_TAG,
    WEIGHT_COMMITMENT_CANDIDATE_TAG,
)
from src.events.publishers.mint_request_publisher import QUEUE_NAME, MintRequestPublisher
from src.events.schemas import MintRequest

_EVAL_ID = "eval-integration-001"
_SPEC_ID = "spec-integration-v1"
_MODEL_ID_UINT = "99001"
_BASELINE_COMMITMENT = "0x" + "12" * 32
_CANDIDATE_COMMITMENT = "0x" + "34" * 32
_CONSUMER_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "schema" / "mint_request.consumer.v1.json").read_text(
        encoding="utf-8"
    )
)
_CONSUMER_VALIDATOR = jsonschema.Draft202012Validator(_CONSUMER_SCHEMA)


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


def _make_decision(
    accepted: bool = True,
    metric_name: str = "workflow_success_rate_under_budget",
    n_current: int = 1000,
) -> DeltaOneDecision:
    return DeltaOneDecision(
        accepted=accepted,
        reason="accepted" if accepted else "delta_below_threshold",
        run_id="run-cand",
        baseline_run_id="run-base",
        model_id="model-integration",
        dataset_hash="sha256:" + "a" * 64,
        metric_name=metric_name,
        delta_percentage_points=2.5,
        ci95_low_percentage_points=0.5,
        ci95_high_percentage_points=4.5,
        n_current=n_current,
        n_baseline=1000,
        evaluated_at=datetime.now(timezone.utc),
    )


def _make_spec() -> dict:
    return {
        "model_id": "model-integration",
        "model_id_uint": _MODEL_ID_UINT,
        "spec_id": _SPEC_ID,
        "eval_spec": {
            "primary_metric": {
                "name": "workflow_success_rate_under_budget",
                "direction": "higher_is_better",
            },
            "metric_family": "proportion",
            "measurement_policy": {"max_cost_usd": 5.0},
            "guardrails": [],
        },
        "contributors": [
            {
                "wallet_address": "0x742d35cc6634c0532925a3b844bc9e7595f62341",
                "weight_bps": 7000,
                "submissionId": "sub-1",
                "contributionBatchId": "batch-1",
            },
            {
                "wallet_address": "0x6c3e007f281f6948b37c511a11e43c8026d2f069",
                "weight_bps": 3000,
                "submissionId": "sub-2",
            },
        ],
    }


def _make_technical_task_router_spec() -> dict:
    spec = _make_spec()
    spec["task_type"] = "technical_task_router"
    spec["eval_spec"]["primary_metric"]["name"] = "technical_task_router.success_under_budget/v1"
    return spec


def _default_tags(eval_id: str) -> dict[str, str]:
    return {
        "hokusai.eval_id": eval_id,
        "hokusai.actual_cost_usd": "2.34",
        WEIGHT_COMMITMENT_BASELINE_TAG: _BASELINE_COMMITMENT,
        WEIGHT_COMMITMENT_CANDIDATE_TAG: _CANDIDATE_COMMITMENT,
    }


def _build_orchestrator(
    *,
    fake_redis_client,
    monkeypatch,
    eval_id: str,
    attestation_hash: str = "a" * 64,
    run_metrics: dict[str, float] | None = None,
    budget_config: BudgetConfig | None = None,
) -> DeltaOneMintOrchestrator:
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(),
    )
    evaluator = Mock()
    evaluator.evaluate_for_model.return_value = _make_decision(accepted=True)
    evaluator.delta_threshold_pp = 1.0
    mint_hook = Mock()
    mint_hook.mint.return_value = TokenMintResult(
        status="success",
        audit_ref="audit-integration",
        timestamp=datetime.now(timezone.utc),
    )
    mlflow_client = _FakeMlflowClient(
        run_metrics=run_metrics
        or {
            "workflow_success_rate_under_budget": 0.87,
            "hokusai_workflow_success_rate_under_budget": 0.87,
        },
        initial_tags=_default_tags(eval_id),
    )
    publisher = MintRequestPublisher(redis_client=fake_redis_client)
    reward_notifier = _FakeRewardNotifier()
    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=mlflow_client,
        mint_request_publisher=publisher,
        reward_entitlement_notifier=reward_notifier,
        budget_config=budget_config,
    )
    monkeypatch.setattr(
        orchestrator,
        "_create_signed_attestation",
        Mock(return_value=(attestation_hash, {"attestation_hash": attestation_hash})),
    )
    return orchestrator


def _queued_mint_request(fake_redis_client, index: int = 0) -> MintRequest:
    raw = fake_redis_client.lindex(QUEUE_NAME, index)
    assert raw is not None
    return MintRequest.model_validate_json(raw)


class _FakeMlflowClient:
    def __init__(self, run_metrics=None, initial_tags=None) -> None:
        self._run_metrics = run_metrics or {}
        self.tags = dict(initial_tags or {})

    def get_run(self, _run_id):
        return SimpleNamespace(data=SimpleNamespace(metrics=self._run_metrics, tags=self.tags))

    def set_tag(self, _run_id, key, value):
        self.tags[key] = value


@pytest.fixture()
def fake_redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def publisher(fake_redis_client):
    return MintRequestPublisher(redis_client=fake_redis_client)


@pytest.fixture()
def orchestrator(publisher, monkeypatch):
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(),
    )
    evaluator = Mock()
    evaluator.evaluate_for_model.return_value = _make_decision(accepted=True)
    evaluator.delta_threshold_pp = 1.0
    mint_hook = Mock()
    mint_hook.mint.return_value = TokenMintResult(
        status="success",
        audit_ref="audit-integration",
        timestamp=datetime.now(timezone.utc),
    )
    mlflow_client = _FakeMlflowClient(
        run_metrics={
            "workflow_success_rate_under_budget": 0.87,
            "hokusai_workflow_success_rate_under_budget": 0.87,
        },
        initial_tags=_default_tags(_EVAL_ID),
    )
    return DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=mlflow_client,
        mint_request_publisher=publisher,
        reward_entitlement_notifier=_FakeRewardNotifier(),
    )


class TestMintRequestPublishIntegration:
    def test_one_message_in_queue_after_acceptance(self, orchestrator, fake_redis_client) -> None:
        outcome = orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        assert outcome.status == "success"
        assert outcome.canonical_score_advanced is True
        assert outcome.mint_result is not None
        assert fake_redis_client.llen(QUEUE_NAME) == 1

    def test_secondary_dry_run_is_recorded_after_primary_publish(
        self, orchestrator, fake_redis_client
    ) -> None:
        outcome = orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        assert outcome.status == "success"
        assert outcome.mint_result is not None
        assert outcome.mint_result.status == "success"
        assert orchestrator._client.tags["hokusai.mint.status"] == "published"  # noqa: SLF001
        assert orchestrator._client.tags["hokusai.mint.legacy_status"] == "success"  # noqa: SLF001
        assert fake_redis_client.llen(QUEUE_NAME) == 1

    def test_published_message_is_valid_mint_request(self, orchestrator, fake_redis_client) -> None:
        orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        raw = fake_redis_client.lindex(QUEUE_NAME, 0)
        msg = MintRequest.model_validate_json(raw)
        payload = json.loads(raw)

        assert msg.model_id == "model-integration"
        assert msg.eval_id == _EVAL_ID
        assert msg.message_type == "mint_request"
        assert msg.schema_version == "1.0"
        assert msg.total_samples > 0
        assert msg.total_samples == msg.evaluation.sample_size_candidate
        assert payload["totalSamples"] == msg.total_samples
        assert "total_samples" not in payload
        _CONSUMER_VALIDATOR.validate(payload)
        assert "baseline" not in payload
        assert "baselineCommitment" not in payload
        assert "candidateCommitment" not in payload
        assert "attesterSignature" not in payload
        assert "signingDigest" not in payload

    def test_contributors_present_and_sum_to_10000(self, orchestrator, fake_redis_client) -> None:
        orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        raw = fake_redis_client.lindex(QUEUE_NAME, 0)
        msg = MintRequest.model_validate_json(raw)

        assert len(msg.contributors) == 2
        assert sum(c.weight_bps for c in msg.contributors) == 10000
        by_submission = {contributor.submission_id: contributor for contributor in msg.contributors}
        assert by_submission["sub-1"].contribution_batch_id == "batch-1"
        assert by_submission["sub-1"].weight_bps == 7000
        assert by_submission["sub-2"].weight_bps == 3000

    def test_scores_in_basis_points(self, orchestrator, fake_redis_client) -> None:
        orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        raw = fake_redis_client.lindex(QUEUE_NAME, 0)
        data = json.loads(raw)
        ev = data["evaluation"]

        assert 0 <= ev["baseline_score_bps"] <= 10000
        assert 0 <= ev["new_score_bps"] <= 10000
        # New score should be higher (acceptance implies improvement)
        assert ev["new_score_bps"] >= ev["baseline_score_bps"]

    def test_cost_fields_populated(self, orchestrator, fake_redis_client) -> None:
        orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        raw = fake_redis_client.lindex(QUEUE_NAME, 0)
        data = json.loads(raw)
        ev = data["evaluation"]

        assert ev["max_cost_usd_micro"] >= 0
        assert ev["actual_cost_usd_micro"] >= 0

    def test_idempotency_key_format(self, orchestrator, fake_redis_client) -> None:
        orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        raw = fake_redis_client.lindex(QUEUE_NAME, 0)
        data = json.loads(raw)

        key = data["idempotency_key"]
        assert key.startswith("0x")
        assert len(key) == 66  # "0x" + 64 hex chars

    def test_same_content_different_eval_ids_reuses_idempotency_key(
        self, fake_redis_client, monkeypatch
    ) -> None:
        first = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id="sched-7-run-a",
        )
        second = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id="sched-7-run-b",
        )

        first.process_evaluation_with_spec("run-cand", "run-base", _make_spec())
        second.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        first_msg = _queued_mint_request(fake_redis_client, 1)
        second_msg = _queued_mint_request(fake_redis_client, 0)

        assert first_msg.eval_id == "sched-7-run-a"
        assert second_msg.eval_id == "sched-7-run-b"
        assert first_msg.attestation_hash == second_msg.attestation_hash
        assert first_msg.idempotency_key == second_msg.idempotency_key
        assert first_msg.idempotency_key == make_idempotency_key(
            int(_MODEL_ID_UINT), first_msg.attestation_hash
        )

    def test_changed_content_produces_new_idempotency_key(
        self, fake_redis_client, monkeypatch
    ) -> None:
        first = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id="sched-7-run-a",
            attestation_hash="a" * 64,
        )
        second = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id="sched-7-run-b",
            attestation_hash="b" * 64,
        )

        first.process_evaluation_with_spec("run-cand", "run-base", _make_spec())
        second.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        first_msg = _queued_mint_request(fake_redis_client, 1)
        second_msg = _queued_mint_request(fake_redis_client, 0)

        assert first_msg.attestation_hash != second_msg.attestation_hash
        assert first_msg.idempotency_key != second_msg.idempotency_key

    def test_replay_no_op_simulation_uses_unique_content_keys(
        self, fake_redis_client, monkeypatch
    ) -> None:
        first = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id="sched-7-run-a",
            attestation_hash="a" * 64,
        )
        replay = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id="sched-7-run-b",
            attestation_hash="a" * 64,
        )
        changed = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id="sched-7-run-c",
            attestation_hash="b" * 64,
        )

        first.process_evaluation_with_spec("run-cand", "run-base", _make_spec())
        replay.process_evaluation_with_spec("run-cand", "run-base", _make_spec())
        changed.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        first_msg = _queued_mint_request(fake_redis_client, 2)
        replay_msg = _queued_mint_request(fake_redis_client, 1)
        changed_msg = _queued_mint_request(fake_redis_client, 0)

        processed: set[str] = set()
        accepted_submissions: list[str] = []
        for message in (first_msg, replay_msg, changed_msg):
            if message.idempotency_key in processed:
                continue
            processed.add(message.idempotency_key)
            accepted_submissions.append(message.idempotency_key)

        assert first_msg.idempotency_key == replay_msg.idempotency_key
        assert changed_msg.idempotency_key != first_msg.idempotency_key
        assert accepted_submissions == [first_msg.idempotency_key, changed_msg.idempotency_key]
        assert processed == {first_msg.idempotency_key, changed_msg.idempotency_key}

    def test_no_message_on_rejection(self, fake_redis_client, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(),
        )
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = _make_decision(accepted=False)
        evaluator.delta_threshold_pp = 1.0
        mint_hook = Mock()
        mlflow_client = _FakeMlflowClient(initial_tags=_default_tags(_EVAL_ID))
        publisher = MintRequestPublisher(redis_client=fake_redis_client)
        orch = DeltaOneMintOrchestrator(
            evaluator=evaluator,
            mint_hook=mint_hook,
            mlflow_client=mlflow_client,
            mint_request_publisher=publisher,
        )

        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        assert outcome.status == "not_eligible"
        assert fake_redis_client.llen(QUEUE_NAME) == 0

    def test_missing_candidate_commitment_aborts_before_publish(
        self, fake_redis_client, monkeypatch
    ) -> None:
        orchestrator = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id=_EVAL_ID,
        )
        orchestrator._client.tags.pop(WEIGHT_COMMITMENT_CANDIDATE_TAG)  # noqa: SLF001

        with pytest.raises(EventPayloadError, match="candidate_commitment"):
            orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        assert fake_redis_client.llen(QUEUE_NAME) == 0
        assert "hokusai.canonical_score" not in orchestrator._client.tags  # noqa: SLF001

    def test_missing_baseline_commitment_aborts_before_publish(
        self, fake_redis_client, monkeypatch
    ) -> None:
        orchestrator = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id=_EVAL_ID,
        )
        orchestrator._client.tags.pop(WEIGHT_COMMITMENT_BASELINE_TAG)  # noqa: SLF001

        with pytest.raises(EventPayloadError, match="baseline_commitment"):
            orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        assert fake_redis_client.llen(QUEUE_NAME) == 0
        assert "hokusai.canonical_score" not in orchestrator._client.tags  # noqa: SLF001

    def test_invalid_commitment_tag_aborts_before_publish(
        self, fake_redis_client, monkeypatch
    ) -> None:
        orchestrator = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id=_EVAL_ID,
        )
        orchestrator._client.tags[WEIGHT_COMMITMENT_CANDIDATE_TAG] = "0x" + "ABCD" * 16  # noqa: SLF001

        with pytest.raises(EventPayloadError, match="candidate_commitment"):
            orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        assert fake_redis_client.llen(QUEUE_NAME) == 0
        assert "hokusai.canonical_score" not in orchestrator._client.tags  # noqa: SLF001

    def test_secondary_dry_run_still_publishes_and_advances(
        self, fake_redis_client, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(),
        )
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = _make_decision(accepted=True)
        evaluator.delta_threshold_pp = 1.0
        mint_hook = Mock()
        mint_hook.mint.return_value = TokenMintResult(
            status="dry_run",
            audit_ref="audit-dry-run",
            timestamp=datetime.now(timezone.utc),
        )
        mlflow_client = _FakeMlflowClient(
            run_metrics={
                "workflow_success_rate_under_budget": 0.87,
                "hokusai_workflow_success_rate_under_budget": 0.87,
            },
            initial_tags=_default_tags(_EVAL_ID),
        )
        publisher = MintRequestPublisher(redis_client=fake_redis_client)
        orch = DeltaOneMintOrchestrator(
            evaluator=evaluator,
            mint_hook=mint_hook,
            mlflow_client=mlflow_client,
            mint_request_publisher=publisher,
            reward_entitlement_notifier=_FakeRewardNotifier(),
        )

        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        assert outcome.status == "success"
        assert outcome.canonical_score_advanced is True
        assert outcome.mint_result is not None
        assert outcome.mint_result.status == "dry_run"
        assert mlflow_client.tags["hokusai.mint.status"] == "published"
        assert mlflow_client.tags["hokusai.mint.legacy_status"] == "dry_run"
        assert fake_redis_client.llen(QUEUE_NAME) == 1

    def test_technical_task_router_spec_emits_total_samples(
        self, fake_redis_client, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(),
        )
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = _make_decision(
            accepted=True,
            metric_name="technical_task_router.success_under_budget/v1",
            n_current=4,
        )
        evaluator.delta_threshold_pp = 1.0
        mint_hook = Mock()
        mint_hook.mint.return_value = TokenMintResult(
            status="success",
            audit_ref="audit-integration",
            timestamp=datetime.now(timezone.utc),
        )
        mlflow_client = _FakeMlflowClient(
            run_metrics={
                "technical_task_router.success_under_budget/v1": 0.87,
                "technical_task_router_success_under_budget_v1": 0.87,
            },
            initial_tags=_default_tags(_EVAL_ID),
        )
        publisher = MintRequestPublisher(redis_client=fake_redis_client)
        orch = DeltaOneMintOrchestrator(
            evaluator=evaluator,
            mint_hook=mint_hook,
            mlflow_client=mlflow_client,
            mint_request_publisher=publisher,
        )

        orch.process_evaluation_with_spec(
            "run-cand", "run-base", _make_technical_task_router_spec()
        )

        payload = json.loads(fake_redis_client.lindex(QUEUE_NAME, 0))
        assert payload["totalSamples"] == 4
        assert payload["evaluation"]["sample_size_candidate"] == 4

    def test_pending_reward_entitlement_receives_contributor_metadata(
        self, fake_redis_client, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(),
        )
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = _make_decision(accepted=True)
        evaluator.delta_threshold_pp = 1.0
        mint_hook = Mock()
        mint_hook.mint.return_value = TokenMintResult(
            status="success",
            audit_ref="audit-integration",
            timestamp=datetime.now(timezone.utc),
        )
        mlflow_client = _FakeMlflowClient(
            run_metrics={
                "workflow_success_rate_under_budget": 0.87,
                "hokusai_workflow_success_rate_under_budget": 0.87,
            },
            initial_tags=_default_tags(_EVAL_ID),
        )
        reward_notifier = _FakeRewardNotifier()
        orch = DeltaOneMintOrchestrator(
            evaluator=evaluator,
            mint_hook=mint_hook,
            mlflow_client=mlflow_client,
            mint_request_publisher=MintRequestPublisher(redis_client=fake_redis_client),
            reward_entitlement_notifier=reward_notifier,
        )

        orch.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        assert [call["status"] for call in reward_notifier.calls] == ["pending"]
        mint_request = reward_notifier.calls[0]["mint_request"]
        by_submission = {
            contributor.submission_id: contributor for contributor in mint_request.contributors
        }
        assert by_submission["sub-1"].contribution_batch_id == "batch-1"
        assert by_submission["sub-2"].weight_bps == 3000

    def test_publish_does_not_read_onchain_block_hash_for_signing(
        self, fake_redis_client, monkeypatch
    ) -> None:
        monkeypatch.setenv("ETH_RPC_URL", "https://rpc.example")
        monkeypatch.setenv("MINT_REQUIRE_ONCHAIN_BASELINE", "true")
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.read_current_model_head",
            Mock(return_value="0x" + "9a" * 32),
        )
        orchestrator = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id=_EVAL_ID,
        )

        outcome = orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())
        msg = _queued_mint_request(fake_redis_client)

        assert outcome.status == "success"
        assert msg.baseline_commitment == _BASELINE_COMMITMENT

    def test_publish_raises_baseline_unavailable_on_rpc_failure(
        self, fake_redis_client, monkeypatch
    ) -> None:
        monkeypatch.setenv("ETH_RPC_URL", "https://rpc.example")
        monkeypatch.setenv("MINT_REQUIRE_ONCHAIN_BASELINE", "true")
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.read_current_model_head",
            Mock(side_effect=BaselineUnavailableError("timeout")),
        )
        orchestrator = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id=_EVAL_ID,
        )

        with pytest.raises(BaselineUnavailableError, match="timeout"):
            orchestrator._resolve_baseline_commitment(  # noqa: SLF001
                model_id_uint=_MODEL_ID_UINT,
                fallback_commitment=None,
            )

    def test_reward_entitlement_failure_does_not_block_queue_or_canonical_advance(
        self, fake_redis_client, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(),
        )
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = _make_decision(accepted=True)
        evaluator.delta_threshold_pp = 1.0
        mint_hook = Mock()
        mint_hook.mint.return_value = TokenMintResult(
            status="success",
            audit_ref="audit-integration",
            timestamp=datetime.now(timezone.utc),
        )
        mlflow_client = _FakeMlflowClient(
            run_metrics={
                "workflow_success_rate_under_budget": 0.87,
                "hokusai_workflow_success_rate_under_budget": 0.87,
            },
            initial_tags=_default_tags(_EVAL_ID),
        )
        reward_notifier = _FakeRewardNotifier(fail_statuses={"pending"})
        orch = DeltaOneMintOrchestrator(
            evaluator=evaluator,
            mint_hook=mint_hook,
            mlflow_client=mlflow_client,
            mint_request_publisher=MintRequestPublisher(redis_client=fake_redis_client),
            reward_entitlement_notifier=reward_notifier,
        )

        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        assert outcome.status == "success"
        assert fake_redis_client.llen(QUEUE_NAME) == 1
        assert mlflow_client.tags["hokusai.canonical_score"] == "0.87"

    def test_over_max_reward_is_capped_but_still_published(
        self, fake_redis_client, monkeypatch
    ) -> None:
        orchestrator = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id=_EVAL_ID,
            budget_config=BudgetConfig(tokens_per_delta_one=100.0, max_reward_per_eval=1.0),
        )

        outcome = orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        assert outcome.status == "success"
        assert outcome.reward_tokens == 1.0
        assert outcome.reward_capped is True
        assert fake_redis_client.llen(QUEUE_NAME) == 1

    def test_cost_ceiling_blocks_publish(self, fake_redis_client, monkeypatch) -> None:
        orchestrator = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id=_EVAL_ID,
            budget_config=BudgetConfig(per_eval_budget_ceiling_usd=1.0),
        )

        outcome = orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        assert outcome.status == "cost_ceiling_exceeded"
        assert outcome.canonical_score_advanced is False
        assert fake_redis_client.llen(QUEUE_NAME) == 0

    def test_cost_ceiling_boundary_allows_publish(self, fake_redis_client, monkeypatch) -> None:
        orchestrator = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id=_EVAL_ID,
            budget_config=BudgetConfig(per_eval_budget_ceiling_usd=2.34),
        )

        outcome = orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        assert outcome.status == "success"
        assert fake_redis_client.llen(QUEUE_NAME) == 1

    def test_mint_paused_blocks_publish(self, fake_redis_client, monkeypatch) -> None:
        orchestrator = _build_orchestrator(
            fake_redis_client=fake_redis_client,
            monkeypatch=monkeypatch,
            eval_id=_EVAL_ID,
            budget_config=BudgetConfig(mint_paused=True),
        )

        outcome = orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        assert outcome.status == "paused"
        assert fake_redis_client.llen(QUEUE_NAME) == 0
