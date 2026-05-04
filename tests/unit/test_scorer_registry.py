"""Unit tests for src/evaluation/scorers/."""

from __future__ import annotations

import pytest

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
from src.evaluation.spec_translation import _resolve_scorer_for_translation
from src.utils.metric_naming import validate_mlflow_metric_key

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
    assert refs == sorted(refs)


# ---------------------------------------------------------------------------
# 10. output_metric_keys pass validate_mlflow_metric_key
# ---------------------------------------------------------------------------


def test_builtin_metric_keys_are_mlflow_safe():
    for meta in list_scorers():
        for key in meta.output_metric_keys:
            # Should not raise
            validate_mlflow_metric_key(key)


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
    assert meta.metric_family == MetricFamily.OUTCOME
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
