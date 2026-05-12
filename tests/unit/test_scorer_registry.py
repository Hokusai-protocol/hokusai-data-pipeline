"""Unit tests for src/evaluation/scorers/."""

from __future__ import annotations

import pytest

from src.evaluation.guardrails import evaluate_guardrails
from src.evaluation.schema import MetricFamily as SchemaMetricFamily
from src.evaluation.scorers import (
    Aggregation,
    MetricFamily,
    ScorerConflictError,
    UnknownScorerError,
    list_scorers,
    register_scorer,
    resolve_scorer,
)
from src.evaluation.scorers.registry import compute_source_hash
from src.evaluation.spec_translation import RuntimeGuardrailSpec, _resolve_scorer_for_translation
from src.utils.metric_naming import derive_mlflow_name, validate_mlflow_metric_key

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _dummy_scorer(values: list[float]) -> float:
    return sum(values)


@pytest.fixture()
def isolated_registry():
    """Snapshot built-in registrations, restore after test."""
    from src.evaluation.scorers import registry as _reg

    snapshot = dict(_reg._REGISTRY)
    yield
    _reg._REGISTRY.clear()
    _reg._REGISTRY.update(snapshot)


# ---------------------------------------------------------------------------
# 1. Resolve built-in "mean"
# ---------------------------------------------------------------------------


def test_resolve_mean_returns_correct_metadata():
    scorer = resolve_scorer("mean")
    meta = scorer.metadata
    assert meta.scorer_ref == "mean"
    assert meta.metric_family == MetricFamily.OUTCOME
    assert meta.aggregation == Aggregation.MEAN
    assert len(meta.source_hash) == 64
    assert all(c in "0123456789abcdef" for c in meta.source_hash)


# ---------------------------------------------------------------------------
# 2. Unknown ref raises UnknownScorerError (which is a KeyError)
# ---------------------------------------------------------------------------


def test_resolve_unknown_ref_raises():
    with pytest.raises(UnknownScorerError) as exc_info:
        resolve_scorer("does_not_exist")
    assert "does_not_exist" in str(exc_info.value)
    assert isinstance(exc_info.value, KeyError)


# ---------------------------------------------------------------------------
# 3. Empty string raises UnknownScorerError
# ---------------------------------------------------------------------------


def test_resolve_empty_string_raises():
    with pytest.raises(UnknownScorerError):
        resolve_scorer("")


# ---------------------------------------------------------------------------
# 4. None raises TypeError (type contract)
# ---------------------------------------------------------------------------


