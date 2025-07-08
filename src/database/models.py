"""Database models for Hokusai ML Platform."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class ModelStatus(Enum):
    """Status of a model in the registration process."""

    DRAFT = "draft"
    REGISTERING = "registering"
    REGISTERED = "registered"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ARCHIVED = "archived"


@dataclass
class TokenModel:
    """Represents a token and its associated model in the database."""

    token_id: str
    model_status: ModelStatus
    mlflow_run_id: Optional[str] = None
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    baseline_value: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database operations."""
        return {
            "token_id": self.token_id,
            "model_status": self.model_status.value,
            "mlflow_run_id": self.mlflow_run_id,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "baseline_value": self.baseline_value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenModel":
        """Create instance from dictionary."""
        return cls(
            token_id=data["token_id"],
            model_status=ModelStatus(data["model_status"]),
            mlflow_run_id=data.get("mlflow_run_id"),
            metric_name=data.get("metric_name"),
            metric_value=data.get("metric_value"),
            baseline_value=data.get("baseline_value"),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else None,
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else None,
            metadata=data.get("metadata"),
        )

    def is_draft(self) -> bool:
        """Check if token is in draft status."""
        return self.model_status == ModelStatus.DRAFT

    def can_register(self) -> bool:
        """Check if token can be registered."""
        return self.model_status in [ModelStatus.DRAFT, ModelStatus.FAILED]
