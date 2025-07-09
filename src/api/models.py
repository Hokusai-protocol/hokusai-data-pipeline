"""Pydantic models for API requests and responses."""

import re
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, validator


class ModelRegistration(BaseModel):
    """Request model for registering a new model."""

    model_name: str = Field(..., description="Name of the model")
    model_type: str = Field(..., description="Type of model (lead_scoring, classification, etc.)")
    model_data: dict[str, Any] = Field(..., description="Model data or reference")
    metadata: dict[str, Any] = Field(default={}, description="Additional metadata")

    @validator("model_type")
    def validate_model_type(cls, v):
        valid_types = ["lead_scoring", "classification", "regression", "ranking"]
        if v not in valid_types:
            raise ValueError(f"Model type must be one of: {valid_types}")
        return v


class ModelRegistrationResponse(BaseModel):
    """Response model for model registration."""

    model_id: str
    model_name: str
    version: str
    status: str = "registered"
    registration_timestamp: datetime


class ModelLineageResponse(BaseModel):
    """Response model for model lineage."""

    model_id: str
    lineage: list[dict[str, Any]]
    total_versions: int
    latest_version: str


class ContributorImpactRequest(BaseModel):
    """Request model for contributor impact query."""

    address: str = Field(..., description="Ethereum address of contributor")

    @validator("address")
    def validate_eth_address(cls, v):
        pattern = r"^0x[a-fA-F0-9]{40}$"
        if not re.match(pattern, v):
            raise ValueError("Invalid Ethereum address format")
        return v


class ContributorImpactResponse(BaseModel):
    """Response model for contributor impact."""

    address: str
    total_models_improved: int
    total_improvement_score: float
    contributions: list[dict[str, Any]]
    first_contribution: Optional[datetime]
    last_contribution: Optional[datetime]


class ExperimentRequest(BaseModel):
    """Request model for creating an experiment."""

    baseline_model_id: str
    contributed_data_reference: str
    experiment_config: dict[str, Any] = Field(default={})


class ExperimentResponse(BaseModel):
    """Response model for experiment creation."""

    experiment_id: str
    status: str
    created_at: datetime


class ModelComparisonRequest(BaseModel):
    """Request model for model comparison."""

    baseline_id: str
    candidate_id: str
    test_dataset_reference: str
    metrics_to_compare: list[str] = Field(
        default=["accuracy", "auroc", "f1_score"], description="Metrics to compare between models"
    )


class ModelComparisonResponse(BaseModel):
    """Response model for model comparison."""

    baseline_metrics: dict[str, float]
    candidate_metrics: dict[str, float]
    improvements: dict[str, float]
    recommendation: str
    comparison_timestamp: datetime


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthCheckResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    services: dict[str, str]
    timestamp: datetime
    system_info: Optional[dict[str, float]] = None