def test_resolve_none_raises_type_error():
    with pytest.raises(TypeError):
        resolve_scorer(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5. Hash stability: same inputs → same digest
# ---------------------------------------------------------------------------


def test_hash_stability():
    h1 = compute_source_hash(
        "test_ref",
        "1.0.0",
        {"type": "array"},
        ("metric",),
        MetricFamily.OUTCOME,
        Aggregation.MEAN,
        _dummy_scorer,
    )
    h2 = compute_source_hash(
        "test_ref",
        "1.0.0",
        {"type": "array"},
        ("metric",),
        MetricFamily.OUTCOME,
        Aggregation.MEAN,
        _dummy_scorer,
    )
    assert h1 == h2
    assert len(h1) == 64


# ---------------------------------------------------------------------------
# 6. Hash sensitivity: changing version changes digest
# ---------------------------------------------------------------------------


def test_hash_sensitivity_version():
    h1 = compute_source_hash(
        "test_ref",
        "1.0.0",
        {"type": "array"},
        ("metric",),
        MetricFamily.OUTCOME,
        Aggregation.MEAN,
        _dummy_scorer,
    )
    h2 = compute_source_hash(
        "test_ref",
        "2.0.0",
        {"type": "array"},
        ("metric",),
        MetricFamily.OUTCOME,
        Aggregation.MEAN,
        _dummy_scorer,
    )
    assert h1 != h2


# ---------------------------------------------------------------------------
# 7. Idempotent re-registration
# ---------------------------------------------------------------------------


def test_idempotent_reregistration(isolated_registry):
    register_scorer(
        "idempotent_test",
        callable_=_dummy_scorer,
        version="1.0.0",
        input_schema={"type": "array"},
        output_metric_keys=("idempotent_test",),
        metric_family=MetricFamily.OUTCOME,
        aggregation=Aggregation.SUM,
    )
    # Second registration with identical metadata should not raise.
    register_scorer(
        "idempotent_test",
        callable_=_dummy_scorer,
        version="1.0.0",
        input_schema={"type": "array"},
        output_metric_keys=("idempotent_test",),
        metric_family=MetricFamily.OUTCOME,
        aggregation=Aggregation.SUM,
    )
    assert resolve_scorer("idempotent_test").metadata.scorer_ref == "idempotent_test"


# ---------------------------------------------------------------------------
# 8. ScorerConflictError on conflicting re-registration
# ---------------------------------------------------------------------------


def test_conflict_on_different_version(isolated_registry):
    register_scorer(
        "conflict_test",
        callable_=_dummy_scorer,
        version="1.0.0",
        input_schema={"type": "array"},
        output_metric_keys=("conflict_test",),
        metric_family=MetricFamily.OUTCOME,
        aggregation=Aggregation.SUM,
    )
    with pytest.raises(ScorerConflictError) as exc_info:
        register_scorer(
            "conflict_test",
            callable_=_dummy_scorer,
            version="2.0.0",  # different version → different hash
            input_schema={"type": "array"},
            output_metric_keys=("conflict_test",),
            metric_family=MetricFamily.OUTCOME,
            aggregation=Aggregation.SUM,
        )
    assert "conflict_test" in str(exc_info.value)
    assert isinstance(exc_info.value, ValueError)


# ---------------------------------------------------------------------------
# 9. list_scorers returns sorted list including all built-ins
# ---------------------------------------------------------------------------


def test_list_scorers_includes_builtins():
    scorers = list_scorers()
    refs = [s.scorer_ref for s in scorers]
    assert "mean" in refs
    assert "sum" in refs
    assert "pass_rate" in refs
    assert "min" in refs
    assert "max" in refs
    assert "mean_per_hundred" in refs
    assert "mean_per_thousand" in refs
    assert "mean_per_ten_thousand" in refs
    assert "technical_task_router:success_within_budget" in refs
    assert refs == sorted(refs)


def test_technical_task_router_scorer_metadata() -> None:
    scorer = resolve_scorer("technical_task_router:success_within_budget")
    meta = scorer.metadata
    assert meta.scorer_ref == "technical_task_router:success_within_budget"
    assert meta.version == "1.0.0"
    assert meta.metric_family == MetricFamily.OUTCOME
    assert meta.aggregation == Aggregation.MEAN
    assert meta.output_metric_keys == ("technical_task_router:success_within_budget",)
    assert meta.input_schema["items"]["properties"]["schema_version"]["type"] == "string"


# ---------------------------------------------------------------------------
# 10. output_metric_keys produce valid MLflow keys after derivation
# ---------------------------------------------------------------------------


def test_builtin_metric_keys_are_mlflow_safe():
    # Canonical output keys may contain ':' (e.g. 'sales:spam_complaint_rate').
    # The registry contract guarantees that derive_mlflow_name(key) is a valid
    # MLflow metric key; direct key validation is intentionally not required.
    for meta in list_scorers():
        for key in meta.output_metric_keys:
            derived = derive_mlflow_name(key)
            validate_mlflow_metric_key(derived)


# ---------------------------------------------------------------------------
# 10b. metric_family values are valid MetricFamily enum members
# ---------------------------------------------------------------------------


def test_builtin_metric_families_are_valid():
    """Verify every built-in scorer's metric_family is a valid value from schema.py."""
    valid_families = set(SchemaMetricFamily)
    for meta in list_scorers():
        assert meta.metric_family in valid_families, (
            f"Scorer {meta.scorer_ref!r} has invalid metric_family {meta.metric_family!r}; "
            f"must be one of {valid_families}"
        )


# ---------------------------------------------------------------------------
# 11. _resolve_scorer_for_translation
# ---------------------------------------------------------------------------


def test_resolve_scorer_for_translation_none_returns_none():
    assert _resolve_scorer_for_translation(None) is None


def test_resolve_scorer_for_translation_valid_ref():
    result = _resolve_scorer_for_translation("mean")
    assert result is not None
    assert result.metadata.scorer_ref == "mean"  # type: ignore[union-attr]


def test_resolve_scorer_for_translation_unknown_ref():
    with pytest.raises(UnknownScorerError):
        _resolve_scorer_for_translation("no_such_scorer")


# ---------------------------------------------------------------------------
# 12. mean_per_n family: metadata
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ref", ["mean_per_hundred", "mean_per_thousand", "mean_per_ten_thousand"])
def test_mean_per_n_metadata(ref):
    scorer = resolve_scorer(ref)
    meta = scorer.metadata
    assert meta.scorer_ref == ref
    assert meta.output_metric_keys == (ref,)
    assert meta.metric_family == MetricFamily.QUALITY
    assert meta.aggregation == Aggregation.MEAN_PER_N
    assert len(meta.source_hash) == 64
    assert all(c in "0123456789abcdef" for c in meta.source_hash)


# ---------------------------------------------------------------------------
# 13. mean_per_n family: value correctness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ref,values,expected",
    [
        # empty input → 0.0
        ("mean_per_hundred", [], 0.0),
        ("mean_per_thousand", [], 0.0),
        ("mean_per_ten_thousand", [], 0.0),
        # all-zero input → 0.0
        ("mean_per_hundred", [0.0, 0.0, 0.0], 0.0),
        ("mean_per_thousand", [0.0, 0.0, 0.0], 0.0),
        ("mean_per_ten_thousand", [0.0, 0.0, 0.0], 0.0),
        # known example: mean([0.01, 0.02, 0.03]) = 0.02
        ("mean_per_hundred", [0.01, 0.02, 0.03], 2.0),
        ("mean_per_thousand", [0.01, 0.02, 0.03], 20.0),
        ("mean_per_ten_thousand", [0.01, 0.02, 0.03], 200.0),
    ],
)
def test_mean_per_n_values(ref, values, expected):
    scorer = resolve_scorer(ref)
    result = scorer.callable_(values)
    assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Sales scorer constants
