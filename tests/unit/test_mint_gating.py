"""Tests for guardrail-gated DeltaOne mint orchestration.

Auth note: tests use fake MLflow clients only; no live MLflow requests are made.
Production auth relies on MLFLOW_TRACKING_TOKEN / Authorization env wiring.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

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

# Required fields for DeltaOneAcceptanceEvent construction
_MODEL_ID_UINT = "99001"
_EVAL_ID = "eval-test-001"
_SPEC_ID = "spec-test-v1"


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
        "model_id_uint": _MODEL_ID_UINT,
        "spec_id": _SPEC_ID,
        "eval_spec": {
            "primary_metric": {
                "name": "workflow_success_rate_under_budget",
                "direction": "higher_is_better",
            },
            "guardrails": guardrails,
        },
    }


def _make_client_with_eval_id(run_metrics=None, extra_tags=None):
    tags = {"hokusai.eval_id": _EVAL_ID}
    if extra_tags:
        tags.update(extra_tags)
    return _FakeMlflowClient(run_metrics=run_metrics or {}, initial_tags=tags)


# ---------------------------------------------------------------------------
# process_evaluation_with_spec: mint gating scenarios
# ---------------------------------------------------------------------------


class TestProcessEvaluationWithSpec:
    def _make_orchestrator(self, decision, run_metrics=None, monkeypatch=None):
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = decision
        evaluator.delta_threshold_pp = 1.0
        mint_hook = Mock()
        mint_hook.mint.return_value = TokenMintResult(
            status="success",
            audit_ref="audit-ok",
            timestamp=datetime.now(timezone.utc),
        )
        client = _make_client_with_eval_id(run_metrics=run_metrics or {})
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
        evaluator.delta_threshold_pp = 1.0
        mint_hook = Mock()
        mint_hook.mint.return_value = TokenMintResult(
            status="success", audit_ref="ok", timestamp=datetime.now(timezone.utc)
        )
        client = _make_client_with_eval_id(run_metrics=run_metrics)
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
        evaluator.delta_threshold_pp = 1.0
        mint_hook = Mock()
        client = _make_client_with_eval_id(run_metrics=run_metrics)
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


# ---------------------------------------------------------------------------
# DeltaOneAcceptanceEvent construction regression tests
# ---------------------------------------------------------------------------


class TestAcceptanceEventConstruction:
    """Verify that process_evaluation_with_spec produces a valid DeltaOneAcceptanceEvent."""

    def _make_orch_with_event_fields(self, run_metrics, monkeypatch):
        """Build an orchestrator with all required event fields set."""
        decision = _make_decision(accepted=True)
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = decision
        evaluator.delta_threshold_pp = 1.0
        mint_hook = Mock()
        mint_hook.mint.return_value = TokenMintResult(
            status="success", audit_ref="ok", timestamp=datetime.now(timezone.utc)
        )
        client = _make_client_with_eval_id(run_metrics=run_metrics)
        orch = DeltaOneMintOrchestrator(
            evaluator=evaluator, mint_hook=mint_hook, mlflow_client=client
        )
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(return_value=[]),
        )
        return orch, mint_hook, decision

    def test_accepted_spec_mint_produces_acceptance_event(self, monkeypatch):
        run_metrics = {"workflow_success_rate_under_budget": 0.87}
        orch, _, _ = self._make_orch_with_event_fields(run_metrics, monkeypatch)
        spec = _make_spec_with_guardrails([])
        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", spec)
        assert outcome.status == "success"
        assert outcome.acceptance_event is not None

    def test_acceptance_event_field_names_and_types(self, monkeypatch):
        from src.evaluation.event_payload import DeltaOneAcceptanceEvent, DeltaOneGuardrailSummary

        run_metrics = {"workflow_success_rate_under_budget": 0.87}
        orch, _, _ = self._make_orch_with_event_fields(run_metrics, monkeypatch)
        spec = _make_spec_with_guardrails([])
        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", spec)

        event = outcome.acceptance_event
        assert isinstance(event, DeltaOneAcceptanceEvent)
        assert event.event_version == "deltaone.acceptance/v1"
        assert isinstance(event.model_id, str)
        assert isinstance(event.model_id_uint, str)
        assert isinstance(event.eval_id, str)
        assert isinstance(event.mlflow_run_id, str)
        assert isinstance(event.benchmark_spec_id, str)
        assert isinstance(event.primary_metric_name, str)
        assert isinstance(event.primary_metric_mlflow_name, str)
        assert isinstance(event.metric_family, str)
        assert 0 <= event.baseline_score_bps <= 10000
        assert 0 <= event.candidate_score_bps <= 10000
        assert event.delta_bps == event.candidate_score_bps - event.baseline_score_bps
        assert 0 <= event.delta_threshold_bps <= 10000
        assert event.attestation_hash.startswith("0x")
        assert event.idempotency_key.startswith("0x")
        assert isinstance(event.guardrail_summary, DeltaOneGuardrailSummary)
        assert event.max_cost_usd_micro >= 0
        assert event.actual_cost_usd_micro >= 0

    def test_baseline_candidate_bps_derived_from_metrics(self, monkeypatch):
        from src.evaluation.event_payload import to_basis_points

        run_metrics = {"workflow_success_rate_under_budget": 0.87}
        orch, _, _ = self._make_orch_with_event_fields(run_metrics, monkeypatch)
        spec = _make_spec_with_guardrails([])
        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", spec)

        event = outcome.acceptance_event
        assert event is not None
        expected_bps = to_basis_points(0.87, "proportion")
        # Both candidate and baseline use same fake run data -> same score
        assert event.baseline_score_bps == expected_bps
        assert event.candidate_score_bps == expected_bps
        assert event.delta_bps == 0

    def test_primary_metric_mlflow_name_colon_normalized(self, monkeypatch):
        """colon in metric name is normalized to underscore for MLflow key."""
        decision = DeltaOneDecision(
            accepted=True,
            reason="accepted",
            run_id="run-cand",
            baseline_run_id="run-base",
            model_id="model-x",
            dataset_hash=HASH_A,
            metric_name="custom:accuracy",
            delta_percentage_points=2.0,
            ci95_low_percentage_points=0.5,
            ci95_high_percentage_points=3.5,
            n_current=1000,
            n_baseline=1000,
            evaluated_at=datetime.now(timezone.utc),
        )
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = decision
        evaluator.delta_threshold_pp = 1.0
        mint_hook = Mock()
        mint_hook.mint.return_value = TokenMintResult(
            status="success", audit_ref="ok", timestamp=datetime.now(timezone.utc)
        )
        # MLflow key uses underscore normalization: custom:accuracy -> custom_accuracy
        run_metrics = {"custom_accuracy": 0.90}
        client = _make_client_with_eval_id(run_metrics=run_metrics)
        orch = DeltaOneMintOrchestrator(
            evaluator=evaluator, mint_hook=mint_hook, mlflow_client=client
        )
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(return_value=[]),
        )
        spec = _make_spec_with_guardrails([])
        spec["eval_spec"]["primary_metric"]["name"] = "custom:accuracy"
        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", spec)

        event = outcome.acceptance_event
        assert event is not None
        assert event.primary_metric_name == "custom:accuracy"
        assert event.primary_metric_mlflow_name == "custom_accuracy"

    def test_guardrail_breach_summary_in_event(self, monkeypatch):
        """Guardrail breach details appear in the event guardrail_summary."""
        decision = _make_decision(accepted=True)
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = decision
        evaluator.delta_threshold_pp = 1.0
        mint_hook = Mock()
        mint_hook.mint.return_value = TokenMintResult(
            status="success", audit_ref="ok", timestamp=datetime.now(timezone.utc)
        )
        run_metrics = {"workflow_success_rate_under_budget": 0.87, "cost_per_call": 0.05}
        client = _make_client_with_eval_id(run_metrics=run_metrics)
        orch = DeltaOneMintOrchestrator(
            evaluator=evaluator, mint_hook=mint_hook, mlflow_client=client
        )
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(return_value=[]),
        )
        spec = _make_spec_with_guardrails(
            [{"name": "cost_per_call", "direction": "lower_is_better", "threshold": 0.10}]
        )
        outcome = orch.process_evaluation_with_spec("run-cand", "run-base", spec)
        assert outcome.acceptance_event is not None
        summary = outcome.acceptance_event.guardrail_summary
        assert summary.total_guardrails == 1
        assert summary.guardrails_passed == 1
        assert len(summary.breaches) == 0

    def test_missing_model_id_uint_prevents_mint(self, monkeypatch):
        """Missing model_id_uint raises EventPayloadError before mint."""
        from src.evaluation.event_payload import EventPayloadError

        decision = _make_decision(accepted=True)
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = decision
        evaluator.delta_threshold_pp = 1.0
        mint_hook = Mock()
        client = _make_client_with_eval_id(run_metrics={"workflow_success_rate_under_budget": 0.87})
        orch = DeltaOneMintOrchestrator(
            evaluator=evaluator, mint_hook=mint_hook, mlflow_client=client
        )
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(return_value=[]),
        )
        # Spec without model_id_uint
        spec = {
            "model_id": "model-x",
            "spec_id": _SPEC_ID,
            "eval_spec": {
                "primary_metric": {
                    "name": "workflow_success_rate_under_budget",
                    "direction": "higher_is_better",
                },
                "guardrails": [],
            },
        }
        with pytest.raises(EventPayloadError, match="model_id_uint"):
            orch.process_evaluation_with_spec("run-cand", "run-base", spec)

        mint_hook.mint.assert_not_called()

    def test_missing_eval_id_prevents_mint(self, monkeypatch):
        """Missing eval_id raises EventPayloadError before mint."""
        from src.evaluation.event_payload import EventPayloadError

        decision = _make_decision(accepted=True)
        evaluator = Mock()
        evaluator.evaluate_for_model.return_value = decision
        evaluator.delta_threshold_pp = 1.0
        mint_hook = Mock()
        # Client without hokusai.eval_id tag
        client = _FakeMlflowClient(
            run_metrics={"workflow_success_rate_under_budget": 0.87},
            initial_tags={},  # No eval_id
        )
        orch = DeltaOneMintOrchestrator(
            evaluator=evaluator, mint_hook=mint_hook, mlflow_client=client
        )
        monkeypatch.setattr(
            "src.evaluation.deltaone_mint_orchestrator.dispatch_deltaone_webhook_event",
            Mock(return_value=[]),
        )
        spec = _make_spec_with_guardrails([])
        with pytest.raises(EventPayloadError, match="eval_id"):
            orch.process_evaluation_with_spec("run-cand", "run-base", spec)

        mint_hook.mint.assert_not_called()

    def test_acceptance_event_in_mint_metadata(self, monkeypatch):
        """The acceptance event dict appears in mint_hook.mint metadata."""
        run_metrics = {"workflow_success_rate_under_budget": 0.87}
        orch, mint_hook, _ = self._make_orch_with_event_fields(run_metrics, monkeypatch)
        spec = _make_spec_with_guardrails([])
        orch.process_evaluation_with_spec("run-cand", "run-base", spec)

        call_kwargs = mint_hook.mint.call_args.kwargs
        assert "metadata" in call_kwargs
        assert "deltaone_acceptance_event" in call_kwargs["metadata"]
        event_data = call_kwargs["metadata"]["deltaone_acceptance_event"]
        assert event_data["event_version"] == "deltaone.acceptance/v1"
