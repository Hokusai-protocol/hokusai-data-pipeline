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

_TASK_ROUTER_ROW_SCHEMA: dict = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "schema_version": {"type": "string", "const": "technical_task_router_row/v1"},
            "allowed_models": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "selected_models": {
                "type": "array",
                "items": {"type": "string"},
            },
            "max_cost_usd": {"type": "number", "exclusiveMinimum": 0},
            "actual_cost_usd": {"type": "number", "minimum": 0},
            "estimated_cost_usd": {"type": "number", "minimum": 0},
            "actual_time_seconds": {"type": "number", "minimum": 0},
            "estimated_duration_seconds": {"type": "number", "minimum": 0},
            "estimated_success_under_budget": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
            "routing_objective": {
                "type": "string",
                "enum": ["lowest_cost", "fastest_completion", "highest_reliability"],
            },
            "completed_successfully": {"type": "boolean"},
        },
        "required": [
            "schema_version",
            "allowed_models",
            "selected_models",
            "max_cost_usd",
            "actual_cost_usd",
            "completed_successfully",
        ],
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
    Negative ``delivered_count`` raises ``ValueError``.
    """
    numerator = 0
    denominator = 0
    for row in rows:
        spam_complaint = row.get("spam_complaint")
        if spam_complaint is None:
            continue
        dc = row.get("delivered_count") or 0
        if dc < 0:
            raise ValueError(f"Negative delivered_count is not allowed: {dc!r}")
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
    Negative ``delivered_count`` raises ``ValueError``.
    """
    numerator = 0
    denominator = 0
    for row in rows:
        unsubscribe = row.get("unsubscribe")
        if unsubscribe is None:
            continue
        dc = row.get("delivered_count") or 0
        if dc < 0:
            raise ValueError(f"Negative delivered_count is not allowed: {dc!r}")
        if dc == 0:
            continue
        denominator += dc
        if unsubscribe:
            numerator += 1
    return numerator / denominator if denominator else 0.0


# ---------------------------------------------------------------------------
# Technical task router scorers — operate on technical_task_router_row/v1 rows
# ---------------------------------------------------------------------------


def _task_router_row_is_feasible(row: dict) -> bool:
    selected_models_raw = row.get("selected_models")
    allowed_models_raw = row.get("allowed_models")
    if not isinstance(selected_models_raw, list) or not isinstance(allowed_models_raw, list):
        return False
    if not all(isinstance(model, str) for model in selected_models_raw + allowed_models_raw):
        return False

    try:
        actual_cost_usd = float(row["actual_cost_usd"])
        max_cost_usd = float(row["max_cost_usd"])
    except (KeyError, TypeError, ValueError):
        return False

    if actual_cost_usd < 0 or max_cost_usd <= 0:
        return False

    return set(selected_models_raw).issubset(set(allowed_models_raw)) and (
        actual_cost_usd <= max_cost_usd
    )


def _task_router_feasibility(rows: list[dict]) -> float:
    """Fraction of rows where selected models are allowed and observed cost is within budget."""
    if not rows:
        return 0.0
    feasible_count = sum(1 for row in rows if _task_router_row_is_feasible(row))
    return feasible_count / len(rows)


def _task_router_success_under_budget(rows: list[dict]) -> float:
    """Fraction of rows that are feasible and completed successfully."""
    if not rows:
        return 0.0
    successful_count = sum(
        1
        for row in rows
        if _task_router_row_is_feasible(row) and row.get("completed_successfully") is True
    )
    return successful_count / len(rows)


def _task_router_benchmark_score(rows: list[dict]) -> float:
    """Primary benchmark score: SuccessfulRunsWithinBudget / TotalRuns."""
    return _task_router_success_under_budget(rows)


def _task_router_row_is_success_under_budget(row: dict) -> bool:
    return _task_router_row_is_feasible(row) and row.get("completed_successfully") is True


def _task_router_invalid_selection_rate(rows: list[dict]) -> float:
    """Fraction of rows where one or more selected models are outside the allowed set."""
    if not rows:
        return 0.0

    invalid_count = 0
    for row in rows:
        selected_models_raw = row.get("selected_models")
        allowed_models_raw = row.get("allowed_models")
        if not isinstance(selected_models_raw, list) or not isinstance(allowed_models_raw, list):
            invalid_count += 1
            continue
        if not all(isinstance(model, str) for model in selected_models_raw + allowed_models_raw):
            invalid_count += 1
            continue
        if not set(selected_models_raw).issubset(set(allowed_models_raw)):
            invalid_count += 1
    return invalid_count / len(rows)


def _task_router_cost_mae_usd(rows: list[dict]) -> float:
    """Mean absolute error between estimated_cost_usd and actual_cost_usd."""
    errors = [
        abs(float(row["estimated_cost_usd"]) - float(row["actual_cost_usd"]))
        for row in rows
        if _has_number(row, "estimated_cost_usd") and _has_number(row, "actual_cost_usd")
    ]
    return _mean(errors)


def _task_router_duration_mae_seconds(rows: list[dict]) -> float:
    """Mean absolute error between estimated_duration_seconds and actual_time_seconds."""
    errors = [
        abs(float(row["estimated_duration_seconds"]) - float(row["actual_time_seconds"]))
        for row in rows
        if _has_number(row, "estimated_duration_seconds")
        and _has_number(row, "actual_time_seconds")
    ]
    return _mean(errors)


