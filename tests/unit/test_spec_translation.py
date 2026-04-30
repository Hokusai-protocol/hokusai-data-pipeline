"""Unit tests for src/evaluation/spec_translation.py."""

from __future__ import annotations

import pytest

from src.evaluation.spec_translation import (
    RuntimeAdapterSpec,
    RuntimeGuardrailSpec,
    RuntimeMetricSpec,
    SpecTranslationError,
    translate_benchmark_spec,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_LEGACY_BASE: dict = {
    "spec_id": "spec-001",
    "provider": "hokusai",
    "model_id": "model-a",
    "dataset_id": "kaggle/mmlu",
    "dataset_version": "v1",
    "eval_split": "test",
    "metric_name": "accuracy",
    "metric_direction": "higher_is_better",
    "tiebreak_rules": None,
    "input_schema": {"columns": ["text"]},
    "output_schema": {"target_column": "label"},
    "eval_container_digest": None,
    "baseline_value": 0.85,
    "created_at": "2026-01-01T00:00:00+00:00",
    "is_active": True,
    "eval_spec": None,
}


def _legacy(**overrides: object) -> dict:
    return {**_LEGACY_BASE, **overrides}


_V1_PRIMARY = {
    "name": "accuracy",
    "direction": "higher_is_better",
    "threshold": 0.9,
    "unit": "fraction",
}

_V1_SECONDARY = [
    {"name": "f1_macro", "direction": "higher_is_better"},
]

_V1_GUARDRAILS = [
    {
        "name": "toxicity",
        "direction": "lower_is_better",
        "threshold": 0.1,
        "blocking": True,
    }
]

_FULL_EVAL_SPEC = {
    "primary_metric": _V1_PRIMARY,
    "secondary_metrics": _V1_SECONDARY,
    "guardrails": _V1_GUARDRAILS,
    "measurement_policy": {"window": "rolling"},
    "label_policy": {"schema": "binary"},
    "coverage_policy": {"min_coverage": 0.95},
    "unit_of_analysis": "session",
    "min_examples": 100,
}


# ---------------------------------------------------------------------------
# Legacy path
# ---------------------------------------------------------------------------


def test_legacy_row_basic() -> None:
    row = _legacy()
    spec = translate_benchmark_spec(row)

    assert isinstance(spec, RuntimeAdapterSpec)
    assert spec.spec_id == "spec-001"
    assert spec.model_id == "model-a"
    assert spec.primary_metric.name == "accuracy"
    assert spec.primary_metric.direction == "higher_is_better"
    assert spec.primary_metric.threshold == pytest.approx(0.85)
    assert spec.secondary_metrics == ()
    assert spec.guardrails == ()
    assert spec.measurement_policy is None


def test_legacy_row_no_baseline() -> None:
    row = _legacy(baseline_value=None)
    spec = translate_benchmark_spec(row)
    assert spec.primary_metric.threshold is None


def test_legacy_row_eval_spec_key_missing() -> None:
    row = {k: v for k, v in _LEGACY_BASE.items() if k != "eval_spec"}
    spec = translate_benchmark_spec(row)
    assert spec.primary_metric.name == "accuracy"


def test_legacy_missing_metric_name() -> None:
    row = _legacy(metric_name=None)
    with pytest.raises(SpecTranslationError) as exc_info:
        translate_benchmark_spec(row)
    assert "metric_name" in str(exc_info.value)


def test_legacy_metric_name_empty_string() -> None:
    row = _legacy(metric_name="")
    with pytest.raises(SpecTranslationError) as exc_info:
        translate_benchmark_spec(row)
    assert "metric_name" in str(exc_info.value)


def test_legacy_invalid_direction() -> None:
    row = _legacy(metric_direction="wibble")
    with pytest.raises(SpecTranslationError) as exc_info:
        translate_benchmark_spec(row)
    assert "metric_direction" in str(exc_info.value)
    assert "wibble" in str(exc_info.value)


# ---------------------------------------------------------------------------
# v1 path
# ---------------------------------------------------------------------------


def test_v1_full() -> None:
    row = _legacy(eval_spec=_FULL_EVAL_SPEC)
    spec = translate_benchmark_spec(row)

    assert spec.primary_metric.name == "accuracy"
    assert spec.primary_metric.direction == "higher_is_better"
    assert spec.primary_metric.threshold == pytest.approx(0.9)
    assert spec.primary_metric.unit == "fraction"

    assert len(spec.secondary_metrics) == 1
    assert spec.secondary_metrics[0].name == "f1_macro"

    assert len(spec.guardrails) == 1
    g = spec.guardrails[0]
    assert isinstance(g, RuntimeGuardrailSpec)
    assert g.name == "toxicity"
    assert g.direction == "lower_is_better"
    assert g.threshold == pytest.approx(0.1)
    assert g.blocking is True

    assert spec.measurement_policy == {"window": "rolling"}
    assert spec.label_policy == {"schema": "binary"}
    assert spec.coverage_policy == {"min_coverage": 0.95}
    assert spec.unit_of_analysis == "session"
    assert spec.min_examples == 100


def test_v1_minimal() -> None:
    eval_spec = {"primary_metric": {"name": "f1", "direction": "higher_is_better"}}
    row = _legacy(eval_spec=eval_spec)
    spec = translate_benchmark_spec(row)

    assert spec.primary_metric.name == "f1"
    assert spec.secondary_metrics == ()
    assert spec.guardrails == ()
    assert spec.measurement_policy is None
    assert spec.label_policy is None
    assert spec.coverage_policy is None
    assert spec.unit_of_analysis is None
    assert spec.min_examples is None


def test_v1_empty_dict() -> None:
    row = _legacy(eval_spec={})
    with pytest.raises(SpecTranslationError) as exc_info:
        translate_benchmark_spec(row)
    assert "eval_spec.primary_metric" in str(exc_info.value)


def test_v1_missing_primary_metric() -> None:
    row = _legacy(eval_spec={"secondary_metrics": []})
    with pytest.raises(SpecTranslationError) as exc_info:
        translate_benchmark_spec(row)
    assert "eval_spec.primary_metric" in str(exc_info.value)


def test_v1_missing_metric_name() -> None:
    row = _legacy(eval_spec={"primary_metric": {"direction": "higher_is_better"}})
    with pytest.raises(SpecTranslationError) as exc_info:
        translate_benchmark_spec(row)
    assert "eval_spec.primary_metric.name" in str(exc_info.value)


def test_v1_invalid_metric_direction() -> None:
    row = _legacy(eval_spec={"primary_metric": {"name": "acc", "direction": "wibble"}})
    with pytest.raises(SpecTranslationError) as exc_info:
        translate_benchmark_spec(row)
    assert "eval_spec.primary_metric.direction" in str(exc_info.value)
    assert "wibble" in str(exc_info.value)


def test_v1_secondary_metrics_wrong_type() -> None:
    row = _legacy(eval_spec={"primary_metric": _V1_PRIMARY, "secondary_metrics": "not a list"})
    with pytest.raises(SpecTranslationError) as exc_info:
        translate_benchmark_spec(row)
    assert "secondary_metrics" in str(exc_info.value)


def test_v1_guardrails_wrong_type() -> None:
    row = _legacy(eval_spec={"primary_metric": _V1_PRIMARY, "guardrails": {}})
    with pytest.raises(SpecTranslationError) as exc_info:
        translate_benchmark_spec(row)
    assert "guardrails" in str(exc_info.value)


def test_v1_guardrail_missing_threshold() -> None:
    row = _legacy(
        eval_spec={
            "primary_metric": _V1_PRIMARY,
            "guardrails": [{"name": "toxicity", "direction": "lower_is_better"}],
        }
    )
    with pytest.raises(SpecTranslationError) as exc_info:
        translate_benchmark_spec(row)
    assert "threshold" in str(exc_info.value)


def test_v1_scorer_refs_preserved() -> None:
    primary = {
        "name": "accuracy",
        "direction": "higher_is_better",
        "scorer_ref": "scorers.accuracy_v2",
        "source_hash": "abc123",
    }
    row = _legacy(eval_spec={"primary_metric": primary})
    spec = translate_benchmark_spec(row)

    assert spec.primary_metric.scorer_ref == "scorers.accuracy_v2"
    assert spec.primary_metric.source_hash == "abc123"


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------


def test_public_exports() -> None:
    assert callable(translate_benchmark_spec)
    assert RuntimeAdapterSpec is not None
    assert SpecTranslationError is not None
    assert RuntimeMetricSpec is not None
    assert RuntimeGuardrailSpec is not None
