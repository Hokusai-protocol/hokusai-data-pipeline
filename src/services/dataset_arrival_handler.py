"""Service for processing S3 dataset arrival events from SQS."""
# ruff: noqa: ANN101

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.api.models.dataset_arrival import DatasetArrival

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]

DATASET_PREFIX_PATTERN = re.compile(r"^datasets/(?P<model_id>[^/]+)/(?P<version>[^/]+)/")


def parse_s3_event_message(raw_body: str) -> list[dict[str, Any]]:
    """Parse an SQS message body into a list of S3 event records.

    Handles both raw S3 event notifications and EventBridge-wrapped messages.
    """
    payload = json.loads(raw_body)

    # Direct S3 event notification format
    if "Records" in payload:
        return [
            _extract_s3_fields(record)
            for record in payload["Records"]
            if record.get("eventSource") == "aws:s3"
            and record.get("eventName", "").startswith("ObjectCreated:")
        ]

    # EventBridge-wrapped S3 event
    if payload.get("source") == "aws.s3" and payload.get("detail-type") == "Object Created":
        detail = payload.get("detail", {})
        return [
            {
                "bucket": detail.get("bucket", {}).get("name", ""),
                "key": detail.get("object", {}).get("key", ""),
                "size": detail.get("object", {}).get("size", 0),
                "etag": detail.get("object", {}).get("etag"),
                "event_time": payload.get("time"),
            }
        ]

    return []


def _extract_s3_fields(record: dict[str, Any]) -> dict[str, Any]:
    s3 = record.get("s3", {})
    return {
        "bucket": s3.get("bucket", {}).get("name", ""),
        "key": s3.get("object", {}).get("key", ""),
        "size": s3.get("object", {}).get("size", 0),
        "etag": s3.get("object", {}).get("eTag"),
        "event_time": record.get("eventTime"),
    }


def extract_model_id_from_key(object_key: str) -> tuple[str | None, str | None]:
    """Extract model_id and version from datasets/{model_id}/{version}/ key."""
    match = DATASET_PREFIX_PATTERN.match(object_key)
    if match:
        return match.group("model_id"), match.group("version")
    return None, None


