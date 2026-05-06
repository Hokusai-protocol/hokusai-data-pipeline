"""Built-in deterministic scorers registered at import time."""

from __future__ import annotations

from src.evaluation.scorers.metadata import Aggregation, MetricFamily
from src.evaluation.scorers.registry import register_scorer

_INPUT_SCHEMA = {"type": "array", "items": {"type": "number"}}

# Input schema for sales scorers: list of sales_outcome_row/v1 row dicts.
# Canonical field names match schema/sales_outcome_row.v1.json.
# Missing outcome labels (qualified_meeting, spam_complaint, unsubscribe) are
# excluded from numerators and denominators rather than treated as zero.
# Missing revenue_amount_cents for delivered rows contributes 0.0 cents.
_SALES_ROW_SCHEMA: dict = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "schema_version": {"type": "string"},
            "metric_name": {"type": "string"},
            "scorer_ref": {"type": "string"},
            "message_count": {"type": "integer", "minimum": 0},
            "delivered_count": {"type": "integer", "minimum": 0},
            "numerator": {"type": "number", "minimum": 0},
            "denominator": {"type": "number", "minimum": 0},
            "label_status": {"type": "string"},
            "qualified_meeting": {"type": ["boolean", "null"]},
            "revenue_amount_cents": {"type": ["integer", "null"], "minimum": 0},
            "revenue_currency": {"type": "string"},
            "spam_complaint": {"type": ["boolean", "null"]},
            "unsubscribe": {"type": ["boolean", "null"]},
        },
    },
}


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


# ---------------------------------------------------------------------------
# Sales outcome scorers — operate on list[dict] row observations, not list[float]
# ---------------------------------------------------------------------------


def _sales_qualified_meeting_rate(rows: list[dict]) -> float:
    """Fraction of observed conversations resulting in a qualified meeting.

    Denominator is the count of rows with a non-null ``qualified_meeting`` label.
    Rows where the label is absent or None are excluded from both numerator and
    denominator (unobserved outcomes).  Zero denominator returns 0.0.
    """
    numerator = 0
    denominator = 0
    for row in rows:
        label = row.get("qualified_meeting")
        if label is None:
            continue
        denominator += 1
        if label:
            numerator += 1
    return numerator / denominator if denominator else 0.0


def _sales_revenue_per_1000_messages(rows: list[dict]) -> float:
    """Observed revenue per 1,000 delivered messages (USD).

    Formula: ``sum(revenue_amount_cents) / 100 / sum(delivered_count) * 1000``.
    Rows with zero or absent ``delivered_count`` are excluded from both numerator
    and denominator.  Absent ``revenue_amount_cents`` contributes 0.0 cents.
    Negative ``revenue_amount_cents`` or negative ``delivered_count`` raises
    ``ValueError``.  Zero total delivered denominator returns 0.0.
    """
    total_cents = 0.0
    total_delivered = 0
    for row in rows:
        dc = row.get("delivered_count")
        if dc is None:
            dc = 0
        if dc < 0:
            raise ValueError(f"Negative delivered_count is not allowed: {dc!r}")
        if dc == 0:
            continue
        cents = row.get("revenue_amount_cents")
        if cents is None:
            cents = 0
        if cents < 0:
            raise ValueError(f"Negative revenue_amount_cents is not allowed: {cents!r}")
        total_cents += cents
        total_delivered += dc
    if total_delivered == 0:
        return 0.0
    return (total_cents / 100.0 / total_delivered) * 1000.0


def _sales_spam_complaint_rate(rows: list[dict]) -> float:
    """Fraction of delivered messages that generated a spam complaint.

    Denominator is the sum of ``delivered_count`` for rows with an observed
    (non-None) ``spam_complaint`` flag.  Numerator increments by 1 per truthy
    flag regardless of ``delivered_count`` (one event per row).  Rows with a
    None flag or zero ``delivered_count`` are excluded from both numerator and
    denominator per the missing-label contract rule.  Zero denominator returns 0.0.
    """
    numerator = 0
    denominator = 0
    for row in rows:
        spam_complaint = row.get("spam_complaint")
        if spam_complaint is None:
            continue
        dc = row.get("delivered_count") or 0
        if dc == 0:
            continue
        denominator += dc
        if spam_complaint:
            numerator += 1
    return numerator / denominator if denominator else 0.0


def _sales_unsubscribe_rate(rows: list[dict]) -> float:
    """Fraction of delivered messages that resulted in an unsubscribe event.

    Denominator is the sum of ``delivered_count`` for rows with an observed
    (non-None) ``unsubscribe`` flag.  Numerator increments by 1 per truthy flag
    regardless of ``delivered_count`` (one event per row).  Rows with a None
    flag or zero ``delivered_count`` are excluded from both numerator and
    denominator per the missing-label contract rule.  Zero denominator returns 0.0.
    """
    numerator = 0
    denominator = 0
    for row in rows:
        unsubscribe = row.get("unsubscribe")
        if unsubscribe is None:
            continue
        dc = row.get("delivered_count") or 0
        if dc == 0:
            continue
        denominator += dc
        if unsubscribe:
            numerator += 1
    return numerator / denominator if denominator else 0.0


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

_SALES_SCORERS = [
    (
        "sales:qualified_meeting_rate",
        _sales_qualified_meeting_rate,
        Aggregation.MEAN,
        (
            "Fraction of observed sales conversations where a qualified meeting was booked. "
            "Reads the qualified_meeting field from sales_outcome_row/v1 rows. "
            "Rows with null or absent qualified_meeting labels are excluded from both "
            "numerator and denominator (unobserved outcomes). Zero denominator returns 0.0."
        ),
    ),
    (
        "sales:revenue_per_1000_messages",
        _sales_revenue_per_1000_messages,
        Aggregation.MEAN_PER_N,
        (
            "Observed revenue per 1,000 delivered messages (USD). "
            "Formula: sum(revenue_amount_cents) / 100 / sum(delivered_count) * 1000. "
            "Rows with zero or absent delivered_count are excluded. "
            "Absent revenue_amount_cents contributes 0.0 cents for delivered rows. "
            "Negative revenue_amount_cents or delivered_count raises ValueError. "
            "Zero total delivered denominator returns 0.0."
        ),
    ),
    (
        "sales:spam_complaint_rate",
        _sales_spam_complaint_rate,
        Aggregation.MEAN,
        (
            "Fraction of delivered messages that generated a spam complaint. "
            "Denominator is sum(delivered_count) for rows with an observed (non-null) "
            "spam_complaint flag; rows with null flags or zero delivered_count are excluded "
            "from both numerator and denominator per the missing-label contract rule. "
            "Zero denominator returns 0.0. Use as a lower_is_better guardrail metric."
        ),
    ),
    (
        "sales:unsubscribe_rate",
        _sales_unsubscribe_rate,
        Aggregation.MEAN,
        (
            "Fraction of delivered messages that resulted in an unsubscribe event. "
            "Denominator is sum(delivered_count) for rows with an observed (non-null) "
            "unsubscribe flag; rows with null flags or zero delivered_count are excluded "
            "from both numerator and denominator per the missing-label contract rule. "
            "Zero denominator returns 0.0. Use as a lower_is_better guardrail metric."
        ),
    ),
]

for _ref, _fn, _agg, _desc in _SALES_SCORERS:
    register_scorer(
        _ref,
        callable_=_fn,
        version="1.0.0",
        input_schema=_SALES_ROW_SCHEMA,
        output_metric_keys=(_ref,),
        metric_family=MetricFamily.OUTCOME,
        aggregation=_agg,
        description=_desc,
    )
