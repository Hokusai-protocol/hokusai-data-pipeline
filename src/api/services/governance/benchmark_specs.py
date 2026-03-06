"""Service for immutable benchmark specification registration and lookup."""

from __future__ import annotations

import hashlib
import io
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

import boto3
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from src.api.models import BenchmarkSpec
from src.api.services.dataset_validator import DatasetValidator
from src.api.services.privacy.pii_detector import PIIDetector, PIIScanResult

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]

VALID_METRIC_DIRECTIONS = {"higher_is_better", "lower_is_better"}


class BenchmarkSpecImmutableError(ValueError):
    """Raised when attempting to mutate an immutable benchmark specification."""


class BenchmarkSpecConflictError(ValueError):
    """Raised when a unique model/dataset/dataset_version binding already exists."""


class PIIFoundError(ValueError):
    """Raised when PII is detected in an uploaded dataset and allow_pii is not set."""


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
        provider: str = "hokusai",
        tiebreak_rules: dict[str, Any] | None = None,
        eval_container_digest: str | None = None,
        is_active: bool = True,
    ) -> dict[str, Any]:
        """Create an immutable benchmark spec record."""
        if metric_direction not in VALID_METRIC_DIRECTIONS:
            raise ValueError("metric_direction must be one of: higher_is_better, lower_is_better")

        if provider not in {"hokusai", "kaggle"}:
            raise ValueError("provider must be one of: hokusai, kaggle")

        now = datetime.now(timezone.utc)
        spec_id = str(uuid4())

        with self._session_scope() as session:
            if session is not None:
                row = BenchmarkSpec(
                    spec_id=spec_id,
                    provider=provider,
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
            "provider": provider,
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

    def list_specs_paginated(
        self: BenchmarkSpecService,
        *,
        model_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """List benchmark specs with pagination, returning (items, total)."""
        with self._session_scope() as session:
            if session is not None:
                query = session.query(BenchmarkSpec)
                if model_id:
                    query = query.filter(BenchmarkSpec.model_id == model_id)
                total = query.count()
                rows = (
                    query.order_by(BenchmarkSpec.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                    .all()
                )
                return [self._encode_row(row) for row in rows], total

        with self._lock:
            items = list(self._in_memory_specs.values())
        if model_id:
            items = [item for item in items if item["model_id"] == model_id]
        items = sorted(items, key=lambda item: item["created_at"], reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total

    def update_spec(self: BenchmarkSpecService, spec_id: str, _changes: dict[str, Any]) -> None:
        """Benchmark specs are immutable; updates are rejected."""
        raise BenchmarkSpecImmutableError(
            f"Benchmark spec {spec_id} is immutable; create a new spec version instead"
        )

    def update_spec_fields(
        self: BenchmarkSpecService, spec_id: str, changes: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update spec fields using core SQL to bypass ORM immutability guard.

        Returns the updated spec dict, or None if not found.
        """
        from sqlalchemy import update

        with self._session_scope() as session:
            if session is not None:
                row = session.query(BenchmarkSpec).filter(BenchmarkSpec.spec_id == spec_id).first()
                if row is None:
                    return None
                if changes:
                    session.execute(
                        update(BenchmarkSpec)
                        .where(BenchmarkSpec.spec_id == spec_id)
                        .values(**changes)
                    )
                    session.commit()
                    session.refresh(row)
                return self._encode_row(row)

        with self._lock:
            if spec_id not in self._in_memory_specs:
                return None
            self._in_memory_specs[spec_id].update(changes)
            return dict(self._in_memory_specs[spec_id])

    def delete_spec(self: BenchmarkSpecService, spec_id: str) -> bool:
        """Delete a benchmark spec. Returns True if deleted, False if not found."""
        with self._session_scope() as session:
            if session is not None:
                row = session.query(BenchmarkSpec).filter(BenchmarkSpec.spec_id == spec_id).first()
                if row is None:
                    return False
                session.delete(row)
                session.commit()
                return True

        with self._lock:
            if spec_id in self._in_memory_specs:
                del self._in_memory_specs[spec_id]
                return True
            return False

    def upload_dataset(
        self: BenchmarkSpecService,
        *,
        model_id: str,
        filename: str,
        file_bytes: bytes,
        pii_detector: PIIDetector,
        allow_pii: bool = False,
        spec_fields: dict[str, Any],
        dataset_validator: DatasetValidator | None = None,
    ) -> dict[str, Any]:
        """Upload a dataset file to S3, scan for PII, and create a BenchmarkSpec atomically.

        Returns dict with s3_uri, sha256_hash, spec_id, filename, file_size_bytes.
        """
        import pandas as pd

        # Compute SHA-256 hash
        sha256_hash = hashlib.sha256(file_bytes).hexdigest()
        file_size = len(file_bytes)

        # Load into DataFrame for PII scan
        suffix = os.path.splitext(filename)[1].lower()
        buf = io.BytesIO(file_bytes)
        if suffix == ".csv":
            df = pd.read_csv(buf)
        elif suffix == ".parquet":
            df = pd.read_parquet(buf)
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

        # Dataset format validation
        if dataset_validator is not None:
            target_column = (spec_fields.get("output_schema") or {}).get("target_column", "")
            input_columns = (spec_fields.get("input_schema") or {}).get("columns", [])
            dataset_validator.validate(
                df,
                target_column=target_column,
                input_columns=input_columns,
                file_size_bytes=file_size,
            )

        # PII scan
        scan_result: PIIScanResult = pii_detector.scan_dataframe(df)
        if scan_result.total_findings > 0 and not allow_pii:
            raise PIIFoundError(
                f"PII detected in uploaded dataset: {scan_result.total_findings} finding(s). "
                "Set allow_pii=true to proceed."
            )

        # Upload to S3
        bucket = os.environ.get("HOKUSAI_DATASET_BUCKET")
        if not bucket:
            raise ValueError("HOKUSAI_DATASET_BUCKET environment variable is not set")

        version = f"v{uuid4().hex[:8]}"
        s3_key = f"datasets/{model_id}/{version}/{filename}"
        s3_uri = f"s3://{bucket}/{s3_key}"

        s3_client = boto3.client("s3")
        s3_client.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=file_bytes,
            ServerSideEncryption="aws:kms",
            Metadata={
                "model_id": model_id,
                "sha256": sha256_hash,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Create BenchmarkSpec atomically; clean up S3 on failure
        try:
            result = self.register_spec(
                model_id=model_id,
                dataset_id=s3_uri,
                dataset_version=version,
                provider="hokusai",
                **spec_fields,
            )
        except Exception:
            # Clean up orphaned S3 object
            try:
                s3_client.delete_object(Bucket=bucket, Key=s3_key)
            except Exception:
                logger.warning(
                    "Failed to clean up S3 object %s after spec creation failure", s3_key
                )
            raise

        return {
            "s3_uri": s3_uri,
            "sha256_hash": sha256_hash,
            "spec_id": result["spec_id"],
            "filename": filename,
            "file_size_bytes": file_size,
        }

    @staticmethod
    def _encode_row(row: BenchmarkSpec) -> dict[str, Any]:
        return {
            "spec_id": str(row.spec_id),
            "provider": row.provider,
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
