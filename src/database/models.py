"""Database models for Hokusai ML Platform."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional, List


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


@dataclass
class APIKeyModel:
    """Represents an API key in the database."""
    
    key_id: str
    key_hash: str
    key_prefix: str
    user_id: str
    name: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    is_active: bool = True
    rate_limit_per_hour: int = 1000
    allowed_ips: Optional[List[str]] = None
    environment: str = "production"
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database operations."""
        return {
            "key_id": self.key_id,
            "key_hash": self.key_hash,
            "key_prefix": self.key_prefix,
            "user_id": self.user_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "is_active": self.is_active,
            "rate_limit_per_hour": self.rate_limit_per_hour,
            "allowed_ips": self.allowed_ips,
            "environment": self.environment,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "APIKeyModel":
        """Create instance from dictionary."""
        return cls(
            key_id=data["key_id"],
            key_hash=data["key_hash"],
            key_prefix=data["key_prefix"],
            user_id=data["user_id"],
            name=data["name"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"])
            if data.get("expires_at")
            else None,
            last_used_at=datetime.fromisoformat(data["last_used_at"])
            if data.get("last_used_at")
            else None,
            is_active=data.get("is_active", True),
            rate_limit_per_hour=data.get("rate_limit_per_hour", 1000),
            allowed_ips=data.get("allowed_ips"),
            environment=data.get("environment", "production"),
        )
    
    def is_expired(self) -> bool:
        """Check if API key has expired."""
        if not self.expires_at:
            return False
        from datetime import timezone
        return datetime.now(timezone.utc) > self.expires_at
    
    def get_display_info(self) -> dict[str, Any]:
        """Get display-safe information about the key."""
        return {
            "key_id": self.key_id,
            "key_prefix": f"{self.key_prefix}***",
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used_at.isoformat() if self.last_used_at else "Never",
            "status": "active" if self.is_active and not self.is_expired() else "inactive",
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
