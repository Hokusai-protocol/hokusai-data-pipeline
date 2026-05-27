"""Shared MLflow SDK health probes.

MLflow authentication is supplied by the standard SDK environment, including
`MLFLOW_TRACKING_TOKEN` where bearer auth is required.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

from mlflow.tracking import MlflowClient

from src.utils.mlflow_url import get_mlflow_url

_REDACTED_PATH = "<redacted-path>"
_CERT_PATH_ENV_VARS = (
    "MLFLOW_CA_BUNDLE_PATH",
    "MLFLOW_CLIENT_CERT_PATH",
    "MLFLOW_CLIENT_KEY_PATH",
    "MLFLOW_TRACKING_SERVER_CERT_PATH",
    "MLFLOW_TRACKING_CLIENT_CERT_PATH",
    "MLFLOW_TRACKING_CLIENT_KEY_PATH",
)


@dataclass(slots=True)
class MLflowRegistryHealthResult:
    """Structured result for MLflow registry SDK connectivity checks."""

    status: Literal["ok", "error"]
    tracking_uri: str
    latency_ms: float
    sample_model: str | None = None
    error_type: str | None = None
    error: str | None = None

    def to_dict(self: MLflowRegistryHealthResult) -> dict[str, Any]:
        """Return a JSON-safe representation without null error fields on success."""
        payload = asdict(self)
        if self.status == "ok":
            payload.pop("error_type", None)
            payload.pop("error", None)
        return payload


def _sanitize_error_message(message: str) -> str:
    sanitized = message
    for env_var in _CERT_PATH_ENV_VARS:
        path = os.getenv(env_var, "").strip()
        if path:
            sanitized = sanitized.replace(path, _REDACTED_PATH)
    return sanitized


def _extract_sample_model(search_results: Any) -> str | None:
    first_model = next(iter(search_results), None)
    if first_model is None:
        return None
    model_name = getattr(first_model, "name", None)
    if model_name is not None:
        return model_name
    if isinstance(first_model, dict):
        raw_name = first_model.get("name")
        return raw_name if isinstance(raw_name, str) else None
    return None


def _search_registered_models_sync() -> tuple[str, str | None]:
    tracking_uri = get_mlflow_url()
    client = MlflowClient(tracking_uri=tracking_uri)
    search_results = client.search_registered_models(max_results=1)
    return tracking_uri, _extract_sample_model(search_results)


async def check_mlflow_registry_sdk(timeout_seconds: float = 5.0) -> MLflowRegistryHealthResult:
    """Probe MLflow registry reachability through the MLflow SDK transport."""
    started_at = time.perf_counter()
    tracking_uri = "<unconfigured>"
    try:
        tracking_uri = get_mlflow_url()
        resolved_tracking_uri, sample_model = await asyncio.wait_for(
            asyncio.to_thread(_search_registered_models_sync),
            timeout=timeout_seconds,
        )
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        return MLflowRegistryHealthResult(
            status="ok",
            tracking_uri=resolved_tracking_uri,
            latency_ms=latency_ms,
            sample_model=sample_model,
        )
    except asyncio.TimeoutError as exc:
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        return MLflowRegistryHealthResult(
            status="error",
            tracking_uri=tracking_uri,
            latency_ms=latency_ms,
            error_type=type(exc).__name__,
            error=f"MLflow registry SDK probe timed out after {timeout_seconds:.1f}s",
        )
    except Exception as exc:  # noqa: BLE001 - health checks should report failures
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        return MLflowRegistryHealthResult(
            status="error",
            tracking_uri=tracking_uri,
            latency_ms=latency_ms,
            error_type=type(exc).__name__,
            error=_sanitize_error_message(str(exc)),
        )
