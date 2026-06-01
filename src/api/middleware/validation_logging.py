"""Structured logging for request validation failures."""

from __future__ import annotations

import ipaddress
import logging
from copy import deepcopy
from uuid import uuid4

from fastapi import Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from starlette.responses import Response

logger = logging.getLogger(__name__)


def classify_client_ip(ip: str | None) -> str:
    """Return a public-safe classification for a client IP."""
    if not ip:
        return "unknown"

    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return "unknown"

    if parsed.is_loopback:
        return "loopback"
    if parsed.version == 6:
        return "ipv6"
    if parsed.is_private:
        return "ipv4_private"
    return "ipv4_public"


def redact_pydantic_errors(errors: list[dict]) -> list[dict]:
    """Strip value-bearing fields from Pydantic error payloads."""
    redacted: list[dict] = []
    for error in errors:
        clean_error = deepcopy(error)
        clean_error.pop("input", None)
        clean_error.pop("ctx", None)
        redacted.append(
            {
                "loc": clean_error.get("loc"),
                "type": clean_error.get("type"),
                "msg": clean_error.get("msg"),
            }
        )
    return redacted


def build_caller_fingerprint(request: Request) -> dict[str, str | None]:
    """Build safe caller context from request state and headers."""
    user_agent = (request.headers.get("user-agent") or "")[:200] or None
    state = request.state
    return {
        "user_id": getattr(state, "user_id", None),
        "api_key_id": getattr(state, "api_key_id", None),
        "user_agent": user_agent,
        "client_ip_class": classify_client_ip(request.client.host if request.client else None),
    }


def get_or_generate_request_id(request: Request) -> str:
    """Return an existing request id or assign a new one."""
    header_value = request.headers.get("X-Request-ID")
    if header_value:
        request_id = header_value[:128]
        request.state.request_id = request_id
        return request_id

    request_id = getattr(request.state, "request_id", None)
    if request_id:
        return request_id

    request_id = str(uuid4())
    request.state.request_id = request_id
    return request_id


def _summarize_validation_errors(errors: list[dict]) -> list[str]:
    summaries: list[str] = []
    for error in errors:
        location = ".".join(str(part) for part in error.get("loc") or ())
        error_type = error.get("type") or "unknown"
        summaries.append(f"{location}:{error_type}" if location else str(error_type))
    return summaries


def emit_model_serving_validation_422(
    logger_: logging.Logger,
    request_id: str,
    model_id: str,
    caller_context: dict | None,
    pydantic_errors: list[dict],
) -> None:
    """Emit a structured validation_422 record for model-serving schema errors."""
    validation_errors = redact_pydantic_errors(pydantic_errors)
    logger_.warning(
        "validation_422",
        extra={
            "event_type": "validation_422",
            "request_id": request_id,
            "endpoint": f"/api/v1/models/{model_id}/predict",
            "validation_errors": validation_errors,
            "validation_error_summary": _summarize_validation_errors(validation_errors),
            "caller_fingerprint": (caller_context or {}).get("caller_fingerprint"),
            "model_id": model_id,
        },
    )


_EXCEPTION_MESSAGE_MAX_LEN = 500


def emit_model_30_inference_failure(
    logger_: logging.Logger,
    *,
    request_id: str,
    model_id: str,
    model_uri: str,
    model_version: str,
    phase: str,
    path_type: str,
    exception_class: str,
    exception_message: str,
) -> None:
    """Emit a structured inference_failure record for Model 30 serving errors."""
    logger_.error(
        "model_30_inference_failure",
        extra={
            "event_type": "model_30_inference_failure",
            "request_id": request_id,
            "model_id": model_id,
            "model_uri": model_uri,
            "model_version": model_version,
            "phase": phase,
            "path_type": path_type,
            "exception_class": exception_class,
            "exception_message": exception_message[:_EXCEPTION_MESSAGE_MAX_LEN],
        },
    )


async def validation_422_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> Response:
    """Log FastAPI request validation errors without exposing payload values."""
    request_id = get_or_generate_request_id(request)
    validation_errors = redact_pydantic_errors(exc.errors())
    logger.warning(
        "validation_422",
        extra={
            "event_type": "validation_422",
            "request_id": request_id,
            "endpoint": request.url.path,
            "method": request.method,
            "path_params": dict(request.path_params),
            "validation_errors": validation_errors,
            "validation_error_summary": _summarize_validation_errors(validation_errors),
            "caller_fingerprint": build_caller_fingerprint(request),
        },
    )
    response = await request_validation_exception_handler(request, exc)
    response.headers["X-Request-ID"] = request_id
    return response
