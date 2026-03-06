"""Pydantic schemas for BenchmarkSpec CRUD operations."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BenchmarkProvider(str, Enum):
    """Supported benchmark data providers."""

    hokusai = "hokusai"
    kaggle = "kaggle"


class MetricDirection(str, Enum):
    """Whether a higher or lower metric value is better."""

    higher_is_better = "higher_is_better"
    lower_is_better = "lower_is_better"


class BenchmarkSpecCreate(BaseModel):
    """Request body for creating a new benchmark spec."""

    model_id: str = Field(..., min_length=1)
    provider: BenchmarkProvider
    dataset_reference: str = Field(
        ..., min_length=1, description="S3 URI or Kaggle dataset reference"
    )
    eval_split: str = Field(..., min_length=1)
    target_column: str = Field(..., min_length=1)
    input_columns: list[str]
    metric_name: str = Field(..., min_length=1)
    metric_direction: MetricDirection
    dataset_version: str | None = None
    metadata: dict[str, Any] | None = None


class BenchmarkSpecUpdate(BaseModel):
    """Partial update schema for PATCH operations. All fields optional."""

    model_id: str | None = Field(default=None, min_length=1)
    provider: BenchmarkProvider | None = None
    dataset_reference: str | None = Field(default=None, min_length=1)
    eval_split: str | None = Field(default=None, min_length=1)
    target_column: str | None = Field(default=None, min_length=1)
    input_columns: list[str] | None = None
    metric_name: str | None = Field(default=None, min_length=1)
    metric_direction: MetricDirection | None = None
    dataset_version: str | None = None
    metadata: dict[str, Any] | None = None


class BenchmarkSpecResponse(BaseModel):
    """Full BenchmarkSpec entity representation."""

    model_config = ConfigDict(use_enum_values=True, from_attributes=True)

    spec_id: UUID
    model_id: str
    provider: BenchmarkProvider
    dataset_reference: str
    eval_split: str
    target_column: str
    input_columns: list[str]
    metric_name: str
    metric_direction: MetricDirection
    dataset_version: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime | None = None
    is_active: bool


class BenchmarkSpecListResponse(BaseModel):
    """Paginated list of BenchmarkSpec entities."""

    items: list[BenchmarkSpecResponse]
    total: int
    page: int
    page_size: int


class DatasetUploadResponse(BaseModel):
    """Response returned after a successful dataset upload to S3."""

    s3_uri: str
    sha256_hash: str
    spec_id: str
    filename: str
    file_size_bytes: int
