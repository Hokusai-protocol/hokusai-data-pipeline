"""Two-part zero-inflated comparator: z-test on zero-fraction + Welch's t on non-zeros."""

from __future__ import annotations

import math

import numpy as np
from scipy import stats

from src.evaluation.schema import ComparatorResult

_DEFAULT_N_BOOTSTRAP = 2000


def evaluate(
    treatment: np.ndarray,
    control: np.ndarray,
    *,
    alpha: float = 0.05,
    min_effect: float = 0.0,
    alternative: str = "greater",
    treatment_unit_ids: np.ndarray | None = None,
    control_unit_ids: np.ndarray | None = None,
    n_bootstrap: int = _DEFAULT_N_BOOTSTRAP,
    _rng: np.random.Generator | None = None,
) -> ComparatorResult:
    """Two-part test with Bonferroni correction (alpha/2 per sub-test).

    CI for the mean delta is computed via bootstrap:
    - cluster bootstrap when ``treatment_unit_ids`` and ``control_unit_ids`` are both provided.
    - IID bootstrap otherwise.
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

    rng = _rng if _rng is not None else np.random.default_rng(0)

    use_cluster = (
        treatment_unit_ids is not None
        and control_unit_ids is not None
        and len(treatment_unit_ids) == n_t
        and len(control_unit_ids) == n_c
    )

    if use_cluster:
        ci_low, ci_high = _cluster_bootstrap_ci(
            treatment,
            control,
            treatment_unit_ids,  # type: ignore[arg-type]
            control_unit_ids,  # type: ignore[arg-type]
            alpha=alpha,
            n_bootstrap=n_bootstrap,
            rng=rng,
        )
        ci_mode = "cluster_bootstrap"
        n_t_clusters = int(len(np.unique(treatment_unit_ids)))  # type: ignore[arg-type]
        n_c_clusters = int(len(np.unique(control_unit_ids)))  # type: ignore[arg-type]
    else:
        ci_low, ci_high = _iid_bootstrap_ci(
            treatment,
            control,
            alpha=alpha,
            n_bootstrap=n_bootstrap,
            rng=rng,
        )
        ci_mode = "iid_bootstrap"
        n_t_clusters = None
        n_c_clusters = None

    p_value = max(p_zero, p_nonzero)
    passed = p_zero < bonferroni_alpha and p_nonzero < bonferroni_alpha

    details: dict[str, object] = {
        "test": "two_part_zero_inflated",
        "p_zero_fraction": p_zero,
        "p_nonzero_magnitude": p_nonzero,
        "bonferroni_alpha": bonferroni_alpha,
        "ci_mode": ci_mode,
        "n_bootstrap": n_bootstrap,
    }
    if n_t_clusters is not None:
        details["n_treatment_clusters"] = n_t_clusters
        details["n_control_clusters"] = n_c_clusters

    return ComparatorResult(
        passed=passed,
        p_value=p_value,
        effect_size=effect_size,
        ci_low=ci_low,
        ci_high=ci_high,
        details=details,
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


def _iid_bootstrap_ci(
    treatment: np.ndarray,
    control: np.ndarray,
    *,
    alpha: float,
    n_bootstrap: int,
    rng: np.random.Generator,
) -> tuple[float, float]:
    """Vectorized IID bootstrap CI for mean difference (treatment - control)."""
    n_t, n_c = len(treatment), len(control)
    t_idx = rng.integers(0, n_t, size=(n_bootstrap, n_t))
    c_idx = rng.integers(0, n_c, size=(n_bootstrap, n_c))
    deltas = treatment[t_idx].mean(axis=1) - control[c_idx].mean(axis=1)
    ci_low = float(np.percentile(deltas, 100.0 * alpha / 2.0))
    ci_high = float(np.percentile(deltas, 100.0 * (1.0 - alpha / 2.0)))
    return ci_low, ci_high


def _cluster_bootstrap_ci(
    treatment: np.ndarray,
    control: np.ndarray,
    treatment_unit_ids: np.ndarray,
    control_unit_ids: np.ndarray,
    *,
    alpha: float,
    n_bootstrap: int,
    rng: np.random.Generator,
) -> tuple[float, float]:
    """Cluster bootstrap CI for mean difference (treatment - control).

    Resamples unique cluster IDs with replacement per arm, concatenates all
    rows from selected clusters, and computes ``mean(treatment) - mean(control)``.
    Percentile CI bounds are returned.
    """
    unique_t = np.unique(treatment_unit_ids)
    unique_c = np.unique(control_unit_ids)
    n_t_clusters = len(unique_t)
    n_c_clusters = len(unique_c)

    t_cluster_map = {cid: treatment[treatment_unit_ids == cid] for cid in unique_t}
    c_cluster_map = {cid: control[control_unit_ids == cid] for cid in unique_c}

    deltas = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        t_sampled = rng.choice(unique_t, size=n_t_clusters, replace=True)
        c_sampled = rng.choice(unique_c, size=n_c_clusters, replace=True)
        t_rows = np.concatenate([t_cluster_map[cid] for cid in t_sampled])
        c_rows = np.concatenate([c_cluster_map[cid] for cid in c_sampled])
        deltas[i] = t_rows.mean() - c_rows.mean()

    ci_low = float(np.percentile(deltas, 100.0 * alpha / 2.0))
    ci_high = float(np.percentile(deltas, 100.0 * (1.0 - alpha / 2.0)))
    return ci_low, ci_high
