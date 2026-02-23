"""SQLAlchemy model for GDPR consent records."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db_base import Base


class ConsentRecord(Base):
    """Consent lifecycle record for a user and consent type."""

    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    consent_type: Mapped[str] = mapped_column(String(128), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
