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
    """Request payload for recording a deferred outcome."""

    inference_log_id: UUID
    outcome_score: float = Field(..., ge=-1_000_000.0, le=1_000_000.0)
    outcome_type: str = Field(..., min_length=1, max_length=128)

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
