"""Pydantic models for evaluation API endpoints."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvaluationJobStatus(str, Enum):
    """Supported evaluation job states."""

    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class EvaluationConfig(BaseModel):
    """Configuration payload for a new evaluation request."""

    eval_type: str = Field(..., min_length=1, description="Evaluation provider/type")
    dataset_reference: str = Field(..., min_length=1, description="Dataset identifier")
    parameters: dict[str, Any] = Field(default_factory=dict)


class EvaluationRequest(BaseModel):
    """Request body for creating a new evaluation."""

    config: EvaluationConfig


class EvaluationResponse(BaseModel):
    """Response returned when an evaluation job is created."""

    model_config = ConfigDict(use_enum_values=True)

    job_id: UUID
    status: EvaluationJobStatus
    estimated_cost: float = Field(..., ge=0)
    queue_position: int = Field(..., ge=1)
    created_at: datetime


class EvaluationStatusResponse(BaseModel):
    """Status payload for an evaluation job."""

    model_config = ConfigDict(use_enum_values=True)

    job_id: UUID
    status: EvaluationJobStatus
    progress_percentage: float = Field(..., ge=0, le=100)
    queue_position: int | None = Field(default=None, ge=1)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_details: str | None = None


class EvaluationManifestResponse(BaseModel):
    """Manifest payload for a completed evaluation."""

    job_id: UUID
    model_id: str
    eval_type: str
    results_summary: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    artifact_urls: list[str] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
