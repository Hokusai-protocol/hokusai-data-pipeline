"""Two-proportion z-test comparator for binary (0/1) proportion metrics."""

from __future__ import annotations

import math

import numpy as np

from src.evaluation.schema import ComparatorResult


def evaluate(
    treatment: np.ndarray,
    control: np.ndarray,
    *,
    alpha: float = 0.05,
    min_effect: float = 0.0,
    alternative: str = "greater",
) -> ComparatorResult:
    """Return a ComparatorResult for binary proportion arrays.

    Uses a two-proportion z-test.  The ``alternative`` parameter is kept for
    interface consistency but only ``"greater"`` (treatment > control) is
    tested: significance requires the lower CI bound to be above zero.
    """
    n_t = len(treatment)
    n_c = len(control)
    if n_t == 0 or n_c == 0:
        return ComparatorResult(
            passed=False,
            p_value=None,
            effect_size=None,
            ci_low=None,
            ci_high=None,
            details={"test": "two_proportion_z", "error": "empty_array"},
        )

    p_t = float(np.mean(treatment))
    p_c = float(np.mean(control))

    se_t = math.sqrt((p_t * (1.0 - p_t)) / n_t)
    se_c = math.sqrt((p_c * (1.0 - p_c)) / n_c)
    combined_se = math.sqrt(se_t**2 + se_c**2)

    delta_pp = (p_t - p_c) * 100.0
    effect_size = delta_pp

    if combined_se == 0.0:
        z_score = float("inf") if delta_pp > 0 else float("-inf")
        p_value = 0.0 if delta_pp > 0 else 1.0
        margin_pp = 0.0
    else:
        z_critical = 1.96
        margin_pp = z_critical * combined_se * 100.0
        z_score = delta_pp / (combined_se * 100.0)
        p_value = _one_tailed_p(z_score)

    ci_low = delta_pp - margin_pp
    ci_high = delta_pp + margin_pp

    passed = ci_low > 0.0 and delta_pp >= min_effect * 100.0

    return ComparatorResult(
        passed=passed,
        p_value=p_value,
        effect_size=effect_size,
        ci_low=ci_low,
        ci_high=ci_high,
        details={
            "test": "two_proportion_z",
            "z_score": z_score,
            "n_treatment": n_t,
            "n_control": n_c,
        },
    )


def _one_tailed_p(z: float) -> float:
    """Approximate one-tailed p-value from z-score (upper tail)."""
    import math as _math

    return 1.0 - 0.5 * (1.0 + _math.erf(z / _math.sqrt(2.0)))
