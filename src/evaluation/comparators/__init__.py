"""Comparator dispatch registry for DeltaOne statistical evaluation."""

from __future__ import annotations

from typing import Callable

import numpy as np

from src.errors.exceptions import UnsupportedMetricFamilyError
from src.evaluation.comparators import continuous, proportion, rank_or_ordinal, zero_inflated
from src.evaluation.schema import ComparatorResult

COMPARATOR_REGISTRY: dict[str, Callable[..., ComparatorResult]] = {
    "proportion": proportion.evaluate,
    "continuous": continuous.evaluate,
    "zero_inflated_continuous": zero_inflated.evaluate,
    "rank_or_ordinal": rank_or_ordinal.evaluate,
}


def dispatch(
    metric_family: str,
    treatment: np.ndarray,
    control: np.ndarray,
    **kwargs: object,
) -> ComparatorResult:
    """Dispatch to the appropriate comparator for the given metric_family."""
    fn = COMPARATOR_REGISTRY.get(metric_family)
    if fn is None:
        raise UnsupportedMetricFamilyError(metric_family)
    return fn(treatment, control, **kwargs)
