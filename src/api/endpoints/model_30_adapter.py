"""Adapter layer between the public model 30 contract and the MLflow artifact.

MLflow authentication is supplied by shared environment configuration such as
`MLFLOW_TRACKING_TOKEN` plus the mTLS setup applied during API startup.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Mapping
from typing import Any

import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd

from src.api.schemas import TechnicalTaskRouterInputs

DEFAULT_MODEL_30_MLFLOW_URI = "models:/Technical Task Router/4"
MODEL_30_VERSION = "4"
MODEL_30_SCHEMA = "technical_task_router_inputs/v2"
ROUTER_FEATURE_COLUMNS: tuple[str, ...] = (
    "task_type",
    "language",
    "framework",
    "repo_type",
    "domain",
    "complexity",
    "description_length_bucket",
    "files_touched_bucket",
    "available_planner_models",
    "available_coder_models",
    "available_reviewer_models",
    "max_cost_usd",
    "prioritize_quality",
    "prioritize_speed",
    "risk_level",
    "requires_tests",
    "security_sensitive",
    "repo_size_bucket",
    "surface",
    "workflow_stages",
    "routing_objective",
    "is_greenfield",
    "is_migration",
    "cross_service",
    "ui_heavy",
)

_ROUTER_LEAKAGE_COLUMNS: frozenset[str] = frozenset(
    {
        "selected_model",
        "selected_models",
        "selected_planner_model",
        "selected_coder_model",
        "selected_reviewer_model",
        "actual_cost_usd",
        "actual_time_seconds",
        "intervention_count",
        "retry_count",
        "completed_successfully",
        "intervention_required",
    }
)

_DESCRIPTION_SHORT_MAX = 200
_DESCRIPTION_MEDIUM_MAX = 1000
_FILES_SMALL_MAX = 5
_FILES_MEDIUM_MAX = 15

_GREENFIELD_KEYWORDS = re.compile(
    r"\b(greenfield|from scratch|new project|scaffold|bootstrap)\b",
    re.I,
)
_MIGRATION_KEYWORDS = re.compile(r"\b(migrat\w*|port|upgrade|convert|replatform)\b", re.I)
_CROSS_SERVICE_KEYWORDS = re.compile(
    r"\b(cross[-\s]?service|multi[-\s]?service|across services|"
    r"service boundary|inter[-\s]?service)\b",
    re.I,
)
_UI_KEYWORDS = re.compile(
    r"\b(ui|frontend|front[-\s]?end|react|vue|angular|css|html|dashboard|"
    r"component|page|screen)\b",
    re.I,
)

_MODEL_30_CACHE: dict[str, Any] = {}
_MODEL_30_CACHE_LOCK = threading.Lock()
_MODEL_30_LOAD_LOCKS: dict[str, threading.Lock] = {}


class Model30LoadInProgressError(RuntimeError):
    """Raised when a cold load is already running for the model URI."""


def get_model_30_uri() -> str:
    """Resolve the model 30 URI from environment with a stable default."""
    return os.getenv("MODEL_30_MLFLOW_URI", DEFAULT_MODEL_30_MLFLOW_URI)


def reset_model_30_cache() -> None:
    """Clear the model cache for tests."""
    with _MODEL_30_CACHE_LOCK:
        _MODEL_30_CACHE.clear()
        _MODEL_30_LOAD_LOCKS.clear()


def is_model_30_cached(model_uri: str) -> bool:
    """Return whether a model URI is already loaded into process cache."""
    return model_uri in _MODEL_30_CACHE


def validate_nested_model_30_inputs(raw_inputs: dict[str, Any]) -> TechnicalTaskRouterInputs:
    """Validate the public nested input contract for model 30."""
    return TechnicalTaskRouterInputs.model_validate(raw_inputs)


def map_nested_to_router_features(validated: TechnicalTaskRouterInputs) -> dict[str, Any]:
    """Translate nested public model 30 inputs to the router training schema."""
    task = validated.task
    routing = validated.routing
    context = validated.context
    workflow = validated.workflow

    description = task.description or ""
    file_count = context.file_count if context and context.file_count is not None else 0

    result: dict[str, Any] = {
        "task_type": task.task_type,
        "language": task.language,
        "framework": task.framework,
        "repo_type": task.repo_type,
        "domain": context.domain if context else None,
        "complexity": _derive_complexity(validated),
        "description_length_bucket": _bucket_description_length(len(description)),
        "files_touched_bucket": _bucket_files_touched(file_count),
        "available_planner_models": _role_available_models(routing, "planner"),
        "available_coder_models": _role_available_models(routing, "coder"),
        "available_reviewer_models": _role_available_models(routing, "reviewer"),
        "max_cost_usd": routing.max_cost_usd if routing else None,
        "prioritize_quality": routing.prioritize_quality if routing else None,
        "prioritize_speed": routing.prioritize_speed if routing else None,
        "risk_level": context.risk_level if context else None,
        "requires_tests": context.requires_tests if context else None,
        "security_sensitive": context.security_sensitive if context else None,
        "repo_size_bucket": context.repo_size_bucket if context else None,
        "surface": workflow.surface if workflow else None,
        "workflow_stages": [stage.value for stage in workflow.stages]
        if workflow and workflow.stages
        else None,
        "routing_objective": routing.objective.value if routing else None,
        **_detect_boolean_flags(description),
    }

    if tuple(result) != ROUTER_FEATURE_COLUMNS:
        missing = set(ROUTER_FEATURE_COLUMNS) - set(result)
        extra = set(result) - set(ROUTER_FEATURE_COLUMNS)
        raise ValueError(
            "Router feature mapper emitted unexpected schema "
            f"(missing={sorted(missing)}, extra={sorted(extra)})"
        )
    leaked = set(result) & _ROUTER_LEAKAGE_COLUMNS
    if leaked:
        raise ValueError(f"Router feature mapper emitted leakage columns: {sorted(leaked)}")

    return result


def model_30_inputs_to_features(validated_inputs: TechnicalTaskRouterInputs) -> pd.DataFrame:
    """Map nested public inputs into a flat one-row feature frame for MLflow pyfunc."""
    router_features = map_nested_to_router_features(validated_inputs)
    return pd.DataFrame([router_features], columns=ROUTER_FEATURE_COLUMNS)


def _bucket_description_length(length: int) -> str:
    if length <= _DESCRIPTION_SHORT_MAX:
        return "short"
    if length <= _DESCRIPTION_MEDIUM_MAX:
        return "medium"
    return "long"


def _bucket_files_touched(file_count: int) -> str:
    if file_count <= 1:
        return "1"
    if file_count <= _FILES_SMALL_MAX:
        return "2_5"
    if file_count <= _FILES_MEDIUM_MAX:
        return "6_15"
    return "16_plus"


def _derive_complexity(validated: TechnicalTaskRouterInputs) -> str:
    context = validated.context
    if context and context.estimated_complexity:
        return context.estimated_complexity

    description = validated.task.description or ""
    file_count = context.file_count if context and context.file_count is not None else 0
    description_bucket = _bucket_description_length(len(description))
    files_bucket = _bucket_files_touched(file_count)

    if description_bucket == "long" or files_bucket == "16_plus":
        return "high"
    if description_bucket == "medium" or files_bucket == "6_15":
        return "medium"
    return "low"


def _detect_boolean_flags(description: str) -> dict[str, bool]:
    return {
        "is_greenfield": bool(_GREENFIELD_KEYWORDS.search(description)),
        "is_migration": bool(_MIGRATION_KEYWORDS.search(description)),
        "cross_service": bool(_CROSS_SERVICE_KEYWORDS.search(description)),
        "ui_heavy": bool(_UI_KEYWORDS.search(description)),
    }


def _sorted_unique(values: list[str] | None) -> list[str]:
    if not values:
        return []
    return sorted(set(values))


def _role_available_models(routing: Any, role: str) -> list[str]:
    if routing is None:
        return []
    role_values = getattr(routing, f"available_{role}_models")
    return _sorted_unique(role_values or routing.available_models)


def call_mlflow_model_30(
    model_uri: str,
    features: object,
    _timings: dict[str, float] | None = None,
) -> Any:
    """Load the cached MLflow model and invoke predict()."""
    load_started_at = time.perf_counter()
    model = _get_or_load_model_30(model_uri)
    artifact_load_ms = (time.perf_counter() - load_started_at) * 1000

    predict_started_at = time.perf_counter()
    result = model.predict(features)
    inference_only_ms = (time.perf_counter() - predict_started_at) * 1000

    if _timings is not None:
        _timings["artifact_load_ms"] = artifact_load_ms
        _timings["inference_only_ms"] = inference_only_ms

    return result


def normalize_model_30_output(
    raw_model_output: Any, validated_inputs: TechnicalTaskRouterInputs
) -> dict[str, Any]:
    """Normalize raw MLflow output into the public model 30 response contract."""
    del validated_inputs
    normalized = _coerce_model_output(raw_model_output)

    selected_models = _extract_selected_models(normalized)
    selected_model = normalized.get("selected_model")
    if selected_model is None and selected_models:
        selected_model = selected_models[0]
    if selected_model is not None and not selected_models:
        selected_models = [selected_model]

    if not selected_model:
        raise ValueError("MLflow output did not contain a usable selected model")

    return {
        "selected_model": str(selected_model),
        "selected_models": [str(model_name) for model_name in selected_models],
        "confidence": _coerce_float(normalized.get("confidence"), default=0.0),
        "rationale": _coerce_string(normalized.get("rationale"), default=""),
        "estimated_cost_usd": _coerce_float(
            normalized.get("estimated_cost_usd"),
            default=0.0,
        ),
    }


def _get_or_load_model_30(model_uri: str) -> Any:
    cached_model = _MODEL_30_CACHE.get(model_uri)
    if cached_model is not None:
        return cached_model

    with _MODEL_30_CACHE_LOCK:
        load_lock = _MODEL_30_LOAD_LOCKS.setdefault(model_uri, threading.Lock())
        cached_model = _MODEL_30_CACHE.get(model_uri)
        if cached_model is not None:
            return cached_model

    if not load_lock.acquire(blocking=False):
        raise Model30LoadInProgressError(
            f"Model 30 cold load is already in progress for {model_uri}"
        )

    try:
        with _MODEL_30_CACHE_LOCK:
            cached_model = _MODEL_30_CACHE.get(model_uri)
            if cached_model is not None:
                return cached_model

        loaded_model = mlflow.pyfunc.load_model(model_uri)
        with _MODEL_30_CACHE_LOCK:
            _MODEL_30_CACHE[model_uri] = loaded_model
        return loaded_model
    finally:
        load_lock.release()


def _coerce_model_output(raw_model_output: Any) -> dict[str, Any]:
    if raw_model_output is None:
        raise ValueError("MLflow output was empty")

    if isinstance(raw_model_output, pd.DataFrame):
        return _coerce_tabular_output(raw_model_output)

    if isinstance(raw_model_output, pd.Series):
        return _coerce_series_output(raw_model_output)

    if isinstance(raw_model_output, Mapping):
        return _normalize_mapping(dict(raw_model_output))

    if isinstance(raw_model_output, list):
        return _coerce_sequence_output(raw_model_output, sequence_label="list")

    if isinstance(raw_model_output, np.ndarray):
        return _coerce_sequence_output(
            raw_model_output.flatten().tolist(),
            sequence_label="ndarray",
        )

    if isinstance(raw_model_output, str):
        return {"selected_model": raw_model_output}

    raise ValueError(f"Unsupported MLflow output type: {type(raw_model_output).__name__}")


def _coerce_tabular_output(raw_model_output: pd.DataFrame) -> dict[str, Any]:
    if raw_model_output.empty:
        raise ValueError("MLflow output was empty")
    return _normalize_mapping(raw_model_output.iloc[0].to_dict())


def _coerce_series_output(raw_model_output: pd.Series) -> dict[str, Any]:
    if raw_model_output.empty:
        raise ValueError("MLflow output was empty")
    return _normalize_mapping(raw_model_output.to_dict())


def _coerce_sequence_output(raw_items: list[Any], *, sequence_label: str) -> dict[str, Any]:
    if not raw_items:
        raise ValueError("MLflow output was empty")
    first_item = raw_items[0]
    if isinstance(first_item, Mapping):
        return _normalize_mapping(dict(first_item))
    if isinstance(first_item, str):
        return {"selected_model": first_item}
    raise ValueError(f"MLflow output {sequence_label} had an unsupported shape")


def _normalize_mapping(raw_mapping: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "selected_model": ("selected_model", "model", "selected", "prediction"),
        "selected_models": ("selected_models", "models"),
        "confidence": ("confidence", "score", "probability"),
        "rationale": ("rationale", "reason", "explanation"),
        "estimated_cost_usd": ("estimated_cost_usd", "estimated_cost", "cost"),
    }

    normalized: dict[str, Any] = {}
    for canonical_key, possible_keys in aliases.items():
        for key in possible_keys:
            if key in raw_mapping and raw_mapping[key] is not None:
                normalized[canonical_key] = raw_mapping[key]
                break
    return normalized


def _extract_selected_models(normalized: dict[str, Any]) -> list[str]:
    raw_selected_models = normalized.get("selected_models")
    if raw_selected_models is None:
        return []
    if isinstance(raw_selected_models, str):
        return [raw_selected_models]
    if isinstance(raw_selected_models, np.ndarray):
        raw_selected_models = raw_selected_models.flatten().tolist()
    if isinstance(raw_selected_models, list):
        return [str(model_name) for model_name in raw_selected_models if model_name]
    raise ValueError("MLflow output selected_models field had an unsupported shape")


def _coerce_float(value: Any, *, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_string(value: Any, *, default: str) -> str:
    if value is None:
        return default
    return str(value)