def _task_router_reliability_brier_score(rows: list[dict]) -> float:
    """Brier score for estimated_success_under_budget against observed benchmark success."""
    errors = [
        (
            float(row["estimated_success_under_budget"])
            - float(_task_router_row_is_success_under_budget(row))
        )
        ** 2
        for row in rows
        if _has_number(row, "estimated_success_under_budget")
    ]
    return _mean(errors)


def _task_router_objective_success_under_budget(rows: list[dict], objective: str) -> float:
    objective_rows = [row for row in rows if row.get("routing_objective") == objective]
    return _task_router_success_under_budget(objective_rows)


def _task_router_lowest_cost_success_under_budget(rows: list[dict]) -> float:
    """Success-under-budget rate for rows routed with the lowest-cost objective."""
    return _task_router_objective_success_under_budget(rows, "lowest_cost")


def _task_router_fastest_completion_success_under_budget(rows: list[dict]) -> float:
    """Success-under-budget rate for rows routed with the fastest-completion objective."""
    return _task_router_objective_success_under_budget(rows, "fastest_completion")


def _task_router_highest_reliability_success_under_budget(rows: list[dict]) -> float:
    """Success-under-budget rate for rows routed with the highest-reliability objective."""
    return _task_router_objective_success_under_budget(rows, "highest_reliability")


def _has_number(row: dict, key: str) -> bool:
    try:
        float(row[key])
    except (KeyError, TypeError, ValueError):
        return False
    return True


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

_TASK_ROUTER_SCORERS = [
    (
        "technical_task_router.feasibility/v1",
        _task_router_feasibility,
        (
            "Fraction of technical task router rows where every selected model is allowed "
            "and actual_cost_usd is less than or equal to max_cost_usd."
        ),
        Aggregation.PASS_RATE,
        MetricFamily.OUTCOME,
    ),
    (
        "technical_task_router.success_under_budget/v1",
        _task_router_success_under_budget,
        (
            "Fraction of technical task router rows where the workflow is feasible and "
            "completed_successfully is true."
        ),
        Aggregation.PASS_RATE,
        MetricFamily.OUTCOME,
    ),
    (
        "technical_task_router.benchmark_score/v1",
        _task_router_benchmark_score,
        (
            "Primary technical task router benchmark score. Computes "
            "SuccessfulRunsWithinBudget / TotalRuns, where successful runs must select only "
            "allowed models, stay within max_cost_usd, and complete successfully."
        ),
        Aggregation.PASS_RATE,
        MetricFamily.OUTCOME,
    ),
    (
        "technical_task_router.invalid_selection_rate/v1",
        _task_router_invalid_selection_rate,
        (
            "Diagnostic fraction of technical task router rows where selected_models is not "
            "a subset of allowed_models. Expected value is 0.0 for valid production routes."
        ),
        Aggregation.PASS_RATE,
        MetricFamily.OUTCOME,
    ),
    (
        "technical_task_router.cost_mae_usd/v1",
        _task_router_cost_mae_usd,
        (
            "Diagnostic mean absolute error in USD between estimated_cost_usd and "
            "actual_cost_usd. Rows without both values are excluded."
        ),
        Aggregation.MEAN,
        MetricFamily.QUALITY,
    ),
    (
        "technical_task_router.duration_mae_seconds/v1",
        _task_router_duration_mae_seconds,
        (
            "Diagnostic mean absolute error in seconds between estimated_duration_seconds "
            "and actual_time_seconds. Rows without both values are excluded."
        ),
        Aggregation.MEAN,
        MetricFamily.QUALITY,
    ),
    (
        "technical_task_router.reliability_brier_score/v1",
        _task_router_reliability_brier_score,
        (
            "Diagnostic Brier score for estimated_success_under_budget against observed "
            "success-under-budget. Lower values indicate better reliability calibration."
        ),
        Aggregation.MEAN,
        MetricFamily.QUALITY,
    ),
    (
        "technical_task_router.lowest_cost_success_under_budget/v1",
        _task_router_lowest_cost_success_under_budget,
        "Diagnostic success-under-budget rate for rows routed with objective=lowest_cost.",
        Aggregation.PASS_RATE,
        MetricFamily.OUTCOME,
    ),
    (
        "technical_task_router.fastest_completion_success_under_budget/v1",
        _task_router_fastest_completion_success_under_budget,
        (
            "Diagnostic success-under-budget rate for rows routed with "
            "objective=fastest_completion."
        ),
        Aggregation.PASS_RATE,
        MetricFamily.OUTCOME,
    ),
    (
        "technical_task_router.highest_reliability_success_under_budget/v1",
        _task_router_highest_reliability_success_under_budget,
        (
            "Diagnostic success-under-budget rate for rows routed with "
            "objective=highest_reliability."
        ),
        Aggregation.PASS_RATE,
        MetricFamily.OUTCOME,
    ),
]

for _ref, _fn, _desc, _agg, _family in _TASK_ROUTER_SCORERS:
    register_scorer(
        _ref,
        callable_=_fn,
        version="1.0.0",
        input_schema=_TASK_ROUTER_ROW_SCHEMA,
        output_metric_keys=(_ref,),
        metric_family=_family,
        aggregation=_agg,
        description=_desc,
    )