# ---------------------------------------------------------------------------

_SALES_REFS = [
    "sales:qualified_meeting_rate",
    "sales:revenue_per_1000_messages",
    "sales:spam_complaint_rate",
    "sales:unsubscribe_rate",
]

# ---------------------------------------------------------------------------
# 14. Sales scorer registry availability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ref", _SALES_REFS)
def test_sales_scorers_resolve(ref):
    scorer = resolve_scorer(ref)
    assert scorer.metadata.scorer_ref == ref


def test_list_scorers_includes_sales_refs():
    refs = [s.scorer_ref for s in list_scorers()]
    for ref in _SALES_REFS:
        assert ref in refs
    assert refs == sorted(refs)


# ---------------------------------------------------------------------------
# 15. Sales scorer metadata completeness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ref", _SALES_REFS)
def test_sales_scorer_metadata_fields(ref):
    meta = resolve_scorer(ref).metadata
    assert meta.version == "1.0.0"
    assert meta.metric_family == MetricFamily.OUTCOME
    assert meta.input_schema is not None
    assert len(meta.output_metric_keys) > 0
    assert meta.aggregation is not None
    assert len(meta.source_hash) == 64
    assert all(c in "0123456789abcdef" for c in meta.source_hash)
    assert meta.description is not None and len(meta.description) > 0


