"""Sales custom outcome eval metric contract — canonical definitions.

This module is the single source of truth for the four Hokusai sales outcome
metrics used by DeltaOne comparator dispatch and the HEM/DeltaOne tag contract.
It is a pure, side-effect-free constants module; it does not register scorers,
touch the database, or import heavyweight dependencies.

Canonical metric names use the ``sales:`` namespace prefix.  MLflow-safe keys
are derived via ``derive_mlflow_name`` from ``src.utils.metric_naming``.

Measurement policy serialization note
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The issue text used the shorthand ``exact_observed``.  The canonical serialized
value in eval_spec fixtures, schema enums, and HEM tags is
``exact_observed_output``.  This module and the JSON schema only accept
``exact_observed_output``; callers that receive ``exact_observed`` should
normalize before lookup.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from src.evaluation.tags import (
    MEASUREMENT_POLICY_TAG,
    MLFLOW_NAME_TAG,
    PRIMARY_METRIC_TAG,
    SCORER_REF_TAG,
)
from src.utils.metric_naming import derive_mlflow_name

# ---------------------------------------------------------------------------
# Literal types for contract fields
# ---------------------------------------------------------------------------

Direction = Literal["higher_is_better", "lower_is_better"]
Comparator = Literal["proportion", "zero_inflated_continuous"]
MeasurementPolicy = Literal[
    "online_ab",
    "reward_model",
    "off_policy",
    "exact_observed_output",
    "diagnostic_only",
]
DenominatorCase = Literal["zero_messages", "missing_label", "delayed_label", "partial_coverage"]

# ---------------------------------------------------------------------------
# Schema version sentinel
# ---------------------------------------------------------------------------

SALES_OUTCOME_ROW_SCHEMA_VERSION = "sales_outcome_row/v1"

# ---------------------------------------------------------------------------
# Measurement policies
# ---------------------------------------------------------------------------

#: All recognized measurement policy values.
MEASUREMENT_POLICIES: frozenset[MeasurementPolicy] = frozenset(
    {
        "online_ab",
        "reward_model",
        "off_policy",
        "exact_observed_output",
        "diagnostic_only",
    }
)

#: Policies that are mint-eligible (may trigger a DeltaOne MintRequest).
MINT_ELIGIBLE_POLICIES: frozenset[MeasurementPolicy] = frozenset(
    {
        "online_ab",
        "reward_model",
        "off_policy",
        "exact_observed_output",
    }
)

#: Policies that are *never* mint-eligible regardless of metric values.
DIAGNOSTIC_ONLY_POLICIES: frozenset[MeasurementPolicy] = frozenset({"diagnostic_only"})


# ---------------------------------------------------------------------------
# Per-metric denominator rules
# ---------------------------------------------------------------------------

_RATE_DENOMINATOR_RULES: Mapping[DenominatorCase, str] = {
    "zero_messages": (
        "When delivered_count is zero the metric value is 0.0. "
        "The row must carry label_status and coverage_fraction reflecting the zero denominator. "
        "Rows with zero denominator are not mint-sufficient on their own and will fail the "
        "coverage/min-examples guardrail."
    ),
    "missing_label": (
        "Rows with a missing or null outcome label are excluded from both the numerator and "
        "denominator. Do not treat a missing label as a negative outcome."
    ),
    "delayed_label": (
        "Before label_available_at or the configured outcome window closes, mark the row "
        "label_status='delayed' and exclude it from mint-eligible aggregation. "
        "diagnostic_only rows may log delayed rows for observability."
    ),
    "partial_coverage": (
        "Rows must carry coverage_fraction. Mint-eligible policies require the eval_spec "
        "coverage_policy guardrail to pass before a MintRequest is published. "
        "diagnostic_only policies may log partial coverage but cannot mint."
    ),
}

_REVENUE_DENOMINATOR_RULES: Mapping[DenominatorCase, str] = {
    "zero_messages": (
        "When delivered_count is zero the metric value is 0.0. "
        "The row must carry label_status and coverage_fraction reflecting the zero denominator. "
        "Rows with zero denominator are not mint-sufficient on their own and will fail the "
        "coverage/min-examples guardrail."
    ),
    "missing_label": (
        "Missing revenue for a delivered message contributes 0.0 only when the outcome window "
        "has closed and the row is labeled 'observed'. Otherwise mark the row 'delayed' or "
        "'missing' and exclude it from mint-eligible aggregation according to label policy."
    ),
    "delayed_label": (
        "Before label_available_at or the configured outcome window closes, mark the row "
        "label_status='delayed' and exclude it from mint-eligible aggregation. "
        "diagnostic_only rows may log delayed rows for observability."
    ),
    "partial_coverage": (
        "Rows must carry coverage_fraction. Mint-eligible policies require the eval_spec "
        "coverage_policy guardrail to pass before a MintRequest is published. "
        "diagnostic_only policies may log partial coverage but cannot mint."
    ),
}

_UNSUBSCRIBE_DENOMINATOR_RULES: Mapping[DenominatorCase, str] = {
    "zero_messages": (
        "When delivered_count is zero the metric value is 0.0. "
        "The row must carry label_status and coverage_fraction reflecting the zero denominator. "
        "Rows with zero denominator are not mint-sufficient on their own and will fail the "
        "coverage/min-examples guardrail."
    ),
    "missing_label": (
        "Missing spam_complaint or unsubscribe flags for delivered messages should be treated "
        "as 'not observed', not silently as False, unless the source system guarantees "
        "absence-as-false after the event window closes. Exclude uncertain rows."
    ),
    "delayed_label": (
        "Before label_available_at or the configured outcome window closes, mark the row "
        "label_status='delayed' and exclude it from mint-eligible aggregation. "
        "diagnostic_only rows may log delayed rows for observability."
    ),
    "partial_coverage": (
        "Rows must carry coverage_fraction. Mint-eligible policies require the eval_spec "
        "coverage_policy guardrail to pass before a MintRequest is published. "
        "diagnostic_only policies may log partial coverage but cannot mint."
    ),
}


# ---------------------------------------------------------------------------
# Contract dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SalesMetricContract:
    """Immutable contract definition for a single sales outcome metric.

    Fields
    ------
    hokusai_name
        Canonical Hokusai metric name including the ``sales:`` prefix.
    mlflow_name
        MLflow-safe key derived via ``derive_mlflow_name(hokusai_name)``.
        Colons are replaced with underscores; no further transformation.
    direction
        Whether higher or lower values indicate better model performance.
    metric_family
        Comparator family string used by DeltaOne dispatch.  This is distinct
        from ``ScorerMetadata.metric_family`` (which is a coarse ``MetricFamily``
        enum used only for internal scorer classification).
    comparator
        Specific DeltaOne statistical comparator to use for this metric.
    aggregation
        Row-level aggregation strategy.  ``MEAN`` for rate metrics;
        ``MEAN_PER_N`` for revenue (mean per 1,000 messages).
    threshold_semantics
        Human-readable description of threshold pass/fail criteria.
    unit_of_analysis
        Observational unit: ``prospect_conversation`` or ``prospect_message``.
    scorer_ref
        Canonical scorer registry ref expected by eval_spec.
    unit
        Display unit for the metric value.
    hem_tags
        HEM run tag keys this metric emits.
    deltaone_tags
        DeltaOne-relevant tag keys emitted alongside the scorer result.
    denominator_rules
        Per-case denominator/label handling rules keyed by ``DenominatorCase``.
    """

    hokusai_name: str
    mlflow_name: str
    direction: Direction
    metric_family: str
    comparator: Comparator
    aggregation: str
    threshold_semantics: str
    unit_of_analysis: str
    scorer_ref: str
    unit: str
    hem_tags: tuple[str, ...]
    deltaone_tags: tuple[str, ...]
    denominator_rules: Mapping[DenominatorCase, str]


# ---------------------------------------------------------------------------
# The four canonical sales metric contracts
# ---------------------------------------------------------------------------

_COMMON_HEM_TAGS: tuple[str, ...] = (
    PRIMARY_METRIC_TAG,
    MLFLOW_NAME_TAG,
    SCORER_REF_TAG,
    MEASUREMENT_POLICY_TAG,
)

_COMMON_DELTAONE_TAGS: tuple[str, ...] = (
    PRIMARY_METRIC_TAG,
    MLFLOW_NAME_TAG,
    SCORER_REF_TAG,
    MEASUREMENT_POLICY_TAG,
)


def _build_contract(
    hokusai_name: str,
    direction: Direction,
    metric_family: str,
    comparator: Comparator,
    aggregation: str,
    threshold_semantics: str,
    unit_of_analysis: str,
    unit: str,
    denominator_rules: Mapping[DenominatorCase, str],
) -> SalesMetricContract:
    return SalesMetricContract(
        hokusai_name=hokusai_name,
        mlflow_name=derive_mlflow_name(hokusai_name),
        direction=direction,
        metric_family=metric_family,
        comparator=comparator,
        aggregation=aggregation,
        threshold_semantics=threshold_semantics,
        unit_of_analysis=unit_of_analysis,
        scorer_ref=hokusai_name,
        unit=unit,
        hem_tags=_COMMON_HEM_TAGS,
        deltaone_tags=_COMMON_DELTAONE_TAGS,
        denominator_rules=denominator_rules,
    )


_QUALIFIED_MEETING_RATE = _build_contract(
    hokusai_name="sales:qualified_meeting_rate",
    direction="higher_is_better",
    metric_family="proportion",
    comparator="proportion",
    aggregation="MEAN",
    threshold_semantics=(
        "Passes when the observed rate is >= threshold and improves over baseline per the "
        "proportion comparator policy. Threshold is a fraction in [0, 1], not a percentage."
    ),
    unit_of_analysis="prospect_conversation",
    unit="proportion",
    denominator_rules=_RATE_DENOMINATOR_RULES,
)

_REVENUE_PER_1000_MESSAGES = _build_contract(
    hokusai_name="sales:revenue_per_1000_messages",
    direction="higher_is_better",
    metric_family="zero_inflated_continuous",
    comparator="zero_inflated_continuous",
    aggregation="MEAN_PER_N",
    threshold_semantics=(
        "Passes when observed USD per 1,000 delivered messages is >= threshold and improves "
        "over baseline per the zero-inflated-continuous comparator policy. Threshold unit is "
        "USD per 1,000 delivered messages unless the row explicitly provides a revenue_currency "
        "field indicating a different currency."
    ),
    unit_of_analysis="prospect_message",
    unit="usd_per_1000_messages",
    denominator_rules=_REVENUE_DENOMINATOR_RULES,
)

_SPAM_COMPLAINT_RATE = _build_contract(
    hokusai_name="sales:spam_complaint_rate",
    direction="lower_is_better",
    metric_family="proportion",
    comparator="proportion",
    aggregation="MEAN",
    threshold_semantics=(
        "Guardrail: passes when observed rate is <= threshold. Used as a blocking lower_is_better "
        "guardrail; a candidate model fails if its spam complaint rate exceeds the threshold. "
        "Threshold is a fraction in [0, 1], not a percentage."
    ),
    unit_of_analysis="prospect_message",
    unit="proportion",
    denominator_rules=_UNSUBSCRIBE_DENOMINATOR_RULES,
)

_UNSUBSCRIBE_RATE = _build_contract(
    hokusai_name="sales:unsubscribe_rate",
    direction="lower_is_better",
    metric_family="proportion",
    comparator="proportion",
    aggregation="MEAN",
    threshold_semantics=(
        "Guardrail: passes when observed rate is <= threshold. Used as a blocking lower_is_better "
        "guardrail; a candidate model fails if its unsubscribe rate exceeds the threshold. "
        "Threshold is a fraction in [0, 1], not a percentage."
    ),
    unit_of_analysis="prospect_message",
    unit="proportion",
    denominator_rules=_UNSUBSCRIBE_DENOMINATOR_RULES,
)

# ---------------------------------------------------------------------------
# Public collections
# ---------------------------------------------------------------------------

#: Ordered tuple of canonical Hokusai names for all sales outcome metrics.
SALES_METRIC_NAMES: tuple[str, ...] = (
    "sales:qualified_meeting_rate",
    "sales:revenue_per_1000_messages",
    "sales:spam_complaint_rate",
    "sales:unsubscribe_rate",
)

#: Mapping from canonical Hokusai name to its contract definition.
SALES_METRICS: dict[str, SalesMetricContract] = {
    "sales:qualified_meeting_rate": _QUALIFIED_MEETING_RATE,
    "sales:revenue_per_1000_messages": _REVENUE_PER_1000_MESSAGES,
    "sales:spam_complaint_rate": _SPAM_COMPLAINT_RATE,
    "sales:unsubscribe_rate": _UNSUBSCRIBE_RATE,
}
