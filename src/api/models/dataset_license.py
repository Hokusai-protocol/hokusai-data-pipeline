"""SQLAlchemy model for dataset licensing metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db_base import Base


class DatasetLicense(Base):
    """License metadata and restrictions for a dataset."""

    __tablename__ = "dataset_licenses"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    dataset_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    license_type: Mapped[str] = mapped_column(String(64), nullable=False)
    allows_commercial: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allows_derivative: Mapped[bool] = mapped_column(Boolean, nullable=False)
    requires_attribution: Mapped[bool] = mapped_column(Boolean, nullable=False)
    restrictions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    verified_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
