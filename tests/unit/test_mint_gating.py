"""Tests for guardrail-gated DeltaOne mint orchestration.

Auth note: tests use fake MLflow clients only; no live MLflow requests are made.
Production auth relies on MLFLOW_TRACKING_TOKEN / Authorization env wiring.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from src.api.schemas.token_mint import TokenMintResult
from src.evaluation.deltaone_evaluator import DeltaOneDecision
from src.evaluation.deltaone_mint_orchestrator import (
    DeltaOneMintOrchestrator,
    _build_blocked_reason,
    _decision_to_comparator_result,
    _extract_guardrail_observations,
    _extract_guardrail_specs,
)
from src.evaluation.schema import ComparatorResult, GuardrailResult
from src.evaluation.spec_translation import RuntimeGuardrailSpec

HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


class _FakeMlflowClient:
    def __init__(
        self,
        run_metrics: dict[str, float] | None = None,
        initial_tags: dict[str, str] | None = None,
    ) -> None:
        self._run_metrics = run_metrics or {}
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


def _make_decision(accepted: bool = True, reason: str = "accepted") -> DeltaOneDecision:
    return DeltaOneDecision(
        accepted=accepted,
        reason=reason,
        run_id="run-cand",
        baseline_run_id="run-base",
        model_id="model-x",
        dataset_hash=HASH_A,
        metric_name="workflow_success_rate_under_budget",
        delta_percentage_points=2.0,
        ci95_low_percentage_points=0.5,
        ci95_high_percentage_points=3.5,
        n_current=1000,
        n_baseline=1000,
        evaluated_at=datetime.now(timezone.utc),
    )


def _make_spec_with_guardrails(guardrails: list[dict]) -> dict:
    return {
        "model_id": "model-x",
        "eval_spec": {
            "primary_metric": {
                "name": "workflow_success_rate_under_budget",
                "direction": "higher_is_better",
            },
            "guardrails": guardrails,
        },
    }


# ---------------------------------------------------------------------------
# process_evaluation_with_spec: mint gating scenarios
# ---------------------------------------------------------------------------


class TestProcessEvaluationWithSpec:
    def _make_orchestrator(self, decision, run_metrics=None, monkeypatch=None):
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = decision
        mint_hook = Mock()
        mint_hook.mint.return_value = TokenMintResult(
            status="success",
            audit_ref="audit-ok",
            timestamp=datetime.now(timezone.utc),
        )
        client = _FakeMlflowClient(run_metrics=run_metrics or {})
        orch = DeltaOneMintOrchestrator(
            evaluator=evaluator, mint_hook=mint_hook, mlflow_client=client
        )
        return orch, mint_hook, client

    def test_primary_pass_guardrail_pass_mint_allowed(self, monkeypatch):
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(return_value=[]),
        )
        decision = _make_decision(accepted=True)
        spec = _make_spec_with_guardrails(
            [{"name": "cost_per_call", "direction": "lower_is_better", "threshold": 0.10}]
        )
        run_metrics = {"workflow_success_rate_under_budget": 0.87, "cost_per_call": 0.05}
        orch, mint_hook, client = self._make_orchestrator(decision, run_metrics)

        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", spec)

        assert outcome.status == "success"
        mint_hook.mint.assert_called_once()

    def test_primary_pass_guardrail_breach_blocks_mint(self, monkeypatch):
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(return_value=[]),
        )
        decision = _make_decision(accepted=True)
        spec = _make_spec_with_guardrails(
            [{"name": "cost_per_call", "direction": "lower_is_better", "threshold": 0.10}]
        )
        run_metrics = {"workflow_success_rate_under_budget": 0.87, "cost_per_call": 0.50}
        orch, mint_hook, client = self._make_orchestrator(decision, run_metrics)

        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", spec)

        assert outcome.status == "guardrail_breach"
        mint_hook.mint.assert_not_called()

    def test_primary_fail_guardrail_pass_blocks_mint(self, monkeypatch):
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(return_value=[]),
        )
        decision = _make_decision(accepted=False, reason="delta_below_threshold")
        spec = _make_spec_with_guardrails(
            [{"name": "cost_per_call", "direction": "lower_is_better", "threshold": 0.10}]
        )
        run_metrics = {"cost_per_call": 0.05}
        orch, mint_hook, client = self._make_orchestrator(decision, run_metrics)

        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", spec)

        assert outcome.status == "not_eligible"
        mint_hook.mint.assert_not_called()

    def test_primary_fail_guardrail_breach_blocks_mint(self, monkeypatch):
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(return_value=[]),
        )
        decision = _make_decision(accepted=False, reason="not_statistically_significant")
        spec = _make_spec_with_guardrails(
            [{"name": "cost_per_call", "direction": "lower_is_better", "threshold": 0.10}]
        )
        run_metrics = {"cost_per_call": 0.50}
        orch, mint_hook, client = self._make_orchestrator(decision, run_metrics)

        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", spec)

        assert outcome.status in {"not_eligible", "guardrail_breach"}
        mint_hook.mint.assert_not_called()

    def test_guardrail_breach_recorded_in_tags(self, monkeypatch):
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(return_value=[]),
        )
        decision = _make_decision(accepted=True)
        spec = _make_spec_with_guardrails(
            [{"name": "cost_per_call", "direction": "lower_is_better", "threshold": 0.10}]
        )
        run_metrics = {"cost_per_call": 0.50}
        orch, mint_hook, client = self._make_orchestrator(decision, run_metrics)

        orch.process_evaluation_with_spec("run-cand", "run-base", spec)

        assert "hokusai.guardrail.cost_per_call.status" in client.tags
        assert client.tags["hokusai.guardrail.cost_per_call.status"] == "fail"


# ---------------------------------------------------------------------------
# Wavemill workflow_success_rate_under_budget regression
# ---------------------------------------------------------------------------


class TestWavemillProportionRegression:
    """workflow_success_rate_under_budget is proportion + budget guardrail."""

    def _build_spec(self) -> dict:
        return _make_spec_with_guardrails(
            [{"name": "budget_utilization", "direction": "lower_is_better", "threshold": 1.0}]
        )

    def test_proportion_pass_budget_pass_mint_allowed(self, monkeypatch):
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(return_value=[]),
        )
        decision = _make_decision(accepted=True)
        run_metrics = {"workflow_success_rate_under_budget": 0.87, "budget_utilization": 0.85}
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = decision
        mint_hook = Mock()
        mint_hook.mint.return_value = TokenMintResult(
            status="success", audit_ref="ok", timestamp=datetime.now(timezone.utc)
        )
        client = _FakeMlflowClient(run_metrics=run_metrics)
        orch = DeltaOneMintOrchestrator(
            evaluator=evaluator, mint_hook=mint_hook, mlflow_client=client
        )

        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", self._build_spec())
        assert outcome.status == "success"
        mint_hook.mint.assert_called_once()

    def test_proportion_pass_budget_breach_blocks_mint(self, monkeypatch):
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(return_value=[]),
        )
        decision = _make_decision(accepted=True)
        run_metrics = {"workflow_success_rate_under_budget": 0.87, "budget_utilization": 1.20}
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = decision
        mint_hook = Mock()
        client = _FakeMlflowClient(run_metrics=run_metrics)
        orch = DeltaOneMintOrchestrator(
            evaluator=evaluator, mint_hook=mint_hook, mlflow_client=client
        )

        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", self._build_spec())
        assert outcome.status == "guardrail_breach"
        mint_hook.mint.assert_not_called()


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_extract_guardrail_specs_parses_correctly(self):
        spec = _make_spec_with_guardrails(
            [{"name": "accuracy", "direction": "higher_is_better", "threshold": 0.9}]
        )
        result = _extract_guardrail_specs(spec)
        assert len(result) == 1
        assert result[0].name == "accuracy"
        assert result[0].threshold == 0.9
        assert result[0].blocking is True

    def test_extract_guardrail_specs_empty(self):
        assert _extract_guardrail_specs({}) == []

    def test_extract_guardrail_observations(self):
        run = SimpleNamespace(data=SimpleNamespace(metrics={"accuracy": 0.92, "other": 1.0}))
        specs = [RuntimeGuardrailSpec(name="accuracy", direction="higher_is_better", threshold=0.9)]
        obs = _extract_guardrail_observations(run, specs)
        assert obs == {"accuracy": 0.92}

    def test_decision_to_comparator_result(self):
        decision = _make_decision(accepted=True)
        result = _decision_to_comparator_result(decision)
        assert isinstance(result, ComparatorResult)
        assert result.passed is True
        assert result.effect_size == decision.delta_percentage_points

    def test_build_blocked_reason_primary_fail(self):
        decision = _make_decision(accepted=False, reason="delta_below_threshold")
        guardrail_result = GuardrailResult(passed=True, breaches=())
        reason = _build_blocked_reason(decision, guardrail_result)
        assert "delta_below_threshold" in reason

    def test_build_blocked_reason_guardrail_breach(self):
        from src.evaluation.schema import GuardrailBreach

        decision = _make_decision(accepted=True)
        breach = GuardrailBreach(
            metric_name="cost",
            observed=0.5,
            threshold=0.1,
            direction="lower_is_better",
            policy="reject_mint",
            reason="cost exceeds threshold",
        )
        guardrail_result = GuardrailResult(passed=False, breaches=(breach,))
        reason = _build_blocked_reason(decision, guardrail_result)
        assert "cost" in reason

    def test_build_blocked_reason_both_fail(self):
        from src.evaluation.schema import GuardrailBreach

        decision = _make_decision(accepted=False, reason="not_statistically_significant")
        breach = GuardrailBreach(
            metric_name="cost",
            observed=0.5,
            threshold=0.1,
            direction="lower_is_better",
            policy="reject_mint",
            reason="cost exceeds threshold",
        )
        guardrail_result = GuardrailResult(passed=False, breaches=(breach,))
        reason = _build_blocked_reason(decision, guardrail_result)
        assert "not_statistically_significant" in reason
        assert "cost" in reason