@pytest.mark.parametrize("ref", _SALES_REFS)
def test_sales_scorer_output_keys_are_canonical(ref):
    meta = resolve_scorer(ref).metadata
    for key in meta.output_metric_keys:
        assert ":" in key, f"Expected canonical colon name, got {key!r}"
        derived = derive_mlflow_name(key)
        validate_mlflow_metric_key(derived)


def test_sales_scorer_derived_mlflow_names_unique():
    derived_names = []
    for ref in _SALES_REFS:
        meta = resolve_scorer(ref).metadata
        for key in meta.output_metric_keys:
            derived_names.append(derive_mlflow_name(key))
    assert len(derived_names) == len(set(derived_names)), "Derived MLflow names must be unique"


@pytest.mark.parametrize("ref", _SALES_REFS)
def test_sales_scorer_aggregation(ref):
    meta = resolve_scorer(ref).metadata
    if ref == "sales:revenue_per_1000_messages":
        assert meta.aggregation == Aggregation.MEAN_PER_N
    else:
        assert meta.aggregation == Aggregation.MEAN


# ---------------------------------------------------------------------------
# 16. Unknown sales ref still raises UnknownScorerError
# ---------------------------------------------------------------------------


def test_unknown_sales_ref_raises():
    with pytest.raises(UnknownScorerError):
        resolve_scorer("sales:does_not_exist")


# ---------------------------------------------------------------------------
# 17. qualified_meeting_rate formula
# ---------------------------------------------------------------------------


def test_qualified_meeting_rate_normal():
    scorer = resolve_scorer("sales:qualified_meeting_rate")
    rows = [
        {"qualified_meeting": 1},
        {"qualified_meeting": 0},
        {"qualified_meeting": 1},
    ]
    assert scorer.callable_(rows) == pytest.approx(2 / 3)


def test_qualified_meeting_rate_all_meetings():
    scorer = resolve_scorer("sales:qualified_meeting_rate")
    rows = [{"qualified_meeting": 1}, {"qualified_meeting": 1}]
    assert scorer.callable_(rows) == pytest.approx(1.0)


def test_qualified_meeting_rate_zero_denominator_all_null():
    scorer = resolve_scorer("sales:qualified_meeting_rate")
    rows = [{"qualified_meeting": None}, {"other_field": 1}]
    assert scorer.callable_(rows) == 0.0


def test_qualified_meeting_rate_empty_rows():
    scorer = resolve_scorer("sales:qualified_meeting_rate")
    assert scorer.callable_([]) == 0.0


def test_qualified_meeting_rate_missing_labels_excluded():
    scorer = resolve_scorer("sales:qualified_meeting_rate")
    # Two rows with label, one without; only labeled rows count
    rows = [
        {"qualified_meeting": 1},
        {"qualified_meeting": None},  # excluded
        {"qualified_meeting": 0},
    ]
    assert scorer.callable_(rows) == pytest.approx(0.5)


def test_qualified_meeting_rate_bool_labels():
    scorer = resolve_scorer("sales:qualified_meeting_rate")
    rows = [{"qualified_meeting": True}, {"qualified_meeting": False}]
    assert scorer.callable_(rows) == pytest.approx(0.5)


def test_qualified_meeting_rate_missing_label_key_returns_zero():
    scorer = resolve_scorer("sales:qualified_meeting_rate")
    rows = [{"delivered_count": 1}]  # qualified_meeting key absent → None → excluded
    assert scorer.callable_(rows) == 0.0


# ---------------------------------------------------------------------------
# 18. revenue_per_1000_messages formula
# ---------------------------------------------------------------------------


def test_revenue_per_1000_normal():
    scorer = resolve_scorer("sales:revenue_per_1000_messages")
    rows = [
        {"delivered_count": 1, "revenue_amount_cents": 1000},  # $10.00
        {"delivered_count": 1, "revenue_amount_cents": 2000},  # $20.00
        {"delivered_count": 1, "revenue_amount_cents": 3000},  # $30.00
    ]
    # total_cents=6000, total_delivered=3 → (6000/100/3)*1000 = 20000.0
    assert scorer.callable_(rows) == pytest.approx(20000.0)