class DatasetArrivalHandler:
    """Processes S3 dataset upload events and optionally triggers re-evaluation."""

    def __init__(
        self,
        session_factory: SessionFactory | None = None,
        database_url: str | None = None,
        benchmark_spec_service: Any | None = None,
        evaluation_queue_manager: Any | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._database_url = database_url
        self._benchmark_spec_service = benchmark_spec_service
        self._evaluation_queue_manager = evaluation_queue_manager
        self._in_memory_arrivals: list[dict[str, Any]] = []
        self._lock = Lock()

    def _get_session_factory(self) -> SessionFactory | None:
        if self._session_factory:
            return self._session_factory
        if self._database_url:
            engine = create_engine(self._database_url, pool_pre_ping=True)
            return sessionmaker(autocommit=False, autoflush=False, bind=engine)
        return None

    @contextmanager
    def _session_scope(self) -> Iterator[Session | None]:
        factory = self._get_session_factory()
        if factory is None:
            yield None
            return
        session = factory()
        try:
            yield session
        finally:
            session.close()

    def handle_s3_event(self, raw_body: str) -> list[dict[str, Any]]:
        """Parse and process an SQS message containing S3 event(s).

        Returns a list of arrival records created.
        """
        try:
            records = parse_s3_event_message(raw_body)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("event=dataset_arrival_parse_error error=%s", str(exc))
            return []

        results = []
        for record in records:
            result = self._process_record(record)
            if result:
                results.append(result)
        return results

    def _process_record(self, record: dict[str, Any]) -> dict[str, Any] | None:
        bucket = record.get("bucket", "")
        key = record.get("key", "")

        if not bucket or not key:
            return None

        model_id, dataset_version = extract_model_id_from_key(key)
        if not model_id:
            logger.debug("event=dataset_arrival_skip_non_dataset key=%s", key)
            return None

        event_time = None
        if record.get("event_time"):
            try:
                event_time = datetime.fromisoformat(record["event_time"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        spec_id = None
        reeval_triggered = False
        error_message = None

        # Look up active BenchmarkSpec for this model
        if self._benchmark_spec_service:
            try:
                spec = self._benchmark_spec_service.get_active_spec_for_model(model_id)
                if spec:
                    spec_id = spec.get("spec_id")

                    # Update the spec's dataset reference to point to the new version
                    s3_uri = f"s3://{bucket}/{key}"
                    self._benchmark_spec_service.update_spec_fields(
                        spec_id,
                        {
                            "dataset_id": s3_uri,
                            "dataset_version": dataset_version,
                        },
                    )

                    # Optionally trigger re-evaluation
                    if self._evaluation_queue_manager:
                        reeval_triggered = self._trigger_reeval(model_id, spec, s3_uri)
            except Exception as exc:
                error_message = str(exc)
                logger.exception(
                    "event=dataset_arrival_processing_error model_id=%s key=%s",
                    model_id,
                    key,
                )

        arrival = self._persist_arrival(
            bucket=bucket,
            object_key=key,
            object_size_bytes=record.get("size", 0),
            etag=record.get("etag"),
            model_id=model_id,
            dataset_version=dataset_version,
            spec_id=spec_id,
            reeval_triggered=reeval_triggered,
            error_message=error_message,
            s3_event_time=event_time,
        )

        logger.info(
            "event=dataset_arrival_processed model_id=%s version=%s reeval=%s",
            model_id,
            dataset_version,
            reeval_triggered,
        )

        return arrival

    def _trigger_reeval(self, model_id: str, spec: dict[str, Any], s3_uri: str) -> bool:
        """Enqueue a re-evaluation job with deduplication. Returns True if enqueued."""
        from src.models.evaluation_job import EvaluationJobPriority

        try:
            eval_config = {
                "trigger": "dataset_arrival",
                "dataset_uri": s3_uri,
                "benchmark_spec": {
                    "spec_id": spec.get("spec_id"),
                    "metric_name": spec.get("metric_name"),
                    "metric_direction": spec.get("metric_direction"),
                    "eval_split": spec.get("eval_split"),
                },
            }
            job_id = self._evaluation_queue_manager.enqueue_with_dedup(
                model_id=model_id,
                trigger_source="data_arrival",
                eval_config=eval_config,
                priority=EvaluationJobPriority.NORMAL.value,
                metadata={"trigger_source": "s3_dataset_arrival"},
            )
            if job_id:
                logger.info(
                    "event=dataset_arrival_reeval_enqueued model_id=%s job_id=%s",
                    model_id,
                    job_id,
                )
                return True
            logger.info(
                "event=dataset_arrival_reeval_deduplicated model_id=%s",
                model_id,
            )
            return False
        except Exception as exc:
            logger.error(
                "event=dataset_arrival_reeval_failed model_id=%s error=%s",
                model_id,
                str(exc),
            )
            return False

    def _persist_arrival(self, **kwargs: Any) -> dict[str, Any]:
        arrival_id = str(uuid4())
        now = datetime.now(timezone.utc)

        with self._session_scope() as session:
            if session is not None:
                row = DatasetArrival(id=arrival_id, **kwargs)
                session.add(row)
                session.commit()
                return self._encode_row(row)

        record = {"id": arrival_id, "created_at": now.isoformat(), **kwargs}
        if record.get("s3_event_time") and hasattr(record["s3_event_time"], "isoformat"):
            record["s3_event_time"] = record["s3_event_time"].isoformat()
        with self._lock:
            self._in_memory_arrivals.append(record)
        return record

    def list_arrivals(
        self, *, model_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List recent dataset arrival events."""
        with self._session_scope() as session:
            if session is not None:
                query = session.query(DatasetArrival)
                if model_id:
                    query = query.filter(DatasetArrival.model_id == model_id)
                rows = query.order_by(DatasetArrival.created_at.desc()).limit(limit).all()
                return [self._encode_row(row) for row in rows]

        with self._lock:
            items = list(self._in_memory_arrivals)
        if model_id:
            items = [i for i in items if i.get("model_id") == model_id]
        return sorted(items, key=lambda x: x.get("created_at", ""), reverse=True)[:limit]

    @staticmethod
    def _encode_row(row: DatasetArrival) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "bucket": row.bucket,
            "object_key": row.object_key,
            "object_size_bytes": row.object_size_bytes,
            "etag": row.etag,
            "model_id": row.model_id,
            "dataset_version": row.dataset_version,
            "spec_id": row.spec_id,
            "reeval_triggered": row.reeval_triggered,
            "error_message": row.error_message,
            "s3_event_time": row.s3_event_time.isoformat() if row.s3_event_time else None,
            "created_at": row.created_at.isoformat(),
        }
