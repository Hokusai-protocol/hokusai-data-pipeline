"""Pydantic schemas for BenchmarkSpec CRUD operations."""

from __future__ import annotations

import math
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.utils.metric_naming import derive_mlflow_name

_SCORER_REF_SKIP_PREFIXES = ("genai:", "judge:")


def _validate_scorer_ref_value(v: object) -> str | None:
    """Shared scorer_ref validation: None allowed, empty string rejected, unknown ref rejected."""
    if v is None:
        return None
    if not isinstance(v, str) or v == "":
        raise ValueError("scorer_ref must be a non-empty string or null")
    if any(v.startswith(p) for p in _SCORER_REF_SKIP_PREFIXES):
        return v
    # Lazy import ensures built-in scorers are registered before resolution.
    from src.evaluation.scorers import UnknownScorerError, resolve_scorer  # noqa: PLC0415

    try:
        resolve_scorer(v)
    except UnknownScorerError as exc:
        raise ValueError(f"unknown scorer_ref: {v!r}") from exc
    return v


class BenchmarkProvider(str, Enum):
    """Supported benchmark data providers."""

    hokusai = "hokusai"
    kaggle = "kaggle"


class StatisticalFamily(str, Enum):
    """Statistical family for DeltaOne comparator dispatch."""

    proportion = "proportion"
    continuous = "continuous"
    zero_inflated_continuous = "zero_inflated_continuous"
    rank_or_ordinal = "rank_or_ordinal"


class MetricDirection(str, Enum):
    """Whether a higher or lower metric value is better."""

    higher_is_better = "higher_is_better"
    lower_is_better = "lower_is_better"


class MetricSpec(BaseModel):
    """Specification for a single evaluation metric.

    ``mlflow_name`` is the exact key written to MLflow for this metric;
    auto-derived from ``name`` when not supplied (colons replaced by
    underscores).
    """

    name: str
    direction: Literal["higher_is_better", "lower_is_better"]
    threshold: float | None = None
    unit: str | None = None
    mlflow_name: str | None = None
    scorer_ref: str | None = None

    @field_validator("scorer_ref", mode="before")
    @classmethod
    def _validate_scorer_ref(cls: type, v: object) -> str | None:
        return _validate_scorer_ref_value(v)

    @model_validator(mode="after")
    def _populate_and_validate_mlflow_name(self: MetricSpec) -> MetricSpec:
        self.mlflow_name = derive_mlflow_name(self.name, override=self.mlflow_name)
        return self


class GuardrailSpec(BaseModel):
    """A hard constraint that blocks promotion if breached.

    ``mlflow_name`` is the exact key written to MLflow for this guardrail;
    auto-derived from ``name`` when not supplied.
    """

    name: str
    direction: Literal["higher_is_better", "lower_is_better"]
    threshold: float
    blocking: bool = True
    mlflow_name: str | None = None
    scorer_ref: str | None = None

    @field_validator("scorer_ref", mode="before")
    @classmethod
    def _validate_scorer_ref(cls: type, v: object) -> str | None:
        return _validate_scorer_ref_value(v)

    @model_validator(mode="after")
    def _populate_and_validate_mlflow_name(self: GuardrailSpec) -> GuardrailSpec:
        self.mlflow_name = derive_mlflow_name(self.name, override=self.mlflow_name)
        return self


class EvalSpec(BaseModel):
    """Custom outcome evaluation contract attached to a benchmark spec."""

    measurement_policy: dict[str, Any] | None = None
    primary_metric: MetricSpec
    secondary_metrics: list[MetricSpec] = []
    guardrails: list[GuardrailSpec] = []
    unit_of_analysis: str | None = None
    min_examples: int | None = Field(default=None, ge=1)
    label_policy: dict[str, Any] | None = None
    coverage_policy: dict[str, Any] | None = None
    metric_family: StatisticalFamily = StatisticalFamily.proportion


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
    baseline_value: float | None = None
    eval_spec: EvalSpec | None = None

    @field_validator("baseline_value")
    @classmethod
    def _baseline_must_be_finite(cls: type, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError("baseline_value must be a finite number")
        return v


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
    baseline_value: float | None = None
    eval_spec: EvalSpec | None = None

    @field_validator("baseline_value")
    @classmethod
    def _baseline_must_be_finite(cls: type, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError("baseline_value must be a finite number")
        return v


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
    baseline_value: float | None = None
    eval_spec: EvalSpec | None = None
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
