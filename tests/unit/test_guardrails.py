"""Tests for the guardrail evaluator."""

from __future__ import annotations

from src.evaluation.guardrails import evaluate_guardrails
from src.evaluation.schema import GuardrailResult
from src.evaluation.spec_translation import RuntimeGuardrailSpec


def _make_spec(
    name: str,
    direction: str = "higher_is_better",
    threshold: float = 0.8,
    blocking: bool = True,
) -> RuntimeGuardrailSpec:
    return RuntimeGuardrailSpec(
        name=name, direction=direction, threshold=threshold, blocking=blocking
    )


class TestEvaluateGuardrails:
    def test_pass_case_higher_is_better(self):
        spec = _make_spec("accuracy", direction="higher_is_better", threshold=0.8)
        result = evaluate_guardrails({"accuracy": 0.9}, [spec])
        assert result.passed is True
        assert result.breaches == ()

    def test_pass_case_lower_is_better(self):
        spec = _make_spec("latency_p99", direction="lower_is_better", threshold=200.0)
        result = evaluate_guardrails({"latency_p99": 150.0}, [spec])
        assert result.passed is True
        assert result.breaches == ()

    def test_single_breach_higher_is_better(self):
        spec = _make_spec("accuracy", direction="higher_is_better", threshold=0.9)
        result = evaluate_guardrails({"accuracy": 0.85}, [spec])
        assert result.passed is False
        assert len(result.breaches) == 1
        breach = result.breaches[0]
        assert breach.metric_name == "accuracy"
        assert breach.observed == 0.85
        assert breach.threshold == 0.9
        assert breach.direction == "higher_is_better"
        assert breach.policy == "reject_mint"
        assert "accuracy" in breach.reason

    def test_single_breach_lower_is_better(self):
        spec = _make_spec("error_rate", direction="lower_is_better", threshold=0.05)
        result = evaluate_guardrails({"error_rate": 0.10}, [spec])
        assert result.passed is False
        assert len(result.breaches) == 1
        breach = result.breaches[0]
        assert breach.metric_name == "error_rate"
        assert breach.policy == "reject_mint"

    def test_multiple_breaches(self):
        specs = [
            _make_spec("accuracy", direction="higher_is_better", threshold=0.9),
            _make_spec("error_rate", direction="lower_is_better", threshold=0.05),
        ]
        observations = {"accuracy": 0.85, "error_rate": 0.10}
        result = evaluate_guardrails(observations, specs)
        assert result.passed is False
        assert len(result.breaches) == 2

    def test_non_blocking_guardrail_does_not_produce_breach(self):
        spec = _make_spec("accuracy", direction="higher_is_better", threshold=0.9, blocking=False)
        result = evaluate_guardrails({"accuracy": 0.50}, [spec])
        assert result.passed is True
        assert result.breaches == ()

    def test_missing_observation_skipped(self):
        spec = _make_spec("accuracy", direction="higher_is_better", threshold=0.9)
        result = evaluate_guardrails({}, [spec])
        assert result.passed is True
        assert result.breaches == ()

    def test_all_breach_fields_populated(self):
        spec = _make_spec("workflow_success_rate", direction="higher_is_better", threshold=0.95)
        result = evaluate_guardrails({"workflow_success_rate": 0.80}, [spec])
        breach = result.breaches[0]
        assert breach.metric_name == "workflow_success_rate"
        assert isinstance(breach.observed, float)
        assert isinstance(breach.threshold, float)
        assert breach.direction in {"higher_is_better", "lower_is_better"}
        assert breach.policy == "reject_mint"
        assert isinstance(breach.reason, str) and len(breach.reason) > 0

    def test_mixed_blocking_and_non_blocking(self):
        specs = [
            _make_spec("strict_metric", direction="higher_is_better", threshold=0.9, blocking=True),
            _make_spec("soft_metric", direction="higher_is_better", threshold=0.95, blocking=False),
        ]
        observations = {"strict_metric": 0.95, "soft_metric": 0.80}
        result = evaluate_guardrails(observations, specs)
        assert result.passed is True
        assert result.breaches == ()

    def test_returns_guardrail_result_type(self):
        result = evaluate_guardrails({}, [])
        assert isinstance(result, GuardrailResult)
        assert result.passed is True
