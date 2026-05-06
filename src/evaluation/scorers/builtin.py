"""Built-in deterministic scorers registered at import time."""

from __future__ import annotations

from src.evaluation.scorers.metadata import Aggregation, MetricFamily
from src.evaluation.scorers.registry import register_scorer

_INPUT_SCHEMA = {"type": "array", "items": {"type": "number"}}

# Input schema for sales scorers: list of row dicts with observed outcome labels.
# All fields except 'delivered' are optional/nullable; missing labels are excluded
# from numerators and denominators rather than treated as zero.
_SALES_ROW_SCHEMA: dict = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "qualified_meeting": {"type": ["integer", "boolean", "null"]},
            "revenue": {"type": ["number", "null"]},
            "delivered": {"type": ["integer", "boolean"]},
            "spam_complaint": {"type": ["integer", "boolean", "null"]},
            "unsubscribe": {"type": ["integer", "boolean", "null"]},
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
    """Observed revenue per 1,000 delivered messages.

    Sums ``revenue`` for rows where ``delivered`` is truthy; ``None`` revenue
    contributes 0.0 for those rows.  Negative revenue raises ``ValueError``.
    Undelivered rows are excluded entirely from both numerator and denominator.
    Zero delivered denominator returns 0.0.
    """
    total_revenue = 0.0
    delivered_count = 0
    for row in rows:
        if not row.get("delivered"):
            continue
        delivered_count += 1
        rev = row.get("revenue")
        if rev is None:
            continue
        if rev < 0:
            raise ValueError(f"Negative revenue is not allowed: {rev!r}")
        total_revenue += rev
    if delivered_count == 0:
        return 0.0
    return (total_revenue / delivered_count) * 1000.0


def _sales_spam_complaint_rate(rows: list[dict]) -> float:
    """Fraction of delivered messages that generated a spam complaint.

    Denominator is the count of delivered rows with an observed (non-None)
    spam_complaint flag.  Rows where the flag is None are excluded from both
    numerator and denominator per the missing-label contract rule.
    Zero denominator returns 0.0.
    """
    numerator = 0
    denominator = 0
    for row in rows:
        if not row.get("delivered"):
            continue
        spam_complaint = row.get("spam_complaint")
        if spam_complaint is None:
            continue
        denominator += 1
        if spam_complaint:
            numerator += 1
    return numerator / denominator if denominator else 0.0


def _sales_unsubscribe_rate(rows: list[dict]) -> float:
    """Fraction of delivered messages that resulted in an unsubscribe event.

    Denominator is the count of delivered rows with an observed (non-None)
    unsubscribe flag.  Rows where the flag is None are excluded from both
    numerator and denominator per the missing-label contract rule.
    Zero denominator returns 0.0.
    """
    numerator = 0
    denominator = 0
    for row in rows:
        if not row.get("delivered"):
            continue
        unsubscribe = row.get("unsubscribe")
        if unsubscribe is None:
            continue
        denominator += 1
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
            "Rows with null or missing qualified_meeting labels are excluded from both "
            "numerator and denominator (unobserved outcomes). Zero denominator returns 0.0."
        ),
    ),
    (
        "sales:revenue_per_1000_messages",
        _sales_revenue_per_1000_messages,
        Aggregation.MEAN_PER_N,
        (
            "Observed revenue per 1,000 delivered messages. Sums non-null revenue over delivered "
            "rows (null revenue contributes 0.0 for delivered rows); raises ValueError on negative "
            "revenue. Undelivered rows excluded entirely. Zero delivered denominator returns 0.0."
        ),
    ),
    (
        "sales:spam_complaint_rate",
        _sales_spam_complaint_rate,
        Aggregation.MEAN,
        (
            "Fraction of delivered messages that generated a spam complaint. "
            "Denominator is the count of delivered rows with an observed (non-null) spam_complaint "
            "flag; rows with null flags are excluded from both numerator and denominator per the "
            "missing-label contract rule. Zero denominator returns 0.0. "
            "Use as a lower_is_better guardrail metric."
        ),
    ),
    (
        "sales:unsubscribe_rate",
        _sales_unsubscribe_rate,
        Aggregation.MEAN,
        (
            "Fraction of delivered messages that resulted in an unsubscribe event. "
            "Denominator is the count of delivered rows with an observed (non-null) unsubscribe "
            "flag; rows with null flags are excluded from both numerator and denominator per the "
            "missing-label contract rule. Zero denominator returns 0.0. "
            "Use as a lower_is_better guardrail metric."
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
