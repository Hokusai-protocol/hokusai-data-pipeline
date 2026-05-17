"""Schemas for tokenized model registration event ingestion."""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TokenizedRegistrationEventRequest(BaseModel):
    """Request body for forwarding tokenized registration completion events."""

    model_config = ConfigDict(extra="ignore")

    model_name: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    token_id: str = Field(..., min_length=1)
    proposal_identifier: str = Field(..., min_length=1)
    metric_name: str = Field(..., min_length=1)
    baseline_value: float
    mlflow_run_id: str = Field(..., min_length=1)
    current_value: float | None = None
    model_uri: str | None = None
    api_schema: dict[str, Any] | None = None
    tags: dict[str, str] | None = None

    @field_validator(
        "model_name",
        "version",
        "token_id",
        "proposal_identifier",
        "metric_name",
        "mlflow_run_id",
        mode="before",
    )
    @classmethod
    def _validate_non_empty_string(cls: type, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value.strip()

    @field_validator("model_uri")
    @classmethod
    def _validate_model_uri(cls: type, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("model_uri must be a non-empty string when provided")
        return value.strip()

    @field_validator("baseline_value", "current_value")
    @classmethod
    def _validate_finite_numbers(cls: type, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("must be a finite number")
        return value


class TokenizedRegistrationEventResponse(BaseModel):
    """Success response for tokenized registration event ingestion."""

    status: Literal["ok"]
    model_id: str
    model_name: str
    version: str
    event_emitted: bool
    detail: str | None = None
