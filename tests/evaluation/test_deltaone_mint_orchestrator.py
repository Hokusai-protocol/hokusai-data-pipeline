"""Unit tests for DeltaOne -> token mint orchestration."""

from __future__ import annotations

# Auth-hook note: this suite uses fake MLflow clients and patched webhook/mint
# calls only; no live MLflow requests are made.
# Production MLflow auth relies on Authorization / MLFLOW_TRACKING_TOKEN env wiring.
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from src.api.schemas.token_mint import TokenMintResult
from src.evaluation.deltaone_evaluator import DeltaOneDecision
from src.evaluation.deltaone_mint_orchestrator import DeltaOneMintOrchestrator
from src.evaluation.event_payload import (
    DELTAONE_ACCEPTANCE_EVENT_VERSION,
    make_idempotency_key,
)


class _FakeMlflowClient:
    """Per-run fake MLflow client supporting separate metrics/tags per run id."""

    def __init__(
        self,
        runs: dict[str, dict[str, dict]] | None = None,
        # Backwards-compat: callers can still pass a single dict of metrics
        # and an initial tag dict that applies to every run.
        run_metrics: dict[str, float] | None = None,
        initial_tags: dict[str, str] | None = None,
    ) -> None:
        if runs is not None:
            self._runs = {
                run_id: {
                    "metrics": dict(payload.get("metrics", {})),
                    "tags": dict(payload.get("tags", {})),
                    "params": dict(payload.get("params", {})),
                }
                for run_id, payload in runs.items()
            }
            self._default = None
        else:
            self._runs = {}
            self._default = {
                "metrics": dict(run_metrics or {}),
                "tags": dict(initial_tags or {}),
                "params": {},
            }
        # `tags` exposes the active per-run tag dict so legacy assertions like
        # `client.tags["hokusai.canonical_score"]` keep working when there is
        # only one logical run.
        self.tags = (
            self._runs[next(iter(self._runs))]["tags"] if self._runs else self._default["tags"]
        )

    def _bucket(self, run_id: str) -> dict:
        if self._runs:
            if run_id not in self._runs:
                self._runs[run_id] = {"metrics": {}, "tags": {}, "params": {}}
            return self._runs[run_id]
        return self._default

    def get_run(self, run_id: str):
        bucket = self._bucket(run_id)
        return SimpleNamespace(
            data=SimpleNamespace(
                metrics=bucket["metrics"],
                tags=bucket["tags"],
                params=bucket["params"],
            )
        )

    def set_tag(self, run_id: str, key: str, value: str) -> None:
        bucket = self._bucket(run_id)
        bucket["tags"][key] = value
        if self._runs and bucket["tags"] is self.tags:
            # `self.tags` already references this dict.
            return
        if not self._runs:
            self.tags = bucket["tags"]


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


def _candidate_tags() -> dict[str, str]:
    return {
        "hokusai.model_id_uint": "42",
        "hokusai.eval_id": "eval-1",
        "hokusai.benchmark_spec_id": "spec-1",
    }


def _build_runs(candidate_metrics: dict, baseline_metrics: dict | None = None):
    return {
        "run-candidate": {
            "metrics": candidate_metrics,
            "tags": _candidate_tags(),
        },
        "run-baseline": {
            "metrics": baseline_metrics if baseline_metrics is not None else {"accuracy": 0.80},
        },
    }


def test_acceptance_mint_success_advances_canonical_score(monkeypatch) -> None:
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

    client = _FakeMlflowClient(runs=_build_runs({"accuracy": 0.92}))
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

    assert outcome.status == "success"
    assert outcome.canonical_score_advanced is True
    candidate_tags = client._runs["run-candidate"]["tags"]
    assert candidate_tags["hokusai.canonical_score"] == "0.92"
    assert candidate_tags["hokusai.canonical_score_run_id"] == "run-candidate"
    assert candidate_tags["hokusai.mint.status"] == "success"

    expected_idempotency = make_idempotency_key(42, "eval-1", outcome.attestation_hash)
    assert outcome.idempotency_key == expected_idempotency
    mint_hook.mint.assert_called_once()
    assert mint_hook.mint.call_args.kwargs["idempotency_key"] == expected_idempotency
    assert candidate_tags["hokusai.mint.idempotency_key"] == expected_idempotency
    # Attestation hash on the tag is the canonical 64-hex form.
    assert candidate_tags["hokusai.mint.attestation_hash"] == outcome.attestation_hash
    assert len(outcome.attestation_hash) == 64

    assert dispatch_mock.call_count == 2
    achieved_call = dispatch_mock.call_args_list[0]
    assert achieved_call.kwargs["event_type"] == "deltaone.achieved"
    payload = achieved_call.kwargs["payload"]
    assert payload["event_version"] == DELTAONE_ACCEPTANCE_EVENT_VERSION
    assert payload["model_id_uint"] == "42"
    assert isinstance(payload["candidate_score_bps"], int)
    assert payload["candidate_score_bps"] == 9200
    assert payload["baseline_score_bps"] == 8000
    assert payload["delta_bps"] == 1200
    assert payload["primary_metric_mlflow_name"] == "accuracy"
    assert payload["idempotency_key"] == expected_idempotency
    assert payload["max_cost_usd_micro"] == 0
    assert payload["actual_cost_usd_micro"] == 0
    assert isinstance(payload["max_cost_usd_micro"], int)
    assert dispatch_mock.call_args_list[1].kwargs["event_type"] == "deltaone.minted"


