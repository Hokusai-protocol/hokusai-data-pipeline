"""Adapter layer between the public model 30 contract and the MLflow artifact.

MLflow authentication is supplied by shared environment configuration such as
`MLFLOW_TRACKING_TOKEN` plus the mTLS setup applied during API startup.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd

from src.api.schemas import TechnicalTaskRouterInputs
from src.api.utils.config import get_settings

DEFAULT_MODEL_30_MLFLOW_URI = "models:/Technical Task Router/4"
MODEL_30_VERSION = "4"
MODEL_30_SCHEMA = "technical_task_router_inputs/v1"
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
_MODEL_30_WARMUP_LOCK: asyncio.Lock | None = None
_MODEL_30_WARMUP_ERROR: str | None = None
_MODEL_30_WARMED_AT: str | None = None
_MODEL_30_WARM_DURATION_MS: int | None = None


class Model30LoadInProgressError(RuntimeError):
    """Raised when a cold load is already running for the model URI."""


class Model30FailurePhase(str, Enum):
    """Structured failure phases for Model 30 MLflow inference."""

    ARTIFACT_LOAD = "artifact_load"
    PREDICT_CALL = "predict_call"
    RESPONSE_NORMALIZATION = "response_normalization"
    TIMEOUT = "timeout"
    MLFLOW_CONNECTIVITY = "mlflow_connectivity"


class Model30WarmupState(str, Enum):
    """Observed warmup state for the in-process model 30 cache."""

    NOT_STARTED = "not_started"
    WARMING = "warming"
    WARMED = "warmed"
    FAILED = "failed"


class Model30InferenceError(RuntimeError):
    """Typed Model 30 inference error that carries a failure phase."""

    def __init__(
        self: Model30InferenceError,
        message: str,
        *,
        phase: Model30FailurePhase,
        original_exc: BaseException,
    ) -> None:
        super().__init__(message)
        self.phase = phase
        self.original_exc = original_exc


_MODEL_30_WARMUP_STATE = Model30WarmupState.NOT_STARTED


def get_model_30_uri() -> str:
    """Resolve the model 30 URI from environment with a stable default."""
    return os.getenv("MODEL_30_MLFLOW_URI", DEFAULT_MODEL_30_MLFLOW_URI)


def reset_model_30_cache() -> None:
    """Clear the model cache for tests."""
    global _MODEL_30_WARMUP_STATE, _MODEL_30_WARMUP_LOCK, _MODEL_30_WARMUP_ERROR
    global _MODEL_30_WARMED_AT, _MODEL_30_WARM_DURATION_MS
    with _MODEL_30_CACHE_LOCK:
        _MODEL_30_CACHE.clear()
        _MODEL_30_LOAD_LOCKS.clear()
    _MODEL_30_WARMUP_STATE = Model30WarmupState.NOT_STARTED
    _MODEL_30_WARMUP_LOCK = None
    _MODEL_30_WARMUP_ERROR = None
    _MODEL_30_WARMED_AT = None
    _MODEL_30_WARM_DURATION_MS = None


def is_model_30_cached(model_uri: str) -> bool:
    """Return whether a model URI is already loaded into process cache."""
    return model_uri in _MODEL_30_CACHE


def set_model_30_warmup_state(
    state: Model30WarmupState,
    *,
    error: str | None = None,
    warmed_at: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Set the model 30 warmup state for readiness checks and tests."""
    global _MODEL_30_WARMUP_STATE, _MODEL_30_WARMUP_ERROR, _MODEL_30_WARMED_AT
    global _MODEL_30_WARM_DURATION_MS
    _MODEL_30_WARMUP_STATE = state
    _MODEL_30_WARMUP_ERROR = error
    _MODEL_30_WARMED_AT = warmed_at
    _MODEL_30_WARM_DURATION_MS = duration_ms


