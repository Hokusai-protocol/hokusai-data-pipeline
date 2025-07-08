"""Pydantic models for API requests and responses."""

from pydantic import BaseModel, Field, validator
from typing import Dict, List, Any, Optional
from datetime import datetime
import re


class ModelRegistration(BaseModel):
    """Request model for registering a new model."""

    model_name: str = Field(..., description="Name of the model")
    model_type: str = Field(..., description="Type of model (lead_scoring, classification, etc.)")
    model_data: Dict[str, Any] = Field(..., description="Model data or reference")
    metadata: Dict[str, Any] = Field(default={}, description="Additional metadata")

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
    lineage: List[Dict[str, Any]]
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
    contributions: List[Dict[str, Any]]
    first_contribution: Optional[datetime]
    last_contribution: Optional[datetime]


class ExperimentRequest(BaseModel):
    """Request model for creating an experiment."""

    baseline_model_id: str
    contributed_data_reference: str
    experiment_config: Dict[str, Any] = Field(default={})


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
    metrics_to_compare: List[str] = Field(
        default=["accuracy", "auroc", "f1_score"],
        description="Metrics to compare between models"
    )


class ModelComparisonResponse(BaseModel):
    """Response model for model comparison."""

    baseline_metrics: Dict[str, float]
    candidate_metrics: Dict[str, float]
    improvements: Dict[str, float]
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
    services: Dict[str, str]
    timestamp: datetime
