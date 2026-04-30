"""Translate BenchmarkSpecService row dicts into typed runtime adapter specs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

_VALID_DIRECTIONS = frozenset({"higher_is_better", "lower_is_better"})


class SpecTranslationError(ValueError):
    """Raised when a BenchmarkSpecService row cannot be translated."""

    def __init__(self: SpecTranslationError, field_path: str, message: str) -> None:
        self.field_path = field_path
        super().__init__(f"{field_path}: {message}")


@dataclass(frozen=True)
class RuntimeMetricSpec:
    """Metric specification consumed by runtime adapters."""

    name: str
    direction: Literal["higher_is_better", "lower_is_better"]
    threshold: float | None = None
    unit: str | None = None
    scorer_ref: str | None = None
    source_hash: str | None = None


@dataclass(frozen=True)
class RuntimeGuardrailSpec:
    """Hard constraint evaluated by runtime adapters."""

    name: str
    direction: Literal["higher_is_better", "lower_is_better"]
    threshold: float
    blocking: bool = True
    scorer_ref: str | None = None
    source_hash: str | None = None


@dataclass(frozen=True)
class RuntimeAdapterSpec:
    """Fully translated spec consumed by evaluation adapters."""

    spec_id: str
    model_id: str
    dataset_id: str
    dataset_version: str
    eval_split: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    primary_metric: RuntimeMetricSpec
    secondary_metrics: tuple[RuntimeMetricSpec, ...] = field(default_factory=tuple)
    guardrails: tuple[RuntimeGuardrailSpec, ...] = field(default_factory=tuple)
    measurement_policy: dict[str, Any] | None = None
    label_policy: dict[str, Any] | None = None
    coverage_policy: dict[str, Any] | None = None
    unit_of_analysis: str | None = None
    min_examples: int | None = None
    eval_container_digest: str | None = None
    baseline_value: float | None = None
    is_active: bool = True
    metric_family: str = "proportion"


def _resolve_scorer_for_translation(ref: str | None) -> object:
    """Return the RegisteredScorer for *ref*, or None if ref is None.

    Lazy import avoids a circular-import risk and keeps the scorer registry
    optional for callers that never use custom scorers.
    """
    if ref is None:
        return None
    from src.evaluation.scorers import resolve_scorer  # noqa: PLC0415

    return resolve_scorer(ref)


def translate_benchmark_spec(row: dict[str, Any]) -> RuntimeAdapterSpec:
    """Translate a BenchmarkSpecService row dict into a RuntimeAdapterSpec."""
    eval_spec = row.get("eval_spec")
    if eval_spec is not None:
        return _translate_v1(eval_spec, row)
    return _translate_legacy(row)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require(d: dict[str, Any], key: str, field_path: str) -> Any:
    if key not in d:
        raise SpecTranslationError(field_path, f"required field '{key}' is missing")
    return d[key]


def _require_str(d: dict[str, Any], key: str, field_path: str) -> str:
    value = _require(d, key, field_path)
    if not isinstance(value, str) or not value:
        raise SpecTranslationError(field_path, f"'{key}' must be a non-empty string")
    return value


def _require_direction(d: dict[str, Any], key: str, field_path: str) -> str:
    value = _require(d, key, field_path)
    if value not in _VALID_DIRECTIONS:
        raise SpecTranslationError(
            field_path,
            f"'{key}' must be one of {sorted(_VALID_DIRECTIONS)}, got {value!r}",
        )
    return value  # type: ignore[return-value]


def _parse_metric_spec(d: Any, path: str) -> RuntimeMetricSpec:
    if not isinstance(d, dict):
        raise SpecTranslationError(path, "expected a dict")
    name = _require_str(d, "name", f"{path}.name")
    direction = _require_direction(d, "direction", f"{path}.direction")
    threshold = d.get("threshold")
    if threshold is not None and not isinstance(threshold, (int, float)):
        raise SpecTranslationError(f"{path}.threshold", "must be a number")
    unit = d.get("unit")
    if unit is not None and not isinstance(unit, str):
        raise SpecTranslationError(f"{path}.unit", "must be a string")
    return RuntimeMetricSpec(
        name=name,
        direction=direction,  # type: ignore[arg-type]
        threshold=float(threshold) if threshold is not None else None,
        unit=unit,
        scorer_ref=d.get("scorer_ref"),
        source_hash=d.get("source_hash"),
    )


def _parse_guardrail_spec(d: Any, path: str) -> RuntimeGuardrailSpec:
    if not isinstance(d, dict):
        raise SpecTranslationError(path, "expected a dict")
    name = _require_str(d, "name", f"{path}.name")
    direction = _require_direction(d, "direction", f"{path}.direction")
    if "threshold" not in d:
        raise SpecTranslationError(f"{path}.threshold", "required field 'threshold' is missing")
    threshold = d["threshold"]
    if not isinstance(threshold, (int, float)):
        raise SpecTranslationError(f"{path}.threshold", "must be a number")
    blocking = d.get("blocking", True)
    if not isinstance(blocking, bool):
        raise SpecTranslationError(f"{path}.blocking", "must be a bool")
    return RuntimeGuardrailSpec(
        name=name,
        direction=direction,  # type: ignore[arg-type]
        threshold=float(threshold),
        blocking=blocking,
        scorer_ref=d.get("scorer_ref"),
        source_hash=d.get("source_hash"),
    )


def _common_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "spec_id": str(row.get("spec_id", "")),
        "model_id": str(row.get("model_id", "")),
        "dataset_id": str(row.get("dataset_id", "")),
        "dataset_version": str(row.get("dataset_version", "")),
        "eval_split": str(row.get("eval_split", "")),
        "input_schema": dict(row.get("input_schema") or {}),
        "output_schema": dict(row.get("output_schema") or {}),
        "eval_container_digest": row.get("eval_container_digest"),
        "baseline_value": row.get("baseline_value"),
        "is_active": bool(row.get("is_active", True)),
    }


def _translate_legacy(row: dict[str, Any]) -> RuntimeAdapterSpec:
    metric_name = row.get("metric_name")
    if not isinstance(metric_name, str) or not metric_name:
        raise SpecTranslationError(
            "metric_name", "required field 'metric_name' must be a non-empty string"
        )
    metric_direction = row.get("metric_direction")
    if metric_direction not in _VALID_DIRECTIONS:
        raise SpecTranslationError(
            "metric_direction",
            f"must be one of {sorted(_VALID_DIRECTIONS)}, got {metric_direction!r}",
        )
    baseline = row.get("baseline_value")
    primary = RuntimeMetricSpec(
        name=metric_name,
        direction=metric_direction,  # type: ignore[arg-type]
        threshold=float(baseline) if baseline is not None else None,
    )
    return RuntimeAdapterSpec(
        **_common_fields(row),
        primary_metric=primary,
        secondary_metrics=(),
        guardrails=(),
    )


def _translate_v1(eval_spec: Any, row: dict[str, Any]) -> RuntimeAdapterSpec:
    if not isinstance(eval_spec, dict):
        raise SpecTranslationError("eval_spec", "must be a dict")

    primary = _parse_metric_spec(
        _require(eval_spec, "primary_metric", "eval_spec.primary_metric"),
        "eval_spec.primary_metric",
    )

    raw_secondary = eval_spec.get("secondary_metrics", [])
    if not isinstance(raw_secondary, list):
        raise SpecTranslationError(
            "eval_spec.secondary_metrics", f"expected a list, got {type(raw_secondary).__name__}"
        )
    secondary: tuple[RuntimeMetricSpec, ...] = tuple(
        _parse_metric_spec(item, f"eval_spec.secondary_metrics[{i}]")
        for i, item in enumerate(raw_secondary)
    )

    raw_guardrails = eval_spec.get("guardrails", [])
    if not isinstance(raw_guardrails, list):
        raise SpecTranslationError(
            "eval_spec.guardrails", f"expected a list, got {type(raw_guardrails).__name__}"
        )
    guardrails: tuple[RuntimeGuardrailSpec, ...] = tuple(
        _parse_guardrail_spec(item, f"eval_spec.guardrails[{i}]")
        for i, item in enumerate(raw_guardrails)
    )

    measurement_policy = eval_spec.get("measurement_policy")
    if measurement_policy is not None and not isinstance(measurement_policy, dict):
        raise SpecTranslationError("eval_spec.measurement_policy", "must be a dict or null")

    label_policy = eval_spec.get("label_policy")
    if label_policy is not None and not isinstance(label_policy, dict):
        raise SpecTranslationError("eval_spec.label_policy", "must be a dict or null")

    coverage_policy = eval_spec.get("coverage_policy")
    if coverage_policy is not None and not isinstance(coverage_policy, dict):
        raise SpecTranslationError("eval_spec.coverage_policy", "must be a dict or null")

    unit_of_analysis = eval_spec.get("unit_of_analysis")
    if unit_of_analysis is not None and not isinstance(unit_of_analysis, str):
        raise SpecTranslationError("eval_spec.unit_of_analysis", "must be a string or null")

    min_examples = eval_spec.get("min_examples")
    if min_examples is not None and not isinstance(min_examples, int):
        raise SpecTranslationError("eval_spec.min_examples", "must be an int or null")

    metric_family = eval_spec.get("metric_family", "proportion")
    if not isinstance(metric_family, str):
        raise SpecTranslationError("eval_spec.metric_family", "must be a string or null")

    return RuntimeAdapterSpec(
        **_common_fields(row),
        primary_metric=primary,
        secondary_metrics=secondary,
        guardrails=guardrails,
        measurement_policy=measurement_policy,
        label_policy=label_policy,
        coverage_policy=coverage_policy,
        unit_of_analysis=unit_of_analysis,
        min_examples=min_examples,
        metric_family=metric_family,
    )