def get_model_30_warmup_state() -> dict[str, Any]:
    """Return public warmup status for readiness and serving gates."""
    return {
        "warmed": _MODEL_30_WARMUP_STATE == Model30WarmupState.WARMED,
        "state": _MODEL_30_WARMUP_STATE.value,
        "warmed_at": _MODEL_30_WARMED_AT,
        "last_error": _MODEL_30_WARMUP_ERROR,
        "duration_ms": _MODEL_30_WARM_DURATION_MS,
    }


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
    available_models = _sorted_unique(routing.available_models if routing else None)

    result: dict[str, Any] = {
        "task_type": task.task_type,
        "language": task.language,
        "framework": task.framework,
        "repo_type": task.repo_type,
        "domain": context.domain if context else None,
        "complexity": _derive_complexity(validated),
        "description_length_bucket": _bucket_description_length(len(description)),
        "files_touched_bucket": _bucket_files_touched(file_count),
        "available_planner_models": available_models,
        "available_coder_models": available_models,
        "available_reviewer_models": available_models,
        "max_cost_usd": routing.max_cost_usd if routing else None,
        "prioritize_quality": routing.prioritize_quality if routing else None,
        "prioritize_speed": routing.prioritize_speed if routing else None,
        "risk_level": context.risk_level if context else None,
        "requires_tests": context.requires_tests if context else None,
        "security_sensitive": context.security_sensitive if context else None,
        "repo_size_bucket": context.repo_size_bucket if context else None,
        "surface": workflow.surface if workflow else None,
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


def call_mlflow_model_30(
    model_uri: str,
    features: object,
    _timings: dict[str, float] | None = None,
) -> Any:
    """Load the cached MLflow model and invoke predict()."""
    load_started_at = time.perf_counter()
    try:
        model = _get_or_load_model_30(model_uri)
    except Model30LoadInProgressError:
        artifact_load_ms = (time.perf_counter() - load_started_at) * 1000
        if _timings is not None:
            _timings["artifact_load_ms"] = artifact_load_ms
        raise
    except Exception as exc:
        artifact_load_ms = (time.perf_counter() - load_started_at) * 1000
        if _timings is not None:
            _timings["artifact_load_ms"] = artifact_load_ms
        phase = (
            Model30FailurePhase.MLFLOW_CONNECTIVITY
            if _is_connectivity_error(exc)
            else Model30FailurePhase.ARTIFACT_LOAD
        )
        raise Model30InferenceError(
            str(exc)[:500],
            phase=phase,
            original_exc=exc,
        ) from exc
    artifact_load_ms = (time.perf_counter() - load_started_at) * 1000

    predict_started_at = time.perf_counter()
    try:
        result = model.predict(features)
    except Exception as exc:
        inference_only_ms = (time.perf_counter() - predict_started_at) * 1000
        if _timings is not None:
            _timings["artifact_load_ms"] = artifact_load_ms
            _timings["inference_only_ms"] = inference_only_ms
        raise Model30InferenceError(
            str(exc)[:500],
            phase=Model30FailurePhase.PREDICT_CALL,
            original_exc=exc,
        ) from exc
    inference_only_ms = (time.perf_counter() - predict_started_at) * 1000

    if _timings is not None:
        _timings["artifact_load_ms"] = artifact_load_ms
        _timings["inference_only_ms"] = inference_only_ms

    return result


def _get_model_30_warmup_lock() -> asyncio.Lock:
    global _MODEL_30_WARMUP_LOCK
    if _MODEL_30_WARMUP_LOCK is None:
        _MODEL_30_WARMUP_LOCK = asyncio.Lock()
    return _MODEL_30_WARMUP_LOCK


_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _resolve_model_30_warm_fixture_path(configured_path: str) -> Path:
    candidate = Path(configured_path)
    if candidate.is_absolute():
        return candidate
    return _PROJECT_ROOT / candidate


def _load_model_30_warm_fixture() -> dict[str, Any]:
    settings = get_settings()
    fixture_path = _resolve_model_30_warm_fixture_path(settings.model_30_warm_fixture_path)
    with fixture_path.open(encoding="utf-8") as fixture_file:
        payload = json.load(fixture_file)
    if not isinstance(payload, dict):
        raise ValueError("Model 30 warm fixture must contain a JSON object")
    return payload


async def warm_model_30(model_uri: str, timeout_s: float) -> dict[str, Any]:
    """Load the artifact into cache and run a minimal valid prediction."""
    logger = logging.getLogger(__name__)
    async with _get_model_30_warmup_lock():
        current_state = get_model_30_warmup_state()
        if current_state["warmed"]:
            return current_state

        set_model_30_warmup_state(Model30WarmupState.WARMING)
        started_at = time.perf_counter()
        logger.info(
            "model_30_warm_started",
            extra={"event": "model_30_warm_started", "model_uri": model_uri},
        )

        try:
            validated_inputs = validate_nested_model_30_inputs(_load_model_30_warm_fixture())
            features = model_30_inputs_to_features(validated_inputs)
            raw_output = await asyncio.wait_for(
                asyncio.to_thread(call_mlflow_model_30, model_uri, features, {}),
                timeout=timeout_s,
            )
            normalize_model_30_output(raw_output, validated_inputs)
        except asyncio.TimeoutError:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            error_message = f"warm timed out after {timeout_s:.1f}s"
            set_model_30_warmup_state(
                Model30WarmupState.FAILED,
                error=error_message,
                duration_ms=duration_ms,
            )
            logger.exception(
                "model_30_warm_failed",
                extra={
                    "event": "model_30_warm_failed",
                    "model_uri": model_uri,
                    "duration_ms": duration_ms,
                    "error": error_message,
                },
            )
            return get_model_30_warmup_state()
        except Exception as exc:  # noqa: BLE001 - warmup should capture and report all failures
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            error_message = str(exc)[:500]
            set_model_30_warmup_state(
                Model30WarmupState.FAILED,
                error=error_message,
                duration_ms=duration_ms,
            )
            logger.exception(
                "model_30_warm_failed",
                extra={
                    "event": "model_30_warm_failed",
                    "model_uri": model_uri,
                    "duration_ms": duration_ms,
                    "error": error_message,
                },
            )
            return get_model_30_warmup_state()

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        set_model_30_warmup_state(
            Model30WarmupState.WARMED,
            warmed_at=datetime.now(UTC).isoformat(),
            duration_ms=duration_ms,
        )
        logger.info(
            "model_30_warm_completed",
            extra={
                "event": "model_30_warm_completed",
                "model_uri": model_uri,
                "duration_ms": duration_ms,
            },
        )
        return get_model_30_warmup_state()


def normalize_model_30_output(
    raw_model_output: Any, validated_inputs: TechnicalTaskRouterInputs
) -> dict[str, Any]:
    """Normalize raw MLflow output into the public model 30 response contract."""
    del validated_inputs
    try:
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
    except Exception as exc:
        raise Model30InferenceError(
            str(exc)[:500],
            phase=Model30FailurePhase.RESPONSE_NORMALIZATION,
            original_exc=exc,
        ) from exc


def _is_connectivity_error(exc: BaseException) -> bool:
    if isinstance(exc, (OSError, ConnectionError)):
        return True
    msg = str(exc).lower()
    return any(
        kw in msg
        for kw in (
            "connection refused",
            "connection reset",
            "timeout",
            "503",
            "service unavailable",
            "name or service not known",
            "max retries",
            "remote end closed",
        )
    )


def log_model_30_failure(
    logger_: logging.Logger,
    *,
    request_id: str,
    model_uri: str,
    model_version: str | None,
    phase: Model30FailurePhase | str,
    path_type: str,
    exc: BaseException,
    duration_ms: float,
    level: int = logging.ERROR,
) -> None:
    """Emit a structured Model 30 failure log record."""
    phase_value = phase.value if isinstance(phase, Model30FailurePhase) else str(phase)
    logger_.log(
        level,
        "model_30_inference_failure",
        extra={
            "event_type": "model_30_inference_failure",
            "request_id": request_id,
            "model_uri": model_uri,
            "model_version": model_version,
            "phase": phase_value,
            "path_type": path_type,
            "exception_class": type(exc).__name__,
            "exception_message": str(exc)[:500],
            "duration_ms": round(duration_ms, 2),
        },
        exc_info=exc,
    )


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