def test_acceptance_mint_failure_does_not_advance_canonical_score(monkeypatch) -> None:
    decision = _accepted_decision()
    evaluator = Mock()
    evaluator.evaluate.return_value = decision
    evaluator.delta_threshold_pp = 1.0

    mint_hook = Mock()
    mint_hook.mint.return_value = TokenMintResult(
        status="failed",
        audit_ref="audit-2",
        timestamp=datetime.now(timezone.utc),
        error="upstream error",
    )

    client = _FakeMlflowClient(runs=_build_runs({"accuracy": 0.92}))
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(return_value=[]),
    )

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
    )

    outcome = orchestrator.process_evaluation("run-candidate", "run-baseline")

    assert outcome.status == "failed"
    assert outcome.canonical_score_advanced is False
    candidate_tags = client._runs["run-candidate"]["tags"]
    assert "hokusai.canonical_score" not in candidate_tags
    assert candidate_tags["hokusai.mint.status"] == "failed"


def test_rejection_skips_mint(monkeypatch) -> None:
    decision = _accepted_decision()
    decision.accepted = False
    decision.reason = "delta_below_threshold"

    evaluator = Mock()
    evaluator.evaluate.return_value = decision
    evaluator.delta_threshold_pp = 1.0
    mint_hook = Mock()

    client = _FakeMlflowClient(runs=_build_runs({"accuracy": 0.85}))
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


def test_acceptance_event_uses_spec_metric_family_and_threshold(monkeypatch) -> None:
    """When called with a spec, the event reflects spec-derived metric_family/threshold."""
    decision = _accepted_decision()
    decision.metric_name = "workflow_success_rate_under_budget"

    evaluator = Mock()
    evaluator.evaluate_for_model.return_value = decision
    evaluator.delta_threshold_pp = 1.0

    mint_hook = Mock()
    mint_hook.mint.return_value = TokenMintResult(
        status="success",
        audit_ref="audit-1",
        timestamp=datetime.now(timezone.utc),
    )

    runs = {
        "run-candidate": {
            "metrics": {
                "workflow_success_rate_under_budget": 0.92,
                "cost_per_call": 0.05,
            },
            "tags": _candidate_tags(),
        },
        "run-baseline": {
            "metrics": {"workflow_success_rate_under_budget": 0.80},
        },
    }
    client = _FakeMlflowClient(runs=runs)
    dispatch_mock = Mock(return_value=[])
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        dispatch_mock,
    )

    spec = {
        "model_id": "model-a",
        "spec_id": "spec-1",
        "model_id_uint": "42",
        "metadata": {
            "max_cost_usd": "1.0",
        },
        "eval_spec": {
            "metric_family": "proportion",
            "primary_metric": {
                "name": "workflow_success_rate_under_budget",
                "mlflow_name": "workflow_success_rate_under_budget",
                "threshold": 0.02,
            },
            "guardrails": [
                {
                    "name": "cost_per_call",
                    "direction": "lower_is_better",
                    "threshold": 0.10,
                },
            ],
        },
    }

    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
    )

    outcome = orchestrator.process_evaluation_with_spec("run-candidate", "run-baseline", spec)

    assert outcome.status == "success"
    achieved = dispatch_mock.call_args_list[0].kwargs["payload"]
    assert achieved["metric_family"] == "proportion"
    assert achieved["delta_threshold_bps"] == 200  # 0.02 * 10000
    assert achieved["benchmark_spec_id"] == "spec-1"
    assert achieved["primary_metric_name"] == "workflow_success_rate_under_budget"
    assert achieved["max_cost_usd_micro"] == 1_000_000
    assert achieved["guardrails"]["total_guardrails"] == 1
    assert achieved["guardrails"]["guardrails_passed"] == 1
    assert achieved["guardrails"]["breaches"] == []


def test_acceptance_missing_eval_id_raises(monkeypatch) -> None:
    """Without eval_id we refuse to emit an on-chain-incompatible event."""
    decision = _accepted_decision()
    evaluator = Mock()
    evaluator.evaluate.return_value = decision
    evaluator.delta_threshold_pp = 1.0

    runs = {
        "run-candidate": {
            "metrics": {"accuracy": 0.92},
            "tags": {"hokusai.model_id_uint": "42"},
        },
        "run-baseline": {"metrics": {"accuracy": 0.80}},
    }
    client = _FakeMlflowClient(runs=runs)
    monkeypatch.setattr(
        "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
        Mock(return_value=[]),
    )

    mint_hook = Mock()
    orchestrator = DeltaOneMintOrchestrator(
        evaluator=evaluator,
        mint_hook=mint_hook,
        mlflow_client=client,
    )

    import pytest

    with pytest.raises(ValueError, match="eval_id"):
        orchestrator.process_evaluation("run-candidate", "run-baseline")
    mint_hook.mint.assert_not_called()
