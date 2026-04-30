"""Welch's t-test comparator for continuous metrics."""

from __future__ import annotations

import numpy as np
from scipy import stats

from src.evaluation.schema import ComparatorResult


def evaluate(
    treatment: np.ndarray,
    control: np.ndarray,
    *,
    alpha: float = 0.05,
    min_effect: float = 0.0,
    alternative: str = "greater",
) -> ComparatorResult:
    """Return a ComparatorResult using Welch's t-test (unequal variances)."""
    n_t = len(treatment)
    n_c = len(control)
    if n_t < 2 or n_c < 2:
        return ComparatorResult(
            passed=False,
            p_value=None,
            effect_size=None,
            ci_low=None,
            ci_high=None,
            details={"test": "welch_t", "error": "insufficient_samples"},
        )

    mean_t = float(np.mean(treatment))
    mean_c = float(np.mean(control))

    t_stat, p_two_tailed = stats.ttest_ind(treatment, control, equal_var=False)
    p_value = float(p_two_tailed) / 2.0 if float(t_stat) > 0 else 1.0 - float(p_two_tailed) / 2.0

    effect_size = _cohens_d(treatment, control)

    delta = mean_t - mean_c
    se = float(np.sqrt(np.var(treatment, ddof=1) / n_t + np.var(control, ddof=1) / n_c))
    ci_low = delta - 1.96 * se
    ci_high = delta + 1.96 * se

    passed = p_value < alpha and delta >= min_effect

    return ComparatorResult(
        passed=passed,
        p_value=p_value,
        effect_size=effect_size,
        ci_low=ci_low,
        ci_high=ci_high,
        details={"test": "welch_t", "t_stat": float(t_stat), "n_treatment": n_t, "n_control": n_c},
    )


def _cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """Pooled Cohen's d effect size."""
    n_a, n_b = len(a), len(b)
    var_a = float(np.var(a, ddof=1))
    var_b = float(np.var(b, ddof=1))
    pooled_sd = float(np.sqrt(((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2)))
    if pooled_sd == 0.0:
        return 0.0
    return float((np.mean(a) - np.mean(b)) / pooled_sd)
