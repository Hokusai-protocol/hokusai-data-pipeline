"""Business logic for evaluation API endpoints."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from redis import Redis

from src.api.schemas.evaluations import (
    EvaluationJobStatus,
    EvaluationManifestResponse,
    EvaluationRequest,
    EvaluationResponse,
    EvaluationStatusResponse,
)


@dataclass
class EvaluationJobRecord:
    """Redis-backed evaluation job record."""

    job_id: str
    model_id: str
    status: str
    eval_type: str
    dataset_reference: str
    parameters: dict[str, Any]
    estimated_cost: float
    progress_percentage: float
    queue_position: int
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error_details: str | None = None


class EvaluationService:
    """Service for creating and tracking asynchronous evaluation jobs."""

    JOB_TTL_SECONDS = 24 * 60 * 60
    MANIFEST_TTL_SECONDS = 7 * 24 * 60 * 60
    IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60
    QUEUE_KEY = "eval:queue"

    def __init__(self: EvaluationService, redis_client: Redis) -> None:
        self.redis = redis_client
        self.max_cost_usd = float(os.getenv("EVALUATION_MAX_COST_USD", "25"))

    def create_evaluation(
        self: EvaluationService,
        model_id: str,
        payload: EvaluationRequest,
        idempotency_key: str,
    ) -> EvaluationResponse:
        """Create an evaluation job or return previous response for same idempotency key."""
        if not idempotency_key:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Idempotency-Key header is required",
            )

        self._validate_model_exists(model_id)

        idempotency_lookup_key = self._idempotency_key(model_id, idempotency_key)
        if existing_job_id := self.redis.get(idempotency_lookup_key):
            return self._response_from_job_id(existing_job_id)

        estimated_cost = self._estimate_cost(payload)
        if estimated_cost > self.max_cost_usd:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    f"Estimated evaluation cost ${estimated_cost:.4f} exceeds allowed "
                    f"threshold ${self.max_cost_usd:.4f}"
                ),
            )

        job_id = str(uuid4())
        now = datetime.now(timezone.utc)
        queue_score = now.timestamp()
        self.redis.zadd(self.QUEUE_KEY, {job_id: queue_score})
        queue_position = self._queue_position(job_id)

        job_record = EvaluationJobRecord(
            job_id=job_id,
            model_id=model_id,
            status=EvaluationJobStatus.queued.value,
            eval_type=payload.config.eval_type,
            dataset_reference=payload.config.dataset_reference,
            parameters=payload.config.parameters,
            estimated_cost=estimated_cost,
            progress_percentage=0.0,
            queue_position=queue_position,
            created_at=now.isoformat(),
        )

        self.redis.setex(
            self._job_key(job_id),
            self.JOB_TTL_SECONDS,
            json.dumps(job_record.__dict__),
        )
        self.redis.setex(idempotency_lookup_key, self.IDEMPOTENCY_TTL_SECONDS, job_id)

        return EvaluationResponse(
            job_id=UUID(job_id),
            status=EvaluationJobStatus.queued,
            estimated_cost=estimated_cost,
            queue_position=queue_position,
            created_at=now,
        )

    def get_status(self: EvaluationService, job_id: str) -> EvaluationStatusResponse:
        """Fetch job status from Redis."""
        job_data = self._load_job(job_id)
        status_value = job_data["status"]
        queue_position: int | None = None
        if status_value == EvaluationJobStatus.queued.value:
            queue_position = self._queue_position(job_id)

        return EvaluationStatusResponse(
            job_id=UUID(job_id),
            status=EvaluationJobStatus(status_value),
            progress_percentage=float(job_data.get("progress_percentage", 0.0)),
            queue_position=queue_position,
            started_at=self._parse_datetime(job_data.get("started_at")),
            completed_at=self._parse_datetime(job_data.get("completed_at")),
            error_details=job_data.get("error_details"),
        )

    def get_manifest(self: EvaluationService, job_id: str) -> EvaluationManifestResponse:
        """Fetch manifest for a completed job."""
        job_data = self._load_job(job_id)

        if job_data["status"] != EvaluationJobStatus.completed.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Evaluation job {job_id} is not completed",
            )

        raw_manifest = self.redis.get(self._manifest_key(job_id))
        if not raw_manifest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Manifest for job {job_id} not found",
            )

        manifest = json.loads(raw_manifest)
        return EvaluationManifestResponse(
            job_id=UUID(manifest["job_id"]),
            model_id=manifest["model_id"],
            eval_type=manifest["eval_type"],
            results_summary=manifest.get("results_summary", {}),
            metrics=manifest.get("metrics", {}),
            artifact_urls=manifest.get("artifact_urls", []),
            created_at=self._parse_datetime(manifest["created_at"]),
            completed_at=self._parse_datetime(manifest["completed_at"]),
        )

    def execute_evaluation_job(self: EvaluationService, job_id: str) -> None:
        """Background execution placeholder for evaluation processing."""
        job_data = self._load_job(job_id)
        started_at = datetime.now(timezone.utc)
        job_data["status"] = EvaluationJobStatus.running.value
        job_data["started_at"] = started_at.isoformat()
        job_data["progress_percentage"] = 25.0
        self._save_job(job_id, job_data)

        completed_at = datetime.now(timezone.utc)
        job_data["status"] = EvaluationJobStatus.completed.value
        job_data["completed_at"] = completed_at.isoformat()
        job_data["progress_percentage"] = 100.0
        job_data["queue_position"] = 0
        self._save_job(job_id, job_data)
        self.redis.zrem(self.QUEUE_KEY, job_id)

        manifest = {
            "job_id": job_id,
            "model_id": job_data["model_id"],
            "eval_type": job_data["eval_type"],
            "results_summary": {
                "status": "completed",
                "dataset": job_data["dataset_reference"],
            },
            "metrics": {"accuracy": 0.0},
            "artifact_urls": [],
            "created_at": job_data["created_at"],
            "completed_at": completed_at.isoformat(),
        }
        self.redis.setex(
            self._manifest_key(job_id),
            self.MANIFEST_TTL_SECONDS,
            json.dumps(manifest),
        )

    def _validate_model_exists(self: EvaluationService, model_id: str) -> None:
        try:
            import mlflow

            # MLflow client auth is configured globally via environment variables
            # (for example MLFLOW_TRACKING_TOKEN / Authorization passthrough).
            client = mlflow.tracking.MlflowClient()
            versions = client.search_model_versions(f"name='{model_id}'")
            if versions:
                return

            # Fallback check for registered model existence.
            client.get_registered_model(model_id)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model {model_id} not found",
            ) from exc

    def _estimate_cost(self: EvaluationService, payload: EvaluationRequest) -> float:
        parameters = payload.config.parameters
        dataset_size = int(parameters.get("dataset_size", 100))
        max_tokens = int(parameters.get("max_tokens", 1000))
        if dataset_size <= 0 or max_tokens <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="dataset_size and max_tokens must be positive integers",
            )

        token_volume = dataset_size * max_tokens
        # Conservative default estimate for OpenAI eval-style workloads.
        return round((token_volume / 1000.0) * 0.002, 6)

    def _response_from_job_id(self: EvaluationService, job_id: str) -> EvaluationResponse:
        job_data = self._load_job(job_id)
        queue_position = self._queue_position(job_id)
        created_at = self._parse_datetime(job_data["created_at"])

        return EvaluationResponse(
            job_id=UUID(job_data["job_id"]),
            status=EvaluationJobStatus(job_data["status"]),
            estimated_cost=float(job_data["estimated_cost"]),
            queue_position=queue_position,
            created_at=created_at,
        )

    def _load_job(self: EvaluationService, job_id: str) -> dict[str, Any]:
        raw = self.redis.get(self._job_key(job_id))
        if not raw:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation job {job_id} not found",
            )
        return json.loads(raw)

    def _save_job(self: EvaluationService, job_id: str, payload: dict[str, Any]) -> None:
        # Refresh TTL on state transitions to keep active jobs available.
        self.redis.setex(self._job_key(job_id), self.JOB_TTL_SECONDS, json.dumps(payload))

    def _queue_position(self: EvaluationService, job_id: str) -> int | None:
        rank = self.redis.zrank(self.QUEUE_KEY, job_id)
        if rank is None:
            return None
        return int(rank) + 1

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if value is None:
            return None
        return datetime.fromisoformat(value)

    @staticmethod
    def _job_key(job_id: str) -> str:
        return f"eval:job:{job_id}"

    @staticmethod
    def _manifest_key(job_id: str) -> str:
        return f"eval:manifest:{job_id}"

    @staticmethod
    def _idempotency_key(model_id: str, idempotency_key: str) -> str:
        return f"eval:idempotency:{model_id}:{idempotency_key}"

    @staticmethod
    def status_expires_at(created_at: datetime) -> datetime:
        """Return job status expiry timestamp for the configured TTL policy."""
        return created_at + timedelta(seconds=EvaluationService.JOB_TTL_SECONDS)
