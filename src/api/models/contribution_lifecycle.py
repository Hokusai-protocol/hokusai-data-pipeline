"""SQLAlchemy model for accepted contribution processing lifecycle state."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .db_base import Base


class ContributionLifecycleState(str, Enum):
    """Valid lifecycle states for an accepted contribution submission."""

    RECEIVED = "received"
    QUEUED = "queued"
    PROCESSING = "processing"
    PROCESSED = "processed"
    REJECTED = "rejected"
    INCLUDED_IN_TRAINING = "included_in_training"
    EXCLUDED = "excluded"


LIFECYCLE_STATE_VALUES = tuple(state.value for state in ContributionLifecycleState)
_STATE_CHECK = ", ".join(f"'{state}'" for state in LIFECYCLE_STATE_VALUES)
JSONB_COMPAT_TYPE = JSONB().with_variant(JSON(), "sqlite")


class ContributionLifecycle(Base):
    """Mutable processing state associated with a submission id."""

    __tablename__ = "contribution_lifecycle"
    __table_args__ = (
        CheckConstraint(
            f"state IN ({_STATE_CHECK})",
            name="ck_contribution_lifecycle_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(  # noqa: A003
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    submission_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    state: Mapped[str] = mapped_column(String(64), nullable=False)
    accepted_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_metadata: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB_COMPAT_TYPE,
        nullable=True,
    )
    training_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evaluation_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    callback_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    callback_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    callback_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    callback_last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
