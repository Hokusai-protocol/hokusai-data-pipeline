"""Helpers for emitting tokenized model registration events."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from ..exceptions import NotificationError

DEFAULT_API_ENDPOINT = "https://api.hokus.ai"
REGISTRATION_EVENT_PATH = "/api/models/tokenized-registration-events"
MAX_ERROR_BODY_LENGTH = 1000
OPTIONAL_REGISTRATION_FIELDS = (
    "eval_spec",
    "scorer_ref",
    "primary_metric",
    "benchmark_spec_id",
)


def resolve_registration_event_api_endpoint(api_endpoint: str | None = None) -> str:
    """Resolve the base API endpoint used for registration events."""
    resolved = (
        api_endpoint
        or os.environ.get("HOKUSAI_API_ENDPOINT")
        or os.environ.get("HOKUSAI_API_URL")
        or DEFAULT_API_ENDPOINT
    )
    return resolved.rstrip("/")


def build_pipeline_registration_event_url(api_endpoint: str) -> str:
    """Build the tokenized registration event URL."""
    if api_endpoint.endswith("/api"):
        return f"{api_endpoint}/models/tokenized-registration-events"
    return f"{api_endpoint}{REGISTRATION_EVENT_PATH}"


def build_registration_event_payload(
    result: dict[str, Any],
    *,
    model_uri: str | None = None,
    api_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the payload expected by the data pipeline registration endpoint."""
    payload: dict[str, Any] = {
        "model_name": result["model_name"],
        "version": str(result["version"]),
        "token_id": result["token_id"],
        "proposal_identifier": result["proposal_identifier"],
        "metric_name": result["metric_name"],
        "baseline_value": result["baseline_value"],
        "mlflow_run_id": result["mlflow_run_id"],
        "model_uri": model_uri or f"models:/{result['model_name']}/{result['version']}",
        "tags": result.get("tags") or {},
    }
    if api_schema is not None:
        payload["api_schema"] = api_schema
    for field_name in OPTIONAL_REGISTRATION_FIELDS:
        value = result.get(field_name)
        if value is not None:
            payload[field_name] = value
    return payload


def notify_pipeline_of_registration(
    payload: dict[str, Any],
    *,
    api_key: str,
    api_endpoint: str | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """POST tokenized registration metadata to the data pipeline API."""
    if not api_key:
        raise NotificationError(
            "Model registration succeeded in MLflow, but notifying the Hokusai site failed: "
            "HOKUSAI_API_KEY is required to emit the registration event.",
            mlflow_registered=True,
        )

    resolved_endpoint = resolve_registration_event_api_endpoint(api_endpoint=api_endpoint)
    url = build_pipeline_registration_event_url(resolved_endpoint)

    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")  # noqa: S310
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
            raw_body = response.read()
            if not raw_body:
                return {}
            try:
                return json.loads(raw_body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return {"raw_response": raw_body.decode("utf-8", errors="replace")}
    except urllib.error.HTTPError as exc:
        response_body = _read_error_body(exc)
        detail = f" Response body: {response_body}" if response_body else ""
        raise NotificationError(
            "Model registration succeeded in MLflow, but notifying the Hokusai site failed "
            f"with HTTP {exc.code}.{detail}",
            status_code=exc.code,
            response_body=response_body,
            mlflow_registered=True,
        ) from exc
    except urllib.error.URLError as exc:
        raise NotificationError(
            "Model registration succeeded in MLflow, but notifying the Hokusai site failed: "
            f"could not connect to {url} ({exc.reason}).",
            mlflow_registered=True,
        ) from exc
    except OSError as exc:
        raise NotificationError(
            "Model registration succeeded in MLflow, but notifying the Hokusai site failed: "
            f"{exc}.",
            mlflow_registered=True,
        ) from exc


def _read_error_body(exc: urllib.error.HTTPError) -> str | None:
    """Read and truncate an HTTP error body."""
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        return None
    if not body:
        return None
    return body[:MAX_ERROR_BODY_LENGTH]
