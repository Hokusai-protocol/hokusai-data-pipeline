"""Nested public request schema for Technical Task Router model serving."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TechnicalTaskRoutingObjective(str, Enum):
    """User-facing strategy objective for model 30 routing."""

    LOWEST_COST = "lowest_cost"
    FASTEST_COMPLETION = "fastest_completion"
    HIGHEST_RELIABILITY = "highest_reliability"


class TechnicalTaskWorkflowStage(str, Enum):
    """Workflow stages model 30 can recommend model assignments for."""

    PLAN = "plan"
    CODE = "code"
    REVIEW = "review"


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
    available_planner_models: list[str] | None = Field(default=None, min_length=1)
    available_coder_models: list[str] | None = Field(default=None, min_length=1)
    available_reviewer_models: list[str] | None = Field(default=None, min_length=1)
    preferred_models: list[str] | None = Field(default=None, min_length=1)
    max_cost_usd: float | None = Field(default=None, gt=0)
    max_latency_seconds: float | None = Field(default=None, gt=0)
    objective: TechnicalTaskRoutingObjective = TechnicalTaskRoutingObjective.HIGHEST_RELIABILITY
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
    stages: list[TechnicalTaskWorkflowStage] | None = Field(default=None, min_length=1)
    execution_environment: str | None = None
    human_review_required: bool | None = None

    @field_validator("stages")
    @classmethod
    def _stages_must_be_unique(
        cls: type[TechnicalTaskWorkflowGroup], stages: list[TechnicalTaskWorkflowStage] | None
    ) -> list[TechnicalTaskWorkflowStage] | None:
        if stages is not None and len(stages) != len(set(stages)):
            raise ValueError("workflow.stages must not contain duplicates")
        return stages


class TechnicalTaskMetadataGroup(BaseModel):
    """Optional integration metadata."""

    model_config = ConfigDict(extra="forbid")

    external_task_id: str | None = None
    run_id: str | None = None
    integration_version: str | None = None
    idempotency_key: str | None = None


class TechnicalTaskRouterInputs(BaseModel):
    """Validated model-30 payload matching technical_task_router_inputs/v2."""

    model_config = ConfigDict(extra="forbid")

    task: TechnicalTaskGroup
    routing: TechnicalTaskRoutingGroup | None = None
    context: TechnicalTaskContextGroup | None = None
    workflow: TechnicalTaskWorkflowGroup | None = None
    metadata: TechnicalTaskMetadataGroup | None = None


class TechnicalTaskStrategyRecommendation(BaseModel):
    """One model-30 workflow strategy recommendation."""

    model_config = ConfigDict(extra="forbid")

    objective: TechnicalTaskRoutingObjective
    planner_model: str | None = None
    coder_model: str | None = None
    reviewer_model: str | None = None
    stages: list[TechnicalTaskWorkflowStage] = Field(default_factory=list)
    estimated_success_under_budget: float = Field(ge=0, le=1)
    estimated_cost_usd: float = Field(ge=0)
    estimated_duration_seconds: float | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1)
    rationale: str | None = None


class TechnicalTaskTradeoffSummary(BaseModel):
    """Comparable strategy summaries for the three primary user objectives."""

    model_config = ConfigDict(extra="forbid")

    lowest_cost: TechnicalTaskStrategyRecommendation | None = None
    fastest_completion: TechnicalTaskStrategyRecommendation | None = None
    highest_reliability: TechnicalTaskStrategyRecommendation | None = None


class TechnicalTaskNearestNeighborsSummary(BaseModel):
    """Nearest-neighbor support metadata for model 30 estimates."""

    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0)
    success_under_budget_rate: float | None = Field(default=None, ge=0, le=1)
    mean_cost_usd: float | None = Field(default=None, ge=0)
    mean_duration_seconds: float | None = Field(default=None, ge=0)


class TechnicalTaskRouterPredictions(BaseModel):
    """Public model-30 v2 prediction response contract."""

    model_config = ConfigDict(extra="forbid")

    recommended_strategy: TechnicalTaskStrategyRecommendation
    alternatives: list[TechnicalTaskStrategyRecommendation] = Field(default_factory=list)
    tradeoffs: TechnicalTaskTradeoffSummary
    nearest_neighbors: TechnicalTaskNearestNeighborsSummary
