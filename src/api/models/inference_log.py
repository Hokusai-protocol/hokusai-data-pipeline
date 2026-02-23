"""SQLAlchemy model for inference usage and outcomes logging."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db_base import Base


class InferenceLog(Base):
    """Durable inference log row used for feedback and contributor attribution."""

    __tablename__ = "inference_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    api_token_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str] = mapped_column(String(255), nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    trace_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    outcome_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    outcome_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


Index(
    "ix_inference_logs_model_name_model_version",
    InferenceLog.model_name,
    InferenceLog.model_version,
)
Index("ix_inference_logs_created_at", InferenceLog.created_at)