def test_revenue_per_1000_zero_denominator_no_delivered():
    scorer = resolve_scorer("sales:revenue_per_1000_messages")
    rows = [{"delivered_count": 0, "revenue_amount_cents": 10000}]
    assert scorer.callable_(rows) == 0.0


def test_revenue_per_1000_empty_rows():
    scorer = resolve_scorer("sales:revenue_per_1000_messages")
    assert scorer.callable_([]) == 0.0


def test_revenue_per_1000_null_revenue_treated_as_zero():
    scorer = resolve_scorer("sales:revenue_per_1000_messages")
    rows = [
        {"delivered_count": 1, "revenue_amount_cents": None},
        {"delivered_count": 1, "revenue_amount_cents": 1000},  # $10.00
    ]
    # total_cents=0+1000=1000, total_delivered=2 → (1000/100/2)*1000 = 5000.0
    assert scorer.callable_(rows) == pytest.approx(5000.0)


def test_revenue_per_1000_undelivered_excluded():
    scorer = resolve_scorer("sales:revenue_per_1000_messages")
    rows = [
        {"delivered_count": 1, "revenue_amount_cents": 1000},  # $10.00
        {"delivered_count": 0, "revenue_amount_cents": 999900},  # must not affect result
    ]
    # total_cents=1000, total_delivered=1 → (1000/100/1)*1000 = 10000.0
    assert scorer.callable_(rows) == pytest.approx(10000.0)


def test_revenue_per_1000_negative_revenue_raises():
    scorer = resolve_scorer("sales:revenue_per_1000_messages")
    rows = [{"delivered_count": 1, "revenue_amount_cents": -500}]
    with pytest.raises(ValueError, match="[Nn]egative"):
        scorer.callable_(rows)


def test_revenue_per_1000_zero_delivered_count_returns_zero():
    scorer = resolve_scorer("sales:revenue_per_1000_messages")
    rows = [{"delivered_count": 0}, {"delivered_count": 0, "revenue_amount_cents": 5000}]
    assert scorer.callable_(rows) == 0.0


def test_revenue_per_1000_missing_delivered_count_returns_zero():
    scorer = resolve_scorer("sales:revenue_per_1000_messages")
    rows = [{"revenue_amount_cents": 1000}]  # no delivered_count key
    assert scorer.callable_(rows) == 0.0


def test_revenue_per_1000_missing_revenue_amount_cents_contributes_zero():
    scorer = resolve_scorer("sales:revenue_per_1000_messages")
    rows = [{"delivered_count": 1}]  # revenue_amount_cents absent → 0 cents
    assert scorer.callable_(rows) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 19. spam_complaint_rate formula
# ---------------------------------------------------------------------------


def test_spam_complaint_rate_normal():
    scorer = resolve_scorer("sales:spam_complaint_rate")
    rows = [
        {"delivered_count": 1, "spam_complaint": True},
        {"delivered_count": 1, "spam_complaint": False},
        {"delivered_count": 1, "spam_complaint": False},
        {"delivered_count": 1, "spam_complaint": False},
    ]
    # numerator=1, denominator=4 → 0.25
    assert scorer.callable_(rows) == pytest.approx(0.25)


def test_spam_complaint_rate_zero_denominator_no_delivered():
    scorer = resolve_scorer("sales:spam_complaint_rate")
    rows = [{"delivered_count": 0, "spam_complaint": True}]
    assert scorer.callable_(rows) == 0.0


def test_spam_complaint_rate_empty_rows():
    scorer = resolve_scorer("sales:spam_complaint_rate")
    assert scorer.callable_([]) == 0.0


def test_spam_complaint_rate_non_delivered_excluded():
    scorer = resolve_scorer("sales:spam_complaint_rate")
    rows = [
        {"delivered_count": 1, "spam_complaint": False},
        {"delivered_count": 0, "spam_complaint": True},  # must not inflate denominator
    ]
    # Row 2 has delivered_count=0 → excluded; denominator=1, numerator=0
    assert scorer.callable_(rows) == pytest.approx(0.0)


