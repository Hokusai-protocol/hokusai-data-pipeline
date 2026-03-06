"""Service for evaluation schedule configuration CRUD."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.models.benchmark_spec import BenchmarkSpec
from src.api.models.evaluation_schedule import EvaluationSchedule

SessionFactory = Callable[[], Session]


class NoBenchmarkSpecError(ValueError):
    """Raised when a model has no active BenchmarkSpec."""


class ScheduleAlreadyExistsError(ValueError):
    """Raised when a schedule already exists for a model."""


class EvaluationScheduleService:
    """CRUD operations for evaluation schedule configuration."""

    def __init__(
        self: EvaluationScheduleService,
        session_factory: SessionFactory | None = None,
        benchmark_spec_service: Any | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._benchmark_spec_service = benchmark_spec_service
        self._in_memory_schedules: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    @contextmanager
    def _session_scope(self: EvaluationScheduleService) -> Iterator[Session | None]:
        if self._session_factory is None:
            yield None
            return
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    def _has_active_benchmark_spec(
        self: EvaluationScheduleService, model_id: str, session: Session | None
    ) -> bool:
        if session is not None:
            row = (
                session.query(BenchmarkSpec)
                .filter(BenchmarkSpec.model_id == model_id, BenchmarkSpec.is_active.is_(True))
                .first()
            )
            return row is not None

        if self._benchmark_spec_service is not None:
            spec = self._benchmark_spec_service.get_active_spec_for_model(model_id)
            return spec is not None

        return False

    def create_schedule(
        self: EvaluationScheduleService,
        *,
        model_id: str,
        cron_expression: str,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Create a new evaluation schedule for a model."""
        with self._session_scope() as session:
            if not self._has_active_benchmark_spec(model_id, session):
                raise NoBenchmarkSpecError(
                    f"Model {model_id} must have an active BenchmarkSpec before creating a schedule"
                )

            if session is not None:
                now = datetime.now(timezone.utc)
                row = EvaluationSchedule(
                    id=str(uuid4()),
                    model_id=model_id,
                    cron_expression=cron_expression,
                    enabled=enabled,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                try:
                    session.commit()
                except IntegrityError as exc:
                    session.rollback()
                    raise ScheduleAlreadyExistsError(
                        f"An evaluation schedule already exists for model {model_id}"
                    ) from exc
                return self._encode_row(row)

        with self._lock:
            existing = [s for s in self._in_memory_schedules.values() if s["model_id"] == model_id]
            if existing:
                raise ScheduleAlreadyExistsError(
                    f"An evaluation schedule already exists for model {model_id}"
                )
            now = datetime.now(timezone.utc)
            schedule_id = str(uuid4())
            record = {
                "id": schedule_id,
                "model_id": model_id,
                "cron_expression": cron_expression,
                "enabled": enabled,
                "last_run_at": None,
                "next_run_at": None,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            self._in_memory_schedules[schedule_id] = record

        return record

    def get_schedule(self: EvaluationScheduleService, model_id: str) -> dict[str, Any] | None:
        """Fetch the evaluation schedule for a model."""
        with self._session_scope() as session:
            if session is not None:
                row = (
                    session.query(EvaluationSchedule)
                    .filter(EvaluationSchedule.model_id == model_id)
                    .first()
                )
                return self._encode_row(row) if row else None

        with self._lock:
            for schedule in self._in_memory_schedules.values():
                if schedule["model_id"] == model_id:
                    return dict(schedule)
        return None

    def update_schedule(
        self: EvaluationScheduleService, model_id: str, changes: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update an existing evaluation schedule. Returns updated dict or None."""
        with self._session_scope() as session:
            if session is not None:
                row = (
                    session.query(EvaluationSchedule)
                    .filter(EvaluationSchedule.model_id == model_id)
                    .first()
                )
                if row is None:
                    return None
                for key, value in changes.items():
                    setattr(row, key, value)
                row.updated_at = datetime.now(timezone.utc)
                session.commit()
                session.refresh(row)
                return self._encode_row(row)

        with self._lock:
            for schedule in self._in_memory_schedules.values():
                if schedule["model_id"] == model_id:
                    schedule.update(changes)
                    schedule["updated_at"] = datetime.now(timezone.utc).isoformat()
                    return dict(schedule)
        return None

    def delete_schedule(self: EvaluationScheduleService, model_id: str) -> bool:
        """Delete evaluation schedule for a model. Returns True if deleted."""
        with self._session_scope() as session:
            if session is not None:
                row = (
                    session.query(EvaluationSchedule)
                    .filter(EvaluationSchedule.model_id == model_id)
                    .first()
                )
                if row is None:
                    return False
                session.delete(row)
                session.commit()
                return True

        with self._lock:
            to_delete = None
            for sid, schedule in self._in_memory_schedules.items():
                if schedule["model_id"] == model_id:
                    to_delete = sid
                    break
            if to_delete:
                del self._in_memory_schedules[to_delete]
                return True
        return False

    @staticmethod
    def _encode_row(row: EvaluationSchedule) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "model_id": row.model_id,
            "cron_expression": row.cron_expression,
            "enabled": row.enabled,
            "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
            "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }
