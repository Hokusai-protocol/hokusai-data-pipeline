"""Adapter layer between the public model 27 contract and its MLflow artifact.

MLflow authentication is supplied by shared environment configuration such as
`MLFLOW_TRACKING_TOKEN` plus the mTLS setup applied during API startup.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Mapping, Sequence
from typing import Any

import mlflow.pyfunc
import numpy as np
import pandas as pd

from src.api.endpoints.model_30_adapter import (
    Model30FailurePhase,
    Model30InferenceError,
    Model30LoadInProgressError,
)
from src.api.schemas import MODEL_27_INPUT_FIELDS, SalesLeadScoringInputs

DEFAULT_MODEL_27_MLFLOW_URI = "models:/Sales Lead Scoring@production"
MODEL_27_VERSION = "production"
MODEL_27_SCHEMA = "sales_lead_scoring_inputs/v1"
MODEL_27_FEATURE_COLUMNS: tuple[str, ...] = MODEL_27_INPUT_FIELDS

_MODEL_27_CACHE: dict[str, Any] = {}
_MODEL_27_CACHE_LOCK = threading.Lock()
_MODEL_27_LOAD_LOCKS: dict[str, threading.Lock] = {}


class Model27LoadInProgressError(Model30LoadInProgressError):
    """Raised when a cold load is already running for a Model 27 URI."""


def get_model_27_uri() -> str:
    """Resolve the model 27 URI from environment with a stable default."""
    return os.getenv("MODEL_27_MLFLOW_URI", DEFAULT_MODEL_27_MLFLOW_URI)


def reset_model_27_cache() -> None:
    """Clear the model 27 in-process cache for tests."""
    with _MODEL_27_CACHE_LOCK:
        _MODEL_27_CACHE.clear()
        _MODEL_27_LOAD_LOCKS.clear()


def is_model_27_cached(model_uri: str) -> bool:
    """Return whether a model URI is already loaded into process cache."""
    return model_uri in _MODEL_27_CACHE


def validate_sales_lead_scoring_inputs(raw: dict[str, Any]) -> SalesLeadScoringInputs:
    """Validate the public Model 27 payload."""
    return SalesLeadScoringInputs.model_validate(raw)


def sales_lead_scoring_inputs_to_features(validated: SalesLeadScoringInputs) -> pd.DataFrame:
    """Map the public request schema to the MLflow feature frame."""
    row = validated.model_dump(by_alias=True)
    return pd.DataFrame([row], columns=MODEL_27_FEATURE_COLUMNS)


def call_mlflow_model_27(
    model_uri: str,
    features: object,
    _timings: dict[str, float] | None = None,
) -> Any:
    """Load the cached MLflow model and invoke predict()."""
    load_started_at = time.perf_counter()
    try:
        model = _get_or_load_model_27(model_uri)
    except Model27LoadInProgressError:
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


def normalize_model_27_output(
    raw_model_output: Any,
    validated_inputs: SalesLeadScoringInputs,
) -> dict[str, Any]:
    """Normalize Model 27 MLflow output to the public lead-scoring contract."""
    del validated_inputs
    try:
        normalized = _coerce_model_output(raw_model_output)
        probability = _extract_probability(normalized)
        lead_score = _extract_lead_score(normalized, probability)
        confidence = _extract_confidence(normalized, probability)
        return {
            "lead_score": lead_score,
            "conversion_probability": probability,
            "recommendation": _recommendation_for_score(lead_score),
            "confidence": confidence,
        }
    except Exception as exc:
        raise Model30InferenceError(
            str(exc)[:500],
            phase=Model30FailurePhase.RESPONSE_NORMALIZATION,
            original_exc=exc,
        ) from exc


def _get_or_load_model_27(model_uri: str) -> Any:
    cached_model = _MODEL_27_CACHE.get(model_uri)
    if cached_model is not None:
        return cached_model

    with _MODEL_27_CACHE_LOCK:
        load_lock = _MODEL_27_LOAD_LOCKS.setdefault(model_uri, threading.Lock())
        cached_model = _MODEL_27_CACHE.get(model_uri)
        if cached_model is not None:
            return cached_model

    if not load_lock.acquire(blocking=False):
        raise Model27LoadInProgressError(
            f"Model 27 cold load is already in progress for {model_uri}"
        )

    try:
        with _MODEL_27_CACHE_LOCK:
            cached_model = _MODEL_27_CACHE.get(model_uri)
            if cached_model is not None:
                return cached_model

        loaded_model = mlflow.pyfunc.load_model(model_uri)
        with _MODEL_27_CACHE_LOCK:
            _MODEL_27_CACHE[model_uri] = loaded_model
        return loaded_model
    finally:
        load_lock.release()


def _coerce_model_output(raw_model_output: Any) -> dict[str, Any]:
    if raw_model_output is None:
        raise ValueError("MLflow output was empty")

    if isinstance(raw_model_output, pd.DataFrame):
        if raw_model_output.empty:
            raise ValueError("MLflow output was empty")
        return dict(raw_model_output.iloc[0].to_dict())

    if isinstance(raw_model_output, pd.Series):
        if raw_model_output.empty:
            raise ValueError("MLflow output was empty")
        return dict(raw_model_output.to_dict())

    if isinstance(raw_model_output, Mapping):
        return dict(raw_model_output)

    if isinstance(raw_model_output, np.ndarray):
        return _sequence_to_mapping(raw_model_output.flatten().tolist())

    if isinstance(raw_model_output, Sequence) and not isinstance(raw_model_output, (str, bytes)):
        return _sequence_to_mapping(list(raw_model_output))

    if isinstance(raw_model_output, (int, float, np.integer, np.floating)):
        return {"prediction": float(raw_model_output)}

    raise ValueError(f"Unsupported MLflow output type: {type(raw_model_output).__name__}")


def _sequence_to_mapping(values: list[Any]) -> dict[str, Any]:
    if not values:
        raise ValueError("MLflow output was empty")
    if len(values) == 1:
        value = values[0]
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, (int, float, np.integer, np.floating)):
            return {"prediction": float(value)}
    if len(values) >= 2 and all(
        isinstance(item, (int, float, np.integer, np.floating)) for item in values[:2]
    ):
        return {"probabilities": [float(values[0]), float(values[1])]}
    first_item = values[0]
    if isinstance(first_item, Mapping):
        return dict(first_item)
    raise ValueError("MLflow output sequence had an unsupported shape")


def _extract_probability(normalized: dict[str, Any]) -> float:
    if "conversion_probability" in normalized:
        return _clamp_probability(normalized["conversion_probability"])
    if "probability" in normalized:
        return _clamp_probability(normalized["probability"])
    if "score" in normalized and isinstance(normalized["score"], (int, float)):
        score = float(normalized["score"])
        if 0.0 <= score <= 1.0:
            return score
    if "lead_score" in normalized:
        return _score_to_probability(normalized["lead_score"])
    probabilities = normalized.get("probabilities")
    if isinstance(probabilities, Sequence) and len(probabilities) >= 2:
        return _clamp_probability(probabilities[1])
    prediction = normalized.get("prediction")
    if isinstance(prediction, (int, float)):
        prediction_value = float(prediction)
        if 0.0 <= prediction_value <= 1.0:
            return prediction_value
        return _score_to_probability(prediction_value)
    raise ValueError("MLflow output did not contain a usable lead probability")


def _extract_lead_score(normalized: dict[str, Any], probability: float) -> int:
    raw_score = normalized.get("lead_score")
    if isinstance(raw_score, (int, float, np.integer, np.floating)):
        return _clamp_score(raw_score)
    prediction = normalized.get("prediction")
    if isinstance(prediction, (int, float, np.integer, np.floating)) and float(prediction) > 1.0:
        return _clamp_score(prediction)
    return int(round(probability * 100))


def _extract_confidence(normalized: dict[str, Any], probability: float) -> float:
    raw_confidence = normalized.get("confidence")
    if isinstance(raw_confidence, (int, float, np.integer, np.floating)):
        return _clamp_probability(raw_confidence)
    return round(max(probability, 1.0 - probability), 6)


def _recommendation_for_score(lead_score: int) -> str:
    if lead_score >= 70:
        return "Hot"
    if lead_score >= 40:
        return "Warm"
    return "Cold"


def _clamp_probability(value: Any) -> float:
    probability = float(value)
    return max(0.0, min(1.0, probability))


def _clamp_score(value: Any) -> int:
    return max(0, min(100, int(round(float(value)))))


def _score_to_probability(value: Any) -> float:
    return _clamp_score(value) / 100.0


def _is_connectivity_error(exc: BaseException) -> bool:
    if isinstance(exc, (OSError, ConnectionError)):
        return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
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