def test_spam_complaint_rate_no_complaints():
    scorer = resolve_scorer("sales:spam_complaint_rate")
    rows = [
        {"delivered_count": 1, "spam_complaint": False},
        {"delivered_count": 1, "spam_complaint": False},
    ]
    assert scorer.callable_(rows) == 0.0


def test_spam_complaint_rate_null_flag_excluded_from_denominator():
    scorer = resolve_scorer("sales:spam_complaint_rate")
    rows = [
        {"delivered_count": 1, "spam_complaint": True},
        {"delivered_count": 1, "spam_complaint": None},  # missing label — excluded entirely
        {"delivered_count": 1, "spam_complaint": False},
    ]
    # denominator=2 (None row dropped), numerator=1
    assert scorer.callable_(rows) == pytest.approx(0.5)


def test_spam_complaint_rate_zero_delivered_count_returns_zero():
    scorer = resolve_scorer("sales:spam_complaint_rate")
    rows = [{"delivered_count": 0, "spam_complaint": True}]
    assert scorer.callable_(rows) == 0.0


def test_spam_complaint_rate_missing_delivered_count_returns_zero():
    scorer = resolve_scorer("sales:spam_complaint_rate")
    rows = [{"spam_complaint": True}]  # no delivered_count key → treated as 0
    assert scorer.callable_(rows) == 0.0


def test_spam_complaint_rate_missing_label_key_returns_zero():
    scorer = resolve_scorer("sales:spam_complaint_rate")
    rows = [{"delivered_count": 1}]  # spam_complaint key absent → None → excluded
    assert scorer.callable_(rows) == 0.0


# ---------------------------------------------------------------------------
# 20. unsubscribe_rate formula
# ---------------------------------------------------------------------------


def test_unsubscribe_rate_normal():
    scorer = resolve_scorer("sales:unsubscribe_rate")
    rows = [
        {"delivered_count": 1, "unsubscribe": True},
        {"delivered_count": 1, "unsubscribe": False},
        {"delivered_count": 1, "unsubscribe": True},
        {"delivered_count": 1, "unsubscribe": False},
    ]
    # numerator=2, denominator=4 → 0.5
    assert scorer.callable_(rows) == pytest.approx(0.5)


def test_unsubscribe_rate_zero_denominator_no_delivered():
    scorer = resolve_scorer("sales:unsubscribe_rate")
    rows = [{"delivered_count": 0, "unsubscribe": True}]
    assert scorer.callable_(rows) == 0.0


def test_unsubscribe_rate_empty_rows():
    scorer = resolve_scorer("sales:unsubscribe_rate")
    assert scorer.callable_([]) == 0.0


def test_unsubscribe_rate_non_delivered_excluded():
    scorer = resolve_scorer("sales:unsubscribe_rate")
    rows = [
        {"delivered_count": 1, "unsubscribe": False},
        {"delivered_count": 0, "unsubscribe": True},  # must not inflate denominator
    ]
    # Row 2 has delivered_count=0 → excluded; denominator=1, numerator=0
    assert scorer.callable_(rows) == pytest.approx(0.0)


def test_unsubscribe_rate_null_flag_excluded_from_denominator():
    scorer = resolve_scorer("sales:unsubscribe_rate")
    rows = [
        {"delivered_count": 1, "unsubscribe": True},
        {"delivered_count": 1, "unsubscribe": None},  # missing label — excluded entirely
        {"delivered_count": 1, "unsubscribe": False},
    ]
    # denominator=2 (None row dropped), numerator=1
    assert scorer.callable_(rows) == pytest.approx(0.5)


def test_unsubscribe_rate_zero_delivered_count_returns_zero():
    scorer = resolve_scorer("sales:unsubscribe_rate")
    rows = [{"delivered_count": 0, "unsubscribe": True}]
    assert scorer.callable_(rows) == 0.0


