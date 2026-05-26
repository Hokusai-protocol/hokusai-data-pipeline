"""Nested public request schema for Technical Task Router model serving."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TechnicalTaskGroup(BaseModel):
    """Required task description for model 30 routing."""

    model_config = ConfigDict(extra="forbid")

    description: str
    task_type: str
    language: str | None = None
    framework: str | None = None
    repo_type: str | None = None


class TechnicalTaskRoutingGroup(BaseModel):
    """Optional routing constraints and preferences."""

    model_config = ConfigDict(extra="forbid")

    available_models: list[str] | None = Field(default=None, min_length=1)
    preferred_models: list[str] | None = Field(default=None, min_length=1)
    max_cost_usd: float | None = Field(default=None, gt=0)
    max_latency_seconds: float | None = Field(default=None, gt=0)
    prioritize_quality: bool | None = None
    prioritize_speed: bool | None = None


class TechnicalTaskContextGroup(BaseModel):
    """Optional task context that can improve routing quality."""

    model_config = ConfigDict(extra="forbid")

    domain: str | None = None
    repo_size_bucket: str | None = None
    requires_tests: bool | None = None
    risk_level: str | None = None
    file_count: int | None = Field(default=None, ge=0)
    estimated_complexity: str | None = None
    security_sensitive: bool | None = None


class TechnicalTaskWorkflowGroup(BaseModel):
    """Optional workflow and execution-surface metadata."""

    model_config = ConfigDict(extra="forbid")

    surface: str | None = None
    stages: list[str] | None = Field(default=None, min_length=1)
    execution_environment: str | None = None
    human_review_required: bool | None = None


class TechnicalTaskPredictionGroup(BaseModel):
    """Optional caller-side expectations."""

    model_config = ConfigDict(extra="forbid")

    expected_duration_seconds: float | None = Field(default=None, ge=0)
    expected_cost_usd: float | None = Field(default=None, ge=0)
    expected_success_probability: float | None = Field(default=None, ge=0, le=1)


class TechnicalTaskOutcomeGroup(BaseModel):
    """Optional post-execution outcome metadata."""

    model_config = ConfigDict(extra="forbid")

    completed_successfully: bool | None = None
    actual_cost_usd: float | None = Field(default=None, ge=0)
    actual_time_seconds: float | None = Field(default=None, ge=0)
    retry_count: int | None = Field(default=None, ge=0)
    intervention_required: bool | None = None
    selected_model: str | None = None


class TechnicalTaskRubricGroup(BaseModel):
    """Optional evaluation metadata."""

    model_config = ConfigDict(extra="forbid")

    quality_score: float | None = None
    correctness_score: float | None = None
    human_rating: str | None = None
    benchmark_passed: bool | None = None


class TechnicalTaskMetadataGroup(BaseModel):
    """Optional integration metadata."""

    model_config = ConfigDict(extra="forbid")

    external_task_id: str | None = None
    run_id: str | None = None
    integration_version: str | None = None
    idempotency_key: str | None = None


class TechnicalTaskRouterInputs(BaseModel):
    """Validated model-30 payload matching technical_task_router_inputs/v1."""

    model_config = ConfigDict(extra="forbid")

    task: TechnicalTaskGroup
    routing: TechnicalTaskRoutingGroup | None = None
    context: TechnicalTaskContextGroup | None = None
    workflow: TechnicalTaskWorkflowGroup | None = None
    prediction: TechnicalTaskPredictionGroup | None = None
    outcome: TechnicalTaskOutcomeGroup | None = None
    rubric: TechnicalTaskRubricGroup | None = None
    metadata: TechnicalTaskMetadataGroup | None = None
