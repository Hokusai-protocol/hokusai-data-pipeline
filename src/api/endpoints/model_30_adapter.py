"""Adapter layer between the public model 30 contract and the MLflow artifact.

MLflow authentication is supplied by shared environment configuration such as
`MLFLOW_TRACKING_TOKEN` plus the mTLS setup applied during API startup.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping
from typing import Any

import mlflow.pyfunc
import numpy as np
import pandas as pd

from src.api.schemas import TechnicalTaskRouterInputs

DEFAULT_MODEL_30_MLFLOW_URI = "models:/Technical Task Router/1"
MODEL_30_VERSION = "1"
MODEL_30_SCHEMA = "technical_task_router_inputs/v1"

_MODEL_30_CACHE: dict[str, Any] = {}
_MODEL_30_CACHE_LOCK = threading.Lock()


def get_model_30_uri() -> str:
    """Resolve the model 30 URI from environment with a stable default."""
    return os.getenv("MODEL_30_MLFLOW_URI", DEFAULT_MODEL_30_MLFLOW_URI)


def reset_model_30_cache() -> None:
    """Clear the model cache for tests."""
    with _MODEL_30_CACHE_LOCK:
        _MODEL_30_CACHE.clear()


def is_model_30_cached(model_uri: str) -> bool:
    """Return whether a model URI is already loaded into process cache."""
    return model_uri in _MODEL_30_CACHE


def validate_nested_model_30_inputs(raw_inputs: dict[str, Any]) -> TechnicalTaskRouterInputs:
    """Validate the public nested input contract for model 30."""
    return TechnicalTaskRouterInputs.model_validate(raw_inputs)


def model_30_inputs_to_features(validated_inputs: TechnicalTaskRouterInputs) -> pd.DataFrame:
    """Map nested public inputs into a flat one-row feature frame for MLflow pyfunc."""
    task = validated_inputs.task
    routing = validated_inputs.routing
    context = validated_inputs.context
    workflow = validated_inputs.workflow
    prediction = validated_inputs.prediction
    metadata = validated_inputs.metadata

    task_descriptor = task.model_dump(mode="json", exclude_none=True)
    if context is not None:
        task_descriptor["context"] = context.model_dump(mode="json", exclude_none=True)
    if workflow is not None:
        task_descriptor["workflow"] = workflow.model_dump(mode="json", exclude_none=True)
    if metadata is not None:
        task_descriptor["metadata"] = metadata.model_dump(mode="json", exclude_none=True)

    row = {
        "schema_version": MODEL_30_SCHEMA,
        "task_descriptor": _json_dump(task_descriptor),
        "task_description": task.description,
        "task_type": task.task_type,
        "language": task.language,
        "framework": task.framework,
        "repo_type": task.repo_type,
        "allowed_models": _json_dump(routing.available_models if routing else []),
        "preferred_models": _json_dump(routing.preferred_models if routing else []),
        "max_cost_usd": routing.max_cost_usd if routing else None,
        "max_latency_seconds": routing.max_latency_seconds if routing else None,
        "prioritize_quality": routing.prioritize_quality if routing else None,
        "prioritize_speed": routing.prioritize_speed if routing else None,
        "domain": context.domain if context else None,
        "repo_size_bucket": context.repo_size_bucket if context else None,
        "requires_tests": context.requires_tests if context else None,
        "risk_level": context.risk_level if context else None,
        "file_count": context.file_count if context else None,
        "estimated_complexity": context.estimated_complexity if context else None,
        "security_sensitive": context.security_sensitive if context else None,
        "surface": workflow.surface if workflow else None,
        "workflow_stages": _json_dump(workflow.stages if workflow else []),
        "execution_environment": workflow.execution_environment if workflow else None,
        "human_review_required": workflow.human_review_required if workflow else None,
        "expected_duration_seconds": prediction.expected_duration_seconds if prediction else None,
        "expected_cost_usd": prediction.expected_cost_usd if prediction else None,
        "expected_success_probability": (
            prediction.expected_success_probability if prediction else None
        ),
        "external_task_id": metadata.external_task_id if metadata else None,
        "run_id": metadata.run_id if metadata else None,
        "integration_version": metadata.integration_version if metadata else None,
        "idempotency_key": metadata.idempotency_key if metadata else None,
        "request_metadata": _json_dump(
            metadata.model_dump(mode="json", exclude_none=True) if metadata else {}
        ),
    }
    return pd.DataFrame([row])


def call_mlflow_model_30(model_uri: str, features: object) -> Any:
    """Load the cached MLflow model and invoke predict()."""
    model = _get_or_load_model_30(model_uri)
    return model.predict(features)


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
        cached_model = _MODEL_30_CACHE.get(model_uri)
        if cached_model is None:
            cached_model = mlflow.pyfunc.load_model(model_uri)
            _MODEL_30_CACHE[model_uri] = cached_model
        return cached_model


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


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


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
