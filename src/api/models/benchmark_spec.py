"""SQLAlchemy model for immutable benchmark specification bindings."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Index, String, UniqueConstraint, event
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db_base import Base


class BenchmarkSpec(Base):
    """Immutable benchmark contract that binds a model to benchmark configuration."""

    __tablename__ = "benchmark_specs"
    __table_args__ = (
        UniqueConstraint(
            "model_id",
            "dataset_id",
            "dataset_version",
            name="uq_benchmark_specs_model_dataset_version",
        ),
    )

    spec_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(255), nullable=False)
    eval_split: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_direction: Mapped[str] = mapped_column(String(32), nullable=False)
    tiebreak_rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    input_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    eval_container_digest: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


Index("ix_benchmark_specs_model_active", BenchmarkSpec.model_id, BenchmarkSpec.is_active)


@event.listens_for(BenchmarkSpec, "before_update", propagate=True)
def _prevent_benchmark_spec_update(_mapper: object, _connection: object, _target: object) -> None:
    raise ValueError("BenchmarkSpec is immutable and cannot be updated")
