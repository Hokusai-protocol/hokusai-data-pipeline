"""Unit tests for DeltaOne confidence interval calculations."""

from __future__ import annotations

import pytest

from src.evaluation.deltaone_evaluator import DeltaOneEvaluator


def test_ci_significant_when_large_signal() -> None:
    evaluator = DeltaOneEvaluator(cooldown_hours=0)

    significant, ci_low, ci_high = evaluator._is_statistically_significant(
        baseline_metric=0.82,
        current_metric=0.87,
        baseline_n=12_000,
        current_n=12_000,
    )

    assert significant is True
    assert ci_low > 0.0
    assert ci_high > ci_low


def test_ci_not_significant_when_interval_crosses_zero() -> None:
    evaluator = DeltaOneEvaluator(cooldown_hours=0)

    significant, ci_low, ci_high = evaluator._is_statistically_significant(
        baseline_metric=0.85,
        current_metric=0.852,
        baseline_n=800,
        current_n=800,
    )

    assert significant is False
    assert ci_low < 0.0 < ci_high


@pytest.mark.parametrize(
    ("baseline_metric", "current_metric"),
    [(-0.1, 0.8), (0.8, 1.1)],
)
def test_ci_rejects_metrics_outside_proportion_bounds(
    baseline_metric: float,
    current_metric: float,
) -> None:
    evaluator = DeltaOneEvaluator(cooldown_hours=0)

    with pytest.raises(ValueError, match="proportion metrics"):
        evaluator._is_statistically_significant(
            baseline_metric=baseline_metric,
            current_metric=current_metric,
            baseline_n=1_000,
            current_n=1_000,
        )
