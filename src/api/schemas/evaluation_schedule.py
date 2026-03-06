"""Pydantic schemas for EvaluationSchedule CRUD operations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvaluationScheduleCreate(BaseModel):
    """Request body for creating an evaluation schedule."""

    cron_expression: str = Field(..., min_length=1)
    enabled: bool = True

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        if not croniter.is_valid(v):
            raise ValueError(f"Invalid cron expression: {v}")
        return v


class EvaluationScheduleUpdate(BaseModel):
    """Partial update schema for PUT operations. All fields optional."""

    cron_expression: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    next_run_at: datetime | None = None

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str | None) -> str | None:
        if v is not None and not croniter.is_valid(v):
            raise ValueError(f"Invalid cron expression: {v}")
        return v


class EvaluationScheduleResponse(BaseModel):
    """Full EvaluationSchedule entity representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_id: str
    cron_expression: str
    enabled: bool
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
