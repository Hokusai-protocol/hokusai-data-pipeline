"""Schemas for inference logging and deferred outcome submission."""

from __future__ import annotations

import json
import math
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, validator

MAX_JSON_PAYLOAD_BYTES = 1024 * 1024  # 1MB


def _json_payload_size(value: dict[str, Any] | None) -> int:
    if value is None:
        return 0
    return len(json.dumps(value, default=str))


class InferenceLogCreate(BaseModel):
    """Validated input for creating a persisted inference log."""

    api_token_id: str = Field(..., min_length=1, max_length=255)
    model_name: str = Field(..., min_length=1, max_length=255)
    model_version: str = Field(..., min_length=1, max_length=255)
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None = None
    trace_metadata: dict[str, Any] | None = None

    @validator("input_payload", "output_payload", "trace_metadata")
    def validate_payload_size(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if _json_payload_size(value) > MAX_JSON_PAYLOAD_BYTES:
            raise ValueError(f"Payload exceeds {MAX_JSON_PAYLOAD_BYTES} bytes")
        return value


class OutcomeSubmission(BaseModel):
    """Request payload for recording a deferred outcome.

    ``selected_models`` (executed models by role) and ``overrides`` are the
    HOK-3364 routing-outcome block. Without them the outcome joins to its
    inference but cannot grade the recommendation: Hokusai cannot tell whether
    the recommended models ran.
    """

    inference_log_id: UUID
    outcome_score: float = Field(..., ge=-1_000_000.0, le=1_000_000.0)
    outcome_type: str = Field(..., min_length=1, max_length=128)
    selected_models: dict[str, str] | None = None
    overrides: list[dict[str, Any]] | None = None

    @validator("overrides", always=True)
    def validate_routing_outcome(
        cls, value: list[dict[str, Any]] | None, values: dict[str, Any]
    ) -> list[dict[str, Any]] | None:
        from src.api.services.routing_join import routing_outcome_errors

        if value is None:
            return value
        errors = routing_outcome_errors(
            {
                "inference_log_id": str(values.get("inference_log_id") or "routed"),
                "selected_models": values.get("selected_models") or {},
                "overrides": value,
            }
        )
        if errors:
            raise ValueError(f"Invalid routing outcome: {'; '.join(errors)}")
        return value

    @validator("outcome_score")
    def validate_outcome_score(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Outcome score must be a finite number")
        return value


class InferenceLogResponse(BaseModel):
    """Response payload exposing a correlation id for later outcomes."""

    inference_log_id: UUID


class OutcomeSubmissionResponse(BaseModel):
    """Response payload for successful deferred outcome ingestion."""

    inference_log_id: UUID
    status: str = "recorded"
