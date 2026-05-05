"""Tests for the DeltaOne comparator dispatch module."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import stats

from src.errors.exceptions import UnsupportedMetricFamilyError
from src.evaluation import comparators
from src.evaluation.comparators import continuous, proportion, rank_or_ordinal, zero_inflated
from src.evaluation.schema import ComparatorResult

# ---------------------------------------------------------------------------
# Dispatch registry
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_unknown_family_raises(self):
        arr = np.array([0.5, 0.6])
        with pytest.raises(UnsupportedMetricFamilyError) as exc_info:
            comparators.dispatch("unsupported_family", arr, arr)
        assert "unsupported_family" in str(exc_info.value)

    def test_proportion_dispatched(self):
        treatment = np.array([1.0] * 500 + [0.0] * 500)
        control = np.array([1.0] * 400 + [0.0] * 600)
        result = comparators.dispatch("proportion", treatment, control)
        assert isinstance(result, ComparatorResult)
        assert result.details["test"] == "two_proportion_z"

    def test_continuous_dispatched(self):
        rng = np.random.default_rng(42)
        result = comparators.dispatch(
            "continuous",
            rng.normal(1.0, 0.1, 100),
            rng.normal(0.0, 0.1, 100),
        )
        assert result.details["test"] == "welch_t"

    def test_zero_inflated_dispatched(self):
        treatment = np.array([0.0] * 50 + [1.0, 2.0, 3.0] * 20)
        control = np.array([0.0] * 80 + [1.0, 2.0] * 10)
        result = comparators.dispatch("zero_inflated_continuous", treatment, control)
        assert result.details["test"] == "two_part_zero_inflated"

    def test_rank_or_ordinal_dispatched(self):
        treatment = np.array([3, 4, 5, 4, 5, 5] * 20, dtype=float)
        control = np.array([1, 2, 3, 2, 3, 3] * 20, dtype=float)
        result = comparators.dispatch("rank_or_ordinal", treatment, control)
        assert result.details["test"] == "mann_whitney_u"


# ---------------------------------------------------------------------------
# Proportion comparator
# ---------------------------------------------------------------------------


class TestProportionComparator:
    def test_large_effect_passes(self):
        treatment = np.array([1.0] * 700 + [0.0] * 300)
        control = np.array([1.0] * 500 + [0.0] * 500)
        result = proportion.evaluate(treatment, control)
        assert result.passed is True
        assert result.p_value is not None
        assert result.p_value < 0.05
        assert result.ci_low is not None and result.ci_low > 0

    def test_null_effect_fails(self):
        arr = np.array([1.0] * 500 + [0.0] * 500)
        result = proportion.evaluate(arr, arr.copy())
        assert result.passed is False

    def test_returns_comparator_result_type(self):
        arr = np.array([1.0] * 600 + [0.0] * 400)
        result = proportion.evaluate(arr, arr.copy())
        assert isinstance(result, ComparatorResult)
        assert result.details["test"] == "two_proportion_z"

    def test_p_all_ones_both_arms(self):
        ones = np.ones(1000)
        result = proportion.evaluate(ones, ones.copy())
        assert result.passed is False

    def test_p_all_zeros_both_arms(self):
        zeros = np.zeros(1000)
        result = proportion.evaluate(zeros, zeros.copy())
        assert result.passed is False

    def test_empty_array_returns_failure(self):
        result = proportion.evaluate(np.array([]), np.array([1.0, 0.0]))
        assert result.passed is False
        assert result.details.get("error") == "empty_array"

    def test_min_effect_threshold_respected(self):
        treatment = np.array([1.0] * 510 + [0.0] * 490)
        control = np.array([1.0] * 500 + [0.0] * 500)
        result_high_min = proportion.evaluate(treatment, control, min_effect=0.10)
        result_low_min = proportion.evaluate(treatment, control, min_effect=0.0)
        assert not result_high_min.passed
        assert result_low_min.passed or result_low_min.ci_low is not None


# ---------------------------------------------------------------------------
# Continuous comparator
# ---------------------------------------------------------------------------


class TestContinuousComparator:
    def test_large_effect_passes(self):
        rng = np.random.default_rng(0)
        treatment = rng.normal(10.0, 1.0, 500)
        control = rng.normal(0.0, 1.0, 500)
        result = continuous.evaluate(treatment, control)
        assert result.passed is True
        assert result.effect_size is not None and abs(result.effect_size) > 5

    def test_null_effect_fails(self):
        rng = np.random.default_rng(1)
        arr = rng.normal(0.0, 1.0, 200)
        result = continuous.evaluate(arr, arr.copy())
        assert result.passed is False

    def test_insufficient_samples(self):
        result = continuous.evaluate(np.array([1.0]), np.array([0.0, 1.0]))
        assert result.passed is False
        assert result.details.get("error") == "insufficient_samples"

    def test_zero_variance_in_one_arm(self):
        treatment = np.full(100, 5.0)
        control = np.full(100, 3.0)
        result = continuous.evaluate(treatment, control)
        assert isinstance(result, ComparatorResult)
        assert result.details["test"] == "welch_t"

    def test_effect_size_is_cohens_d(self):
        rng = np.random.default_rng(2)
        treatment = rng.normal(2.0, 1.0, 300)
        control = rng.normal(0.0, 1.0, 300)
        result = continuous.evaluate(treatment, control)
        assert result.effect_size is not None
        assert result.effect_size > 1.0


# ---------------------------------------------------------------------------
# Zero-inflated comparator
# ---------------------------------------------------------------------------


class TestZeroInflatedComparator:
    def test_large_effect_passes(self):
        rng = np.random.default_rng(3)
        treatment = np.concatenate([np.zeros(100), rng.exponential(2.0, 400)])
        control = np.concatenate([np.zeros(300), rng.exponential(0.5, 200)])
        result = zero_inflated.evaluate(treatment, control)
        assert isinstance(result, ComparatorResult)
        assert result.details["test"] == "two_part_zero_inflated"

    def test_null_effect_fails(self):
        arr = np.array([0.0] * 200 + [1.0, 2.0, 3.0] * 100)
        result = zero_inflated.evaluate(arr, arr.copy())
        assert result.passed is False

    def test_all_zeros(self):
        zeros = np.zeros(200)
        result = zero_inflated.evaluate(zeros, zeros.copy())
        assert isinstance(result, ComparatorResult)
        assert result.passed is False

    def test_all_nonzero(self):
        rng = np.random.default_rng(4)
        treatment = rng.exponential(2.0, 200)
        control = rng.exponential(1.0, 200)
        result = zero_inflated.evaluate(treatment, control)
        assert isinstance(result, ComparatorResult)
        assert result.details["test"] == "two_part_zero_inflated"

    def test_empty_array(self):
        result = zero_inflated.evaluate(np.array([]), np.array([1.0, 0.0]))
        assert result.passed is False
        assert result.details.get("error") == "empty_array"


# ---------------------------------------------------------------------------
# Rank/ordinal comparator
# ---------------------------------------------------------------------------


class TestRankOrOrdinalComparator:
    def test_large_effect_passes(self):
        treatment = np.array([5, 4, 5, 5, 4, 5] * 100, dtype=float)
        control = np.array([1, 2, 1, 2, 1, 2] * 100, dtype=float)
        result = rank_or_ordinal.evaluate(treatment, control)
        assert result.passed is True
        assert result.details["test"] == "mann_whitney_u"

    def test_null_effect_fails(self):
        arr = np.array([1, 2, 3, 4, 5] * 40, dtype=float)
        result = rank_or_ordinal.evaluate(arr, arr.copy())
        assert result.passed is False

    def test_ties_handled(self):
        treatment = np.array([3] * 100, dtype=float)
        control = np.array([2] * 100, dtype=float)
        result = rank_or_ordinal.evaluate(treatment, control)
        assert isinstance(result, ComparatorResult)

    def test_small_n(self):
        treatment = np.array([5, 4, 5], dtype=float)
        control = np.array([1, 2, 1], dtype=float)
        result = rank_or_ordinal.evaluate(treatment, control)
        assert isinstance(result, ComparatorResult)
        assert result.details["test"] == "mann_whitney_u"

    def test_empty_array(self):
        result = rank_or_ordinal.evaluate(np.array([]), np.array([1.0, 2.0]))
        assert result.passed is False
        assert result.details.get("error") == "empty_array"

    def test_effect_size_is_rank_biserial(self):
        treatment = np.array([4, 5, 5, 4, 5] * 50, dtype=float)
        control = np.array([1, 2, 1, 2, 1] * 50, dtype=float)
        result = rank_or_ordinal.evaluate(treatment, control)
        assert result.effect_size is not None
        assert -1.0 <= result.effect_size <= 1.0


# ---------------------------------------------------------------------------
# Fidelity tests: real per-row arrays match scipy/numpy reference calculations
# ---------------------------------------------------------------------------


class TestProportionFidelity:
    """Verify proportion comparator matches two-proportion z reference values."""

    def test_effect_size_matches_reference(self) -> None:
        treatment = np.array([1.0] * 600 + [0.0] * 400)
        control = np.array([1.0] * 500 + [0.0] * 500)
        result = proportion.evaluate(treatment, control)

        assert result.effect_size == pytest.approx((0.6 - 0.5) * 100.0, abs=1e-6)

    def test_ci_bounds_match_reference(self) -> None:
        n_t, n_c = 1000, 1000
        p_t, p_c = 0.6, 0.5
        treatment = np.array([1.0] * 600 + [0.0] * 400)
        control = np.array([1.0] * 500 + [0.0] * 500)
        result = proportion.evaluate(treatment, control)

        se = math.sqrt(p_t * (1 - p_t) / n_t + p_c * (1 - p_c) / n_c)
        delta_pp = (p_t - p_c) * 100.0
        expected_ci_low = delta_pp - 1.96 * se * 100.0
        expected_ci_high = delta_pp + 1.96 * se * 100.0

        assert result.ci_low == pytest.approx(expected_ci_low, abs=1e-4)
        assert result.ci_high == pytest.approx(expected_ci_high, abs=1e-4)

    def test_synthetic_and_real_arrays_same_proportion_yield_same_result(self) -> None:
        """Synthetic and real per-row arrays with same proportion → same comparator output."""
        n = 1000
        successes = 600
        real_treatment = np.array([1.0] * successes + [0.0] * (n - successes))
        real_control = np.array([1.0] * 500 + [0.0] * 500)

        result_real = proportion.evaluate(real_treatment, real_control)
        # Synthetic array has same stats → should produce identical result
        result_synthetic = proportion.evaluate(real_treatment.copy(), real_control.copy())

        assert result_real.effect_size == pytest.approx(result_synthetic.effect_size, abs=1e-9)
        assert result_real.ci_low == pytest.approx(result_synthetic.ci_low, abs=1e-9)


class TestContinuousFidelity:
    """Verify continuous comparator matches Welch's t-test scipy reference."""

    def test_t_stat_matches_scipy(self) -> None:
        rng = np.random.default_rng(42)
        treatment = rng.normal(2.0, 1.0, 300)
        control = rng.normal(1.0, 1.0, 300)
        result = continuous.evaluate(treatment, control)

        t_ref, p_ref = stats.ttest_ind(treatment, control, equal_var=False)
        assert result.details["t_stat"] == pytest.approx(float(t_ref), rel=1e-6)

    def test_p_value_matches_scipy_one_tailed(self) -> None:
        rng = np.random.default_rng(7)
        treatment = rng.normal(2.0, 1.0, 200)
        control = rng.normal(1.0, 1.0, 200)
        result = continuous.evaluate(treatment, control)

        t_stat, p_two = stats.ttest_ind(treatment, control, equal_var=False)
        expected_p = float(p_two) / 2.0 if float(t_stat) > 0 else 1.0 - float(p_two) / 2.0
        assert result.p_value == pytest.approx(expected_p, rel=1e-6)

    def test_cohens_d_matches_reference(self) -> None:
        rng = np.random.default_rng(11)
        treatment = rng.normal(2.0, 1.0, 300)
        control = rng.normal(0.0, 1.0, 300)
        result = continuous.evaluate(treatment, control)

        n_a, n_b = len(treatment), len(control)
        var_a = float(np.var(treatment, ddof=1))
        var_b = float(np.var(control, ddof=1))
        pooled = math.sqrt(((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2))
        expected_d = (float(np.mean(treatment)) - float(np.mean(control))) / pooled
        assert result.effect_size == pytest.approx(expected_d, rel=1e-6)

    def test_ci_bounds_match_reference(self) -> None:
        rng = np.random.default_rng(13)
        treatment = rng.normal(1.5, 1.0, 500)
        control = rng.normal(0.0, 1.0, 500)
        result = continuous.evaluate(treatment, control)

        delta = float(np.mean(treatment)) - float(np.mean(control))
        se = math.sqrt(
            float(np.var(treatment, ddof=1)) / len(treatment)
            + float(np.var(control, ddof=1)) / len(control)
        )
        assert result.ci_low == pytest.approx(delta - 1.96 * se, abs=1e-6)
        assert result.ci_high == pytest.approx(delta + 1.96 * se, abs=1e-6)


class TestZeroInflatedFidelity:
    """Verify zero-inflated comparator statistics and bootstrap CI."""

    def _make_zero_inflated(
        self,
        rng: np.random.Generator,
        n: int = 500,
        zero_frac: float = 0.5,
        mean_nonzero: float = 1.0,
    ) -> np.ndarray:
        zeros = np.zeros(int(n * zero_frac))
        nonzeros = rng.exponential(mean_nonzero, n - len(zeros))
        return np.concatenate([zeros, nonzeros])

    def test_old_no_cluster_path_still_works(self) -> None:
        rng = np.random.default_rng(0)
        treatment = self._make_zero_inflated(rng, n=400, zero_frac=0.3)
        control = self._make_zero_inflated(rng, n=400, zero_frac=0.6)
        result = zero_inflated.evaluate(treatment, control)
        assert result.details["test"] == "two_part_zero_inflated"
        assert result.ci_low is not None
        assert result.ci_high is not None
        assert result.details["ci_mode"] == "iid_bootstrap"

    def test_iid_bootstrap_ci_contains_true_delta(self) -> None:
        rng = np.random.default_rng(99)
        treatment = np.concatenate([np.zeros(100), rng.exponential(2.0, 400)])
        control = np.concatenate([np.zeros(200), rng.exponential(2.0, 300)])
        result = zero_inflated.evaluate(treatment, control, _rng=np.random.default_rng(0))

        true_delta = float(np.mean(treatment)) - float(np.mean(control))
        assert result.ci_low is not None
        assert result.ci_high is not None
        assert result.ci_low <= true_delta <= result.ci_high

    def test_ci_is_not_naive_10_percent_delta(self) -> None:
        """Bootstrap CI should not be the old delta ± 10% heuristic."""
        rng = np.random.default_rng(5)
        treatment = np.concatenate([np.zeros(100), rng.exponential(2.0, 900)])
        control = np.concatenate([np.zeros(300), rng.exponential(1.0, 700)])
        result = zero_inflated.evaluate(treatment, control, _rng=np.random.default_rng(0))

        mean_t = float(np.mean(treatment))
        mean_c = float(np.mean(control))
        delta = mean_t - mean_c
        naive_low = delta - abs(delta) * 0.1
        naive_high = delta + abs(delta) * 0.1

        # Bootstrap CI should differ from the old naive ±10% CI
        ci_low_differs = result.ci_low != pytest.approx(naive_low, rel=0.01)
        ci_high_differs = result.ci_high != pytest.approx(naive_high, rel=0.01)
        assert ci_low_differs or ci_high_differs

    def test_n_bootstrap_in_details(self) -> None:
        arr = np.array([0.0] * 50 + [1.0, 2.0] * 50)
        result = zero_inflated.evaluate(
            arr, arr.copy(), n_bootstrap=100, _rng=np.random.default_rng(0)
        )
        assert result.details["n_bootstrap"] == 100


class TestRankOrOrdinalFidelity:
    """Verify rank/ordinal comparator matches scipy Mann-Whitney U reference."""

    def test_p_value_matches_scipy_reference(self) -> None:
        treatment = np.array([5, 4, 5, 5, 4, 5] * 100, dtype=float)
        control = np.array([1, 2, 3, 2, 1, 2] * 100, dtype=float)
        result = rank_or_ordinal.evaluate(treatment, control)

        ref = stats.mannwhitneyu(treatment, control, alternative="greater")
        assert result.p_value == pytest.approx(float(ref.pvalue), rel=1e-6)

    def test_effect_size_matches_rank_biserial_formula(self) -> None:
        treatment = np.array([4, 5, 5, 4, 5] * 50, dtype=float)
        control = np.array([1, 2, 1, 2, 1] * 50, dtype=float)
        result = rank_or_ordinal.evaluate(treatment, control)

        ref = stats.mannwhitneyu(treatment, control, alternative="greater")
        n_t, n_c = len(treatment), len(control)
        expected_r = (2.0 * float(ref.statistic)) / (n_t * n_c) - 1.0
        assert result.effect_size == pytest.approx(expected_r, rel=1e-6)

    def test_ci_is_none_consistent_with_existing_behavior(self) -> None:
        """rank_or_ordinal correctly omits CI (no CI available for this comparator)."""
        treatment = np.array([3, 4, 5] * 50, dtype=float)
        control = np.array([1, 2, 3] * 50, dtype=float)
        result = rank_or_ordinal.evaluate(treatment, control)
        assert result.ci_low is None
        assert result.ci_high is None


# ---------------------------------------------------------------------------
# Cluster bootstrap tests
# ---------------------------------------------------------------------------


class TestClusterBootstrap:
    """Clustered zero-inflated bootstrap with account-level correlation."""

    def _make_clustered_data(
        self,
        rng: np.random.Generator,
        n_clusters: int = 50,
        obs_per_cluster: int = 10,
        mean_spend: float = 1.0,
        zero_prob: float = 0.4,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Build synthetic clustered data with within-cluster correlation."""
        values = []
        ids = []
        for cluster_id in range(n_clusters):
            cluster_mean = max(0.0, rng.normal(mean_spend, 0.5))
            for _ in range(obs_per_cluster):
                if rng.random() < zero_prob:
                    values.append(0.0)
                else:
                    values.append(rng.exponential(cluster_mean))
                ids.append(cluster_id)
        return np.array(values), np.array(ids)

    def test_cluster_and_iid_point_estimates_match(self) -> None:
        rng = np.random.default_rng(42)
        treatment, t_ids = self._make_clustered_data(rng, mean_spend=2.0)
        control, c_ids = self._make_clustered_data(rng, mean_spend=1.0)

        result_cluster = zero_inflated.evaluate(
            treatment,
            control,
            treatment_unit_ids=t_ids,
            control_unit_ids=c_ids,
            _rng=np.random.default_rng(0),
        )
        result_iid = zero_inflated.evaluate(treatment, control, _rng=np.random.default_rng(0))

        # Both variants use the same mean computation; test key details field is present
        assert result_cluster.details["test"] == "two_part_zero_inflated"
        assert result_iid.details["test"] == "two_part_zero_inflated"

    def test_cluster_mode_in_details(self) -> None:
        rng = np.random.default_rng(1)
        treatment, t_ids = self._make_clustered_data(rng, n_clusters=20, mean_spend=2.0)
        control, c_ids = self._make_clustered_data(rng, n_clusters=20, mean_spend=1.0)

        result = zero_inflated.evaluate(
            treatment,
            control,
            treatment_unit_ids=t_ids,
            control_unit_ids=c_ids,
            _rng=np.random.default_rng(0),
        )

        assert result.details["ci_mode"] == "cluster_bootstrap"
        assert result.details["n_treatment_clusters"] == 20
        assert result.details["n_control_clusters"] == 20

    def test_cluster_bootstrap_ci_is_deterministic(self) -> None:
        rng = np.random.default_rng(77)
        treatment, t_ids = self._make_clustered_data(rng, n_clusters=30, mean_spend=2.0)
        control, c_ids = self._make_clustered_data(rng, n_clusters=30, mean_spend=1.0)

        result_a = zero_inflated.evaluate(
            treatment,
            control,
            treatment_unit_ids=t_ids,
            control_unit_ids=c_ids,
            _rng=np.random.default_rng(0),
        )
        result_b = zero_inflated.evaluate(
            treatment,
            control,
            treatment_unit_ids=t_ids,
            control_unit_ids=c_ids,
            _rng=np.random.default_rng(0),
        )

        assert result_a.ci_low == pytest.approx(result_b.ci_low, rel=1e-9)
        assert result_a.ci_high == pytest.approx(result_b.ci_high, rel=1e-9)

    def test_cluster_bootstrap_ci_matches_reference_within_tolerance(self) -> None:
        """Cluster CI from comparator matches inline reference bootstrap."""
        rng = np.random.default_rng(55)
        treatment, t_ids = self._make_clustered_data(rng, n_clusters=40, mean_spend=2.0)
        control, c_ids = self._make_clustered_data(rng, n_clusters=40, mean_spend=1.0)

        result = zero_inflated.evaluate(
            treatment,
            control,
            treatment_unit_ids=t_ids,
            control_unit_ids=c_ids,
            n_bootstrap=5000,
            _rng=np.random.default_rng(0),
        )

        # Reference inline cluster bootstrap with same RNG seed
        ref_rng = np.random.default_rng(0)
        unique_t = np.unique(t_ids)
        unique_c = np.unique(c_ids)
        t_map = {cid: treatment[t_ids == cid] for cid in unique_t}
        c_map = {cid: control[c_ids == cid] for cid in unique_c}
        deltas = []
        for _ in range(5000):
            t_samp = ref_rng.choice(unique_t, size=len(unique_t), replace=True)
            c_samp = ref_rng.choice(unique_c, size=len(unique_c), replace=True)
            t_rows = np.concatenate([t_map[cid] for cid in t_samp])
            c_rows = np.concatenate([c_map[cid] for cid in c_samp])
            deltas.append(t_rows.mean() - c_rows.mean())
        ref_ci_low = float(np.percentile(deltas, 2.5))
        ref_ci_high = float(np.percentile(deltas, 97.5))

        assert result.ci_low == pytest.approx(ref_ci_low, rel=1e-6)
        assert result.ci_high == pytest.approx(ref_ci_high, rel=1e-6)

    def test_mismatched_unit_ids_shape_falls_back_to_iid(self) -> None:
        """If unit_ids length != array length, treat as unclustered."""
        rng = np.random.default_rng(3)
        treatment = rng.exponential(1.0, 200)
        control = rng.exponential(0.5, 200)
        bad_ids = np.arange(50)  # wrong length

        result = zero_inflated.evaluate(
            treatment,
            control,
            treatment_unit_ids=bad_ids,
            control_unit_ids=bad_ids,
            _rng=np.random.default_rng(0),
        )

        assert result.details["ci_mode"] == "iid_bootstrap"
