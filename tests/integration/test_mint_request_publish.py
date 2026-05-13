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
from types import SimpleNamespace
from unittest.mock import Mock

import fakeredis
import pytest

from src.api.schemas.token_mint import TokenMintResult
from src.evaluation.deltaone_evaluator import DeltaOneDecision
from src.evaluation.deltaone_mint_orchestrator import DeltaOneMintOrchestrator
from src.events.publishers.mint_request_publisher import QUEUE_NAME, MintRequestPublisher
from src.events.schemas import MintRequest

_EVAL_ID = "eval-integration-001"
_SPEC_ID = "spec-integration-v1"
_MODEL_ID_UINT = "99001"


def _make_decision(accepted: bool = True) -> DeltaOneDecision:
    return DeltaOneDecision(
        accepted=accepted,
        reason="accepted" if accepted else "delta_below_threshold",
        run_id="run-cand",
        baseline_run_id="run-base",
        model_id="model-integration",
        dataset_hash="sha256:" + "a" * 64,
        metric_name="workflow_success_rate_under_budget",
        delta_percentage_points=2.5,
        ci95_low_percentage_points=0.5,
        ci95_high_percentage_points=4.5,
        n_current=1000,
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
            {"wallet_address": "0x742d35cc6634c0532925a3b844bc9e7595f62341", "weight_bps": 7000},
            {"wallet_address": "0x6c3e007f281f6948b37c511a11e43c8026d2f069", "weight_bps": 3000},
        ],
    }


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
        initial_tags={
            "hokusai.eval_id": _EVAL_ID,
            "hokusai.actual_cost_usd": "2.34",
        },
    )
    return DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=mlflow_client,
        mint_request_publisher=publisher,
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

        assert msg.model_id == "model-integration"
        assert msg.eval_id == _EVAL_ID
        assert msg.message_type == "mint_request"
        assert msg.schema_version == "1.0"

    def test_contributors_present_and_sum_to_10000(self, orchestrator, fake_redis_client) -> None:
        orchestrator.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        raw = fake_redis_client.lindex(QUEUE_NAME, 0)
        msg = MintRequest.model_validate_json(raw)

        assert len(msg.contributors) == 2
        assert sum(c.weight_bps for c in msg.contributors) == 10000

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

    def test_no_message_on_rejection(self, fake_redis_client, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(),
        )
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = _make_decision(accepted=False)
        evaluator.delta_threshold_pp = 1.0
        mint_hook = Mock()
        mlflow_client = _FakeMlflowClient(initial_tags={"hokusai.eval_id": _EVAL_ID})
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
            initial_tags={
                "hokusai.eval_id": _EVAL_ID,
                "hokusai.actual_cost_usd": "2.34",
            },
        )
        publisher = MintRequestPublisher(redis_client=fake_redis_client)
        orch = DeltaOneMintOrchestrator(
            evaluator=evaluator,
            mint_hook=mint_hook,
            mlflow_client=mlflow_client,
            mint_request_publisher=publisher,
        )

        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", _make_spec())

        assert outcome.status == "success"
        assert outcome.canonical_score_advanced is True
        assert outcome.mint_result is not None
        assert outcome.mint_result.status == "dry_run"
        assert mlflow_client.tags["hokusai.mint.status"] == "published"
        assert mlflow_client.tags["hokusai.mint.legacy_status"] == "dry_run"
        assert fake_redis_client.llen(QUEUE_NAME) == 1