def test_unsubscribe_rate_missing_delivered_count_returns_zero():
    scorer = resolve_scorer("sales:unsubscribe_rate")
    rows = [{"unsubscribe": True}]  # no delivered_count key → treated as 0
    assert scorer.callable_(rows) == 0.0


def test_unsubscribe_rate_missing_label_key_returns_zero():
    scorer = resolve_scorer("sales:unsubscribe_rate")
    rows = [{"delivered_count": 1}]  # unsubscribe key absent → None → excluded
    assert scorer.callable_(rows) == 0.0


# ---------------------------------------------------------------------------
# 21. Guardrail compatibility for spam_complaint_rate and unsubscribe_rate
# ---------------------------------------------------------------------------


def _guardrail(name: str, threshold: float) -> RuntimeGuardrailSpec:
    return RuntimeGuardrailSpec(name=name, direction="lower_is_better", threshold=threshold)


def test_spam_complaint_rate_below_threshold_passes():
    rows = [{"delivered_count": 1, "spam_complaint": False}] * 99 + [
        {"delivered_count": 1, "spam_complaint": True}
    ]
    scorer = resolve_scorer("sales:spam_complaint_rate")
    rate = scorer.callable_(rows)
    guardrail = _guardrail("spam_complaint_rate", 0.02)
    result = evaluate_guardrails({"spam_complaint_rate": rate}, [guardrail])
    assert result.passed is True


def test_spam_complaint_rate_above_threshold_breaches():
    rows = [{"delivered_count": 1, "spam_complaint": True}] * 5 + [
        {"delivered_count": 1, "spam_complaint": False}
    ] * 5
    scorer = resolve_scorer("sales:spam_complaint_rate")
    rate = scorer.callable_(rows)
    guardrail = _guardrail("spam_complaint_rate", 0.02)
    result = evaluate_guardrails({"spam_complaint_rate": rate}, [guardrail])
    assert result.passed is False
    assert len(result.breaches) == 1


def test_spam_complaint_rate_zero_delivered_does_not_breach():
    rows = [{"delivered_count": 0, "spam_complaint": True}]
    scorer = resolve_scorer("sales:spam_complaint_rate")
    rate = scorer.callable_(rows)
    assert rate == 0.0
    guardrail = _guardrail("spam_complaint_rate", 0.02)
    result = evaluate_guardrails({"spam_complaint_rate": rate}, [guardrail])
    assert result.passed is True


def test_unsubscribe_rate_below_threshold_passes():
    rows = [{"delivered_count": 1, "unsubscribe": False}] * 99 + [
        {"delivered_count": 1, "unsubscribe": True}
    ]
    scorer = resolve_scorer("sales:unsubscribe_rate")
    rate = scorer.callable_(rows)
    result = evaluate_guardrails({"unsubscribe_rate": rate}, [_guardrail("unsubscribe_rate", 0.05)])
    assert result.passed is True


def test_unsubscribe_rate_above_threshold_breaches():
    rows = [{"delivered_count": 1, "unsubscribe": True}] * 3 + [
        {"delivered_count": 1, "unsubscribe": False}
    ] * 7
    scorer = resolve_scorer("sales:unsubscribe_rate")
    rate = scorer.callable_(rows)
    result = evaluate_guardrails({"unsubscribe_rate": rate}, [_guardrail("unsubscribe_rate", 0.05)])
    assert result.passed is False
    assert len(result.breaches) == 1


def test_unsubscribe_rate_zero_delivered_does_not_breach():
    rows = [{"delivered_count": 0, "unsubscribe": True}]
    scorer = resolve_scorer("sales:unsubscribe_rate")
    rate = scorer.callable_(rows)
    assert rate == 0.0
    result = evaluate_guardrails({"unsubscribe_rate": rate}, [_guardrail("unsubscribe_rate", 0.05)])
    assert result.passed is True
