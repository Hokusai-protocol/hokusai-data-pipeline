"""Service for immutable benchmark specification registration and lookup."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from src.api.models import BenchmarkSpec

SessionFactory = Callable[[], Session]

VALID_METRIC_DIRECTIONS = {"higher_is_better", "lower_is_better"}


class BenchmarkSpecImmutableError(ValueError):
    """Raised when attempting to mutate an immutable benchmark specification."""


class BenchmarkSpecConflictError(ValueError):
    """Raised when a unique model/dataset/dataset_version binding already exists."""


@lru_cache(maxsize=4)
def _session_factory_from_url(database_url: str) -> sessionmaker:
    engine = create_engine(database_url, pool_pre_ping=True)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


class BenchmarkSpecService:
    """Create/list/get benchmark specs with immutable semantics."""

    def __init__(
        self: BenchmarkSpecService,
        session_factory: SessionFactory | None = None,
        database_url: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._database_url = database_url
        self._in_memory_specs: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def _get_session_factory(self: BenchmarkSpecService) -> SessionFactory | None:
        if self._session_factory:
            return self._session_factory

        database_url = self._database_url
        if not database_url:
            return None

        return _session_factory_from_url(database_url)

    @contextmanager
    def _session_scope(self: BenchmarkSpecService) -> Iterator[Session | None]:
        session_factory = self._get_session_factory()
        if session_factory is None:
            yield None
            return

        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def register_spec(
        self: BenchmarkSpecService,
        *,
        model_id: str,
        dataset_id: str,
        dataset_version: str,
        eval_split: str,
        metric_name: str,
        metric_direction: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        tiebreak_rules: dict[str, Any] | None = None,
        eval_container_digest: str | None = None,
        is_active: bool = True,
    ) -> dict[str, Any]:
        """Create an immutable benchmark spec record."""
        if metric_direction not in VALID_METRIC_DIRECTIONS:
            raise ValueError("metric_direction must be one of: higher_is_better, lower_is_better")

        now = datetime.now(timezone.utc)
        spec_id = str(uuid4())

        with self._session_scope() as session:
            if session is not None:
                row = BenchmarkSpec(
                    spec_id=spec_id,
                    model_id=model_id,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    eval_split=eval_split,
                    metric_name=metric_name,
                    metric_direction=metric_direction,
                    tiebreak_rules=tiebreak_rules,
                    input_schema=input_schema,
                    output_schema=output_schema,
                    eval_container_digest=eval_container_digest,
                    created_at=now,
                    is_active=is_active,
                )
                session.add(row)
                try:
                    session.commit()
                except IntegrityError as exc:
                    session.rollback()
                    raise BenchmarkSpecConflictError(
                        "A benchmark spec already exists for this model/dataset/version"
                    ) from exc
                return self._encode_row(row)

        record = {
            "spec_id": spec_id,
            "model_id": model_id,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "eval_split": eval_split,
            "metric_name": metric_name,
            "metric_direction": metric_direction,
            "tiebreak_rules": tiebreak_rules,
            "input_schema": input_schema,
            "output_schema": output_schema,
            "eval_container_digest": eval_container_digest,
            "created_at": now.isoformat(),
            "is_active": is_active,
        }

        with self._lock:
            duplicate = [
                spec
                for spec in self._in_memory_specs.values()
                if spec["model_id"] == model_id
                and spec["dataset_id"] == dataset_id
                and spec["dataset_version"] == dataset_version
            ]
            if duplicate:
                raise BenchmarkSpecConflictError(
                    "A benchmark spec already exists for this model/dataset/version"
                )
            self._in_memory_specs[spec_id] = record

        return record

    def list_specs(
        self: BenchmarkSpecService, *, model_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List benchmark specs, optionally scoped to a model."""
        with self._session_scope() as session:
            if session is not None:
                query = session.query(BenchmarkSpec)
                if model_id:
                    query = query.filter(BenchmarkSpec.model_id == model_id)
                rows = (
                    query.order_by(BenchmarkSpec.created_at.desc())
                    .order_by(BenchmarkSpec.spec_id.desc())
                    .all()
                )
                return [self._encode_row(row) for row in rows]

        with self._lock:
            items = list(self._in_memory_specs.values())

        if model_id:
            items = [item for item in items if item["model_id"] == model_id]

        return sorted(items, key=lambda item: item["created_at"], reverse=True)

    def get_spec(self: BenchmarkSpecService, spec_id: str) -> dict[str, Any] | None:
        """Fetch one benchmark spec by id."""
        with self._session_scope() as session:
            if session is not None:
                row = session.query(BenchmarkSpec).filter(BenchmarkSpec.spec_id == spec_id).first()
                return self._encode_row(row) if row else None

        with self._lock:
            return self._in_memory_specs.get(spec_id)

    def get_active_spec_for_model(
        self: BenchmarkSpecService, model_id: str
    ) -> dict[str, Any] | None:
        """Fetch latest active benchmark spec bound to model id."""
        with self._session_scope() as session:
            if session is not None:
                row = (
                    session.query(BenchmarkSpec)
                    .filter(BenchmarkSpec.model_id == model_id, BenchmarkSpec.is_active.is_(True))
                    .order_by(BenchmarkSpec.created_at.desc())
                    .order_by(BenchmarkSpec.spec_id.desc())
                    .first()
                )
                return self._encode_row(row) if row else None

        with self._lock:
            candidates = [
                item
                for item in self._in_memory_specs.values()
                if item["model_id"] == model_id and item["is_active"]
            ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item["created_at"], reverse=True)[0]

    def update_spec(self: BenchmarkSpecService, spec_id: str, _changes: dict[str, Any]) -> None:
        """Benchmark specs are immutable; updates are rejected."""
        raise BenchmarkSpecImmutableError(
            f"Benchmark spec {spec_id} is immutable; create a new spec version instead"
        )

    @staticmethod
    def _encode_row(row: BenchmarkSpec) -> dict[str, Any]:
        return {
            "spec_id": str(row.spec_id),
            "model_id": row.model_id,
            "dataset_id": row.dataset_id,
            "dataset_version": row.dataset_version,
            "eval_split": row.eval_split,
            "metric_name": row.metric_name,
            "metric_direction": row.metric_direction,
            "tiebreak_rules": row.tiebreak_rules,
            "input_schema": row.input_schema,
            "output_schema": row.output_schema,
            "eval_container_digest": row.eval_container_digest,
            "created_at": row.created_at.isoformat(),
            "is_active": row.is_active,
        }
