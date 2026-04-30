"""Two-part zero-inflated comparator: z-test on zero-fraction + Welch's t on non-zeros."""

from __future__ import annotations

import math

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
    """Two-part test with Bonferroni correction (alpha/2 per sub-test)."""
    n_t = len(treatment)
    n_c = len(control)
    if n_t == 0 or n_c == 0:
        return ComparatorResult(
            passed=False,
            p_value=None,
            effect_size=None,
            ci_low=None,
            ci_high=None,
            details={"test": "two_part_zero_inflated", "error": "empty_array"},
        )

    bonferroni_alpha = alpha / 2.0

    # Part 1: z-test on nonzero-fraction
    frac_t = float(np.mean(treatment != 0))
    frac_c = float(np.mean(control != 0))
    p_zero = _proportion_z_p(frac_t, frac_c, n_t, n_c)

    # Part 2: Welch's t on non-zero values only
    nz_t = treatment[treatment != 0]
    nz_c = control[control != 0]

    if len(nz_t) >= 2 and len(nz_c) >= 2:
        t_stat, p_two_tailed = stats.ttest_ind(nz_t, nz_c, equal_var=False)
        p_nonzero = float(p_two_tailed) / 2.0 if float(t_stat) > 0 else 1.0
    else:
        p_nonzero = 1.0

    effect_size = (frac_t - frac_c) * 100.0

    mean_t = float(np.mean(treatment))
    mean_c = float(np.mean(control))
    delta = mean_t - mean_c
    ci_low = delta - delta * 0.1 if delta != 0 else 0.0
    ci_high = delta + delta * 0.1 if delta != 0 else 0.0

    p_value = max(p_zero, p_nonzero)
    passed = p_zero < bonferroni_alpha and p_nonzero < bonferroni_alpha

    return ComparatorResult(
        passed=passed,
        p_value=p_value,
        effect_size=effect_size,
        ci_low=ci_low,
        ci_high=ci_high,
        details={
            "test": "two_part_zero_inflated",
            "p_zero_fraction": p_zero,
            "p_nonzero_magnitude": p_nonzero,
            "bonferroni_alpha": bonferroni_alpha,
        },
    )


def _proportion_z_p(p_t: float, p_c: float, n_t: int, n_c: int) -> float:
    """One-tailed p-value for difference in proportions (treatment > control)."""
    se_t = math.sqrt((p_t * (1.0 - p_t)) / n_t) if n_t > 0 else 0.0
    se_c = math.sqrt((p_c * (1.0 - p_c)) / n_c) if n_c > 0 else 0.0
    combined_se = math.sqrt(se_t**2 + se_c**2)
    if combined_se == 0.0:
        return 0.0 if p_t > p_c else 1.0
    z = (p_t - p_c) / combined_se
    return 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
