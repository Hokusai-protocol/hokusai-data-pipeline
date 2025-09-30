"""Database models for deployed models and model serving functionality."""

from datetime import datetime
from enum import Enum as PyEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    String,
    Text,
    create_engine,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class DeployedModelStatus(PyEnum):
    """Status of a deployed model."""

    PENDING = "pending"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    FAILED = "failed"
    STOPPED = "stopped"


class DeployedModel(Base):
    """Model representing a deployed ML model endpoint."""

    __tablename__ = "deployed_models"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # MLFlow model reference
    model_id = Column(String(255), nullable=False, index=True, comment="MLFlow model ID")

    # Provider information
    provider = Column(
        String(50), nullable=False, comment="Infrastructure provider (e.g., huggingface)"
    )
    provider_model_id = Column(
        String(255), nullable=True, comment="Provider-specific model identifier"
    )

    # Deployment details
    endpoint_url = Column(String(500), nullable=True, comment="URL of the deployed model endpoint")
    status = Column(
        SQLEnum(DeployedModelStatus),
        nullable=False,
        default=DeployedModelStatus.PENDING,
        index=True,
        comment="Current deployment status",
    )
    instance_type = Column(
        String(50),
        nullable=False,
        default="cpu",
        comment="Instance type for deployment (cpu, gpu, etc.)",
    )

    # Error handling
    error_message = Column(Text, nullable=True, comment="Error message if deployment failed")

    # Metadata (using deployment_metadata to avoid SQLAlchemy reserved word)
    deployment_metadata = Column(
        "metadata",  # Column name in database
        JSON,
        nullable=False,
        default=dict,
        comment="Additional metadata about the deployment",
    )

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return (
            f"<DeployedModel("
            f"id={self.id}, "
            f"model_id={self.model_id}, "
            f"provider={self.provider}, "
            f"status={self.status}"
            f")>"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for serialization."""
        return {
            "id": str(self.id),
            "model_id": self.model_id,
            "provider": self.provider,
            "provider_model_id": self.provider_model_id,
            "endpoint_url": self.endpoint_url,
            "status": self.status,
            "instance_type": self.instance_type,
            "error_message": self.error_message,
            "metadata": self.deployment_metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Indexes are already created via the index=True parameter in Column definitions
# Additional composite indexes can be added here if needed


def get_session(database_url: str):
    """Create a database session."""
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def create_tables(database_url: str):
    """Create all tables in the database."""
    engine = create_engine(database_url)
    Base.metadata.create_all(bind=engine)
