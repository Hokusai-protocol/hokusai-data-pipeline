"""SQLAlchemy model for tracking S3 dataset arrival events."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db_base import Base


class DatasetArrival(Base):
    """Records each S3 dataset upload event detected via SQS."""

    __tablename__ = "dataset_arrivals"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)  # noqa: A003
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    object_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    dataset_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    spec_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reeval_triggered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    s3_event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
