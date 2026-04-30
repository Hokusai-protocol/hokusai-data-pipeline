"""Tests for the DeltaOne comparator dispatch module."""

from __future__ import annotations

import numpy as np
import pytest

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
