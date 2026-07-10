"""Nested public request schema for Technical Task Router model serving."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _to_camel(field_name: str) -> str:
    parts = field_name.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


class TechnicalTaskRouterBaseModel(BaseModel):
    """Shared public contract settings for model 30 request/response schemas."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        alias_generator=_to_camel,
    )


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


class TechnicalTaskGroup(TechnicalTaskRouterBaseModel):
    """Required task description for model 30 routing."""

    description: str
    task_type: str
    language: str | None = None
    framework: str | None = None
    repo_type: str | None = None


class TechnicalTaskRoutingGroup(TechnicalTaskRouterBaseModel):
    """Optional routing constraints and preferences.

    Candidate-pool policy:
    * omit all pool fields to request unconstrained global ranking;
    * send two or more unique candidates in a role pool for ranking-eligible routing;
    * send exactly one unique candidate to force that role into non-ranking mode;
    * explicit empty lists are rejected.
    """

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


class TechnicalTaskContextGroup(TechnicalTaskRouterBaseModel):
    """Optional task context that can improve routing quality."""

    domain: str | None = None
    repo_size_bucket: str | None = None
    requires_tests: bool | None = None
    risk_level: str | None = None
    file_count: int | None = Field(default=None, ge=0)
    estimated_complexity: str | None = None
    security_sensitive: bool | None = None


class TechnicalTaskWorkflowGroup(TechnicalTaskRouterBaseModel):
    """Optional workflow and execution-surface metadata."""

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


class TechnicalTaskMetadataGroup(TechnicalTaskRouterBaseModel):
    """Optional integration metadata."""

    external_task_id: str | None = None
    run_id: str | None = None
    integration_version: str | None = None
    idempotency_key: str | None = None


class TechnicalTaskRouterInputs(TechnicalTaskRouterBaseModel):
    """Validated model-30 payload matching technical_task_router_inputs/v2."""

    task: TechnicalTaskGroup
    routing: TechnicalTaskRoutingGroup | None = None
    context: TechnicalTaskContextGroup | None = None
    workflow: TechnicalTaskWorkflowGroup | None = None
    metadata: TechnicalTaskMetadataGroup | None = None


class TechnicalTaskStrategyRecommendation(TechnicalTaskRouterBaseModel):
    """One model-30 workflow strategy recommendation."""

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


class TechnicalTaskTradeoffSummary(TechnicalTaskRouterBaseModel):
    """Comparable strategy summaries for the three primary user objectives."""

    lowest_cost: TechnicalTaskStrategyRecommendation | None = None
    fastest_completion: TechnicalTaskStrategyRecommendation | None = None
    highest_reliability: TechnicalTaskStrategyRecommendation | None = None


class TechnicalTaskNearestNeighborsSummary(TechnicalTaskRouterBaseModel):
    """Nearest-neighbor support metadata for model 30 estimates."""

    count: int = Field(ge=0)
    success_under_budget_rate: float | None = Field(default=None, ge=0, le=1)
    mean_cost_usd: float | None = Field(default=None, ge=0)
    mean_duration_seconds: float | None = Field(default=None, ge=0)


class TechnicalTaskRouterPredictions(TechnicalTaskRouterBaseModel):
    """Public model-30 v2 prediction response contract."""

    recommended_strategy: TechnicalTaskStrategyRecommendation
    alternatives: list[TechnicalTaskStrategyRecommendation] = Field(default_factory=list)
    tradeoffs: TechnicalTaskTradeoffSummary
    nearest_neighbors: TechnicalTaskNearestNeighborsSummary
