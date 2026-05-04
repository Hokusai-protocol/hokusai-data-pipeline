"""Built-in deterministic scorers registered at import time."""

from __future__ import annotations

from src.evaluation.scorers.metadata import Aggregation, MetricFamily
from src.evaluation.scorers.registry import register_scorer

_INPUT_SCHEMA = {"type": "array", "items": {"type": "number"}}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _sum(values: list[float]) -> float:
    return sum(values)


def _pass_rate(values: list[float]) -> float:
    return sum(1.0 for v in values if v > 0) / len(values) if values else 0.0


def _min(values: list[float]) -> float:
    return min(values) if values else 0.0


def _max(values: list[float]) -> float:
    return max(values) if values else 0.0


def _mean_per_n(values: list[float], n: float) -> float:
    return (sum(values) / len(values) * n) if values else 0.0


def _mean_per_hundred(values: list[float]) -> float:
    return _mean_per_n(values, 100)


def _mean_per_thousand(values: list[float]) -> float:
    return _mean_per_n(values, 1000)


def _mean_per_ten_thousand(values: list[float]) -> float:
    return _mean_per_n(values, 10000)


_OUTCOME_SCORERS = [
    ("mean", _mean, Aggregation.MEAN),
    ("sum", _sum, Aggregation.SUM),
    ("pass_rate", _pass_rate, Aggregation.PASS_RATE),
    ("min", _min, Aggregation.MIN),
    ("max", _max, Aggregation.MAX),
]

_CONTINUOUS_SCORERS = [
    ("mean_per_hundred", _mean_per_hundred, Aggregation.MEAN_PER_N),
    ("mean_per_thousand", _mean_per_thousand, Aggregation.MEAN_PER_N),
    ("mean_per_ten_thousand", _mean_per_ten_thousand, Aggregation.MEAN_PER_N),
]

for _ref, _fn, _agg in _OUTCOME_SCORERS:
    register_scorer(
        _ref,
        callable_=_fn,
        version="1.0.0",
        input_schema=_INPUT_SCHEMA,
        output_metric_keys=(_ref,),
        metric_family=MetricFamily.OUTCOME,
        aggregation=_agg,
        description=f"Built-in {_ref} scorer over a list of numeric values.",
    )

for _ref, _fn, _agg in _CONTINUOUS_SCORERS:
    register_scorer(
        _ref,
        callable_=_fn,
        version="1.0.0",
        input_schema=_INPUT_SCHEMA,
        output_metric_keys=(_ref,),
        metric_family=MetricFamily.QUALITY,
        aggregation=_agg,
        description=f"Built-in {_ref} scorer over a list of numeric values.",
    )
