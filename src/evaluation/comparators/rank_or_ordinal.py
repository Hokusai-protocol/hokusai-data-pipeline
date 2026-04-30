"""Mann-Whitney U comparator for rank or ordinal metrics."""

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
    """Return a ComparatorResult using Mann-Whitney U test."""
    n_t = len(treatment)
    n_c = len(control)
    if n_t == 0 or n_c == 0:
        return ComparatorResult(
            passed=False,
            p_value=None,
            effect_size=None,
            ci_low=None,
            ci_high=None,
            details={"test": "mann_whitney_u", "error": "empty_array"},
        )

    mw_alternative = "greater" if alternative == "greater" else alternative
    try:
        result = stats.mannwhitneyu(treatment, control, alternative=mw_alternative)
        u_stat = float(result.statistic)
        p_value = float(result.pvalue)
    except ValueError:
        return ComparatorResult(
            passed=False,
            p_value=1.0,
            effect_size=0.0,
            ci_low=None,
            ci_high=None,
            details={"test": "mann_whitney_u", "error": "test_failed"},
        )

    effect_size = _rank_biserial_r(u_stat, n_t, n_c)

    passed = p_value < alpha and effect_size >= min_effect

    return ComparatorResult(
        passed=passed,
        p_value=p_value,
        effect_size=effect_size,
        ci_low=None,
        ci_high=None,
        details={
            "test": "mann_whitney_u",
            "u_statistic": u_stat,
            "n_treatment": n_t,
            "n_control": n_c,
        },
    )


def _rank_biserial_r(u_stat: float, n_t: int, n_c: int) -> float:
    """Rank-biserial correlation as effect size for Mann-Whitney U."""
    return (2.0 * u_stat) / (n_t * n_c) - 1.0
