"""Redis-backed queue manager for evaluation jobs."""
# ruff: noqa: ANN101, ANN102
# mypy: ignore-errors

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import redis
from redis.exceptions import RedisError

from src.models.evaluation_job import EvaluationJob, EvaluationJobStatus

logger = logging.getLogger(__name__)


@dataclass
class EvaluationQueueConfig:
    """Configuration values for the evaluation queue."""

    max_concurrent_per_model: int = 5
    max_concurrent_global: int = 20
    job_timeout_seconds: int = 1800
    max_retries: int = 3
    retry_base_delay_seconds: int = 60
    poll_interval_seconds: float = 1.0
    key_prefix: str = "hokusai:eval:v1"

    @classmethod
    def from_env(cls) -> EvaluationQueueConfig:
        """Build config from environment variables."""
        return cls(
            max_concurrent_per_model=int(os.getenv("EVAL_QUEUE_MAX_CONCURRENT_PER_MODEL", "5")),
            max_concurrent_global=int(os.getenv("EVAL_QUEUE_MAX_CONCURRENT_GLOBAL", "20")),
            job_timeout_seconds=int(os.getenv("EVAL_QUEUE_JOB_TIMEOUT_SECONDS", "1800")),
            max_retries=int(os.getenv("EVAL_QUEUE_MAX_RETRIES", "3")),
            retry_base_delay_seconds=int(os.getenv("EVAL_QUEUE_RETRY_BASE_DELAY_SECONDS", "60")),
            poll_interval_seconds=float(os.getenv("EVAL_QUEUE_POLL_INTERVAL_SECONDS", "1")),
        )


class EvaluationQueueManager:
    """Manages lifecycle of evaluation jobs in Redis."""

    def __init__(
        self,
        redis_client: redis.Redis,
        config: EvaluationQueueConfig | None = None,
    ) -> None:
        """Initialize queue manager."""
        self.redis = redis_client
        self.config = config or EvaluationQueueConfig.from_env()
        self.dequeue_script = self.redis.register_script(self._dequeue_lua())

    def enqueue(self, job: EvaluationJob) -> str:
        """Enqueue a job using priority ordering with FIFO tie-breaks."""
        now = datetime.now(tz=timezone.utc)
        job.created_at = job.created_at or now
        job.updated_at = now
        job.status = EvaluationJobStatus.PENDING
        if job.timeout_seconds <= 0:
            job.timeout_seconds = self.config.job_timeout_seconds
        if job.max_attempts <= 0:
            job.max_attempts = self.config.max_retries

        queue_score = self._queue_score(job.priority, job.created_at)

        pipe = self.redis.pipeline(transaction=True)
        pipe.hset(self._job_key(job.id), mapping=job.to_redis_hash(queue_score))
        pipe.zadd(self._queue_global_key(), {job.id: queue_score})
        pipe.zadd(self._queue_key(job.model_id), {job.id: queue_score})
        pipe.sadd(self._models_key(), job.model_id)
        pipe.execute()

        logger.info(
            "event=eval_job_enqueued job_id=%s model_id=%s priority=%s",
            job.id,
            job.model_id,
            job.priority,
        )
        return job.id

    def dequeue(self, model_id: str | None = None) -> EvaluationJob | None:
        """Atomically dequeue the next eligible pending job."""
        now_ts = time.time()
        try:
            now_iso = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()
            result = self.dequeue_script(
                keys=[
                    self._queue_global_key(),
                    self._delayed_key(),
                    self._active_global_key(),
                    self._models_key(),
                ],
                args=[
                    now_ts,
                    self.config.max_concurrent_per_model,
                    self.config.max_concurrent_global,
                    model_id or "",
                    self.config.key_prefix,
                    now_iso,
                ],
            )
        except RedisError as exc:
            # fakeredis does not always support Lua evalsha; use fallback dequeue for tests.
            if "unknown command `evalsha`" in str(exc).lower():
                return self._dequeue_fallback(model_id=model_id, now_ts=now_ts, now_iso=now_iso)
            logger.exception("event=eval_dequeue_redis_error")
            raise

        job_id = self._decode(result)
        if not job_id:
            return None

        job = self.get_status(job_id)
        if job:
            logger.info("event=eval_job_started job_id=%s model_id=%s", job.id, job.model_id)
        return job

    def _dequeue_fallback(
        self,
        model_id: str | None,
        now_ts: float,
        now_iso: str,
    ) -> EvaluationJob | None:
        if self.get_active_count() >= self.config.max_concurrent_global:
            return None

        self._promote_due_retries(now_ts)
        queue_key = self._queue_key(model_id) if model_id else self._queue_global_key()
        candidates = [self._decode(item) for item in self.redis.zrange(queue_key, 0, 200)]
        for candidate in candidates:
            if not candidate:
                continue
            job = self.get_status(candidate)
            if not job:
                continue
            if self.get_active_count(job.model_id) >= self.config.max_concurrent_per_model:
                continue

            pipe = self.redis.pipeline(transaction=True)
            pipe.zrem(self._queue_global_key(), job.id)
            pipe.zrem(self._queue_key(job.model_id), job.id)
            pipe.sadd(self._active_global_key(), job.id)
            pipe.sadd(self._active_key(job.model_id), job.id)
            pipe.hset(
                self._job_key(job.id),
                mapping={
                    "status": EvaluationJobStatus.ACTIVE.value,
                    "updated_at": now_iso,
                    "started_at": now_iso,
                },
            )
            pipe.execute()
            return self.get_status(job.id)
        return None

    def complete(
        self,
        job_id: str,
        result: dict[str, Any],
        processing_time_ms: float | None = None,
    ) -> None:
        """Mark an active job completed and persist output."""
        job = self.get_status(job_id)
        if not job:
            return

        now = datetime.now(tz=timezone.utc)
        self.redis.hset(
            self._job_key(job_id),
            mapping={
                "status": EvaluationJobStatus.COMPLETED.value,
                "updated_at": now.isoformat(),
                "completed_at": now.isoformat(),
                "result": json.dumps(result, sort_keys=True),
                "error_message": "",
            },
        )
        self.redis.srem(self._active_key(job.model_id), job_id)
        self.redis.srem(self._active_global_key(), job_id)
        self.redis.incr(self._metric_key("completed"))

        if processing_time_ms is None and job.started_at:
            processing_time_ms = (now - job.started_at).total_seconds() * 1000

        if processing_time_ms is not None:
            pipe = self.redis.pipeline(transaction=True)
            pipe.incrbyfloat(self._metric_key("processing_time_total_ms"), processing_time_ms)
            pipe.incr(self._metric_key("processing_time_count"))
            pipe.execute()

        logger.info("event=eval_job_completed job_id=%s", job_id)

    def fail(self, job_id: str, error: str) -> None:
        """Record job failure and retry or move to DLQ."""
        job = self.get_status(job_id)
        if not job:
            return

        now = datetime.now(tz=timezone.utc)
        sanitized_error = self._sanitize_error(error)
        attempt_count = job.attempt_count + 1

        pipe = self.redis.pipeline(transaction=True)
        pipe.srem(self._active_key(job.model_id), job_id)
        pipe.srem(self._active_global_key(), job_id)
        pipe.hset(
            self._job_key(job_id),
            mapping={
                "attempt_count": attempt_count,
                "updated_at": now.isoformat(),
                "error_message": sanitized_error,
            },
        )

        if attempt_count >= job.max_attempts:
            pipe.hset(
                self._job_key(job_id),
                mapping={
                    "status": EvaluationJobStatus.DEAD.value,
                    "completed_at": now.isoformat(),
                    "next_retry_at": "",
                },
            )
            pipe.lpush(self._dlq_key(), job_id)
            pipe.incr(self._metric_key("dlq"))
            logger.error(
                "event=eval_job_dead job_id=%s attempts=%s",
                job_id,
                attempt_count,
            )
        else:
            delay = self._retry_delay_seconds(attempt_count)
            retry_at = now.timestamp() + delay
            pipe.hset(
                self._job_key(job_id),
                mapping={
                    "status": EvaluationJobStatus.PENDING.value,
                    "next_retry_at": datetime.fromtimestamp(
                        retry_at,
                        tz=timezone.utc,
                    ).isoformat(),
                },
            )
            pipe.zadd(self._delayed_key(), {job_id: retry_at})
            logger.warning(
                "event=eval_job_retry_scheduled job_id=%s attempt=%s retry_in_seconds=%s",
                job_id,
                attempt_count,
                delay,
            )

        pipe.incr(self._metric_key("failed"))
        pipe.execute()

    def get_status(self, job_id: str) -> EvaluationJob | None:
        """Fetch job status and metadata by ID."""
        payload = self.redis.hgetall(self._job_key(job_id))
        if not payload:
            return None
        return EvaluationJob.from_redis_hash(payload)

    def get_queue_depth(self, model_id: str | None = None) -> int:
        """Return number of queued jobs."""
        if model_id:
            queue_count = int(self.redis.zcard(self._queue_key(model_id)))
            delayed_count = self._count_delayed_for_model(model_id)
            return queue_count + delayed_count
        return int(
            self.redis.zcard(self._queue_global_key()) + self.redis.zcard(self._delayed_key())
        )

    def get_active_count(self, model_id: str | None = None) -> int:
        """Return active jobs count."""
        if model_id:
            return int(self.redis.scard(self._active_key(model_id)))
        return int(self.redis.scard(self._active_global_key()))

    def get_dlq_jobs(self, limit: int = 100) -> list[EvaluationJob]:
        """List jobs currently in dead letter queue."""
        ids = [self._decode(job_id) for job_id in self.redis.lrange(self._dlq_key(), 0, limit - 1)]
        jobs: list[EvaluationJob] = []
        for job_id in ids:
            if not job_id:
                continue
            job = self.get_status(job_id)
            if job:
                jobs.append(job)
        return jobs

    def retry_dlq_job(self, job_id: str) -> bool:
        """Move a dead job back into the pending queue."""
        job = self.get_status(job_id)
        if not job or job.status != EvaluationJobStatus.DEAD:
            return False

        now = datetime.now(tz=timezone.utc)
        job.status = EvaluationJobStatus.PENDING
        job.attempt_count = 0
        job.error_message = None
        job.completed_at = None
        job.updated_at = now
        job.next_retry_at = None

        queue_score = self._queue_score(job.priority, now)
        pipe = self.redis.pipeline(transaction=True)
        pipe.lrem(self._dlq_key(), 0, job_id)
        pipe.hset(self._job_key(job_id), mapping=job.to_redis_hash(queue_score))
        pipe.zadd(self._queue_global_key(), {job_id: queue_score})
        pipe.zadd(self._queue_key(job.model_id), {job_id: queue_score})
        pipe.execute()

        logger.info("event=eval_dlq_job_retried job_id=%s", job_id)
        return True

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending job and remove it from queue/delay sets."""
        job = self.get_status(job_id)
        if not job:
            return False
        if job.status not in {EvaluationJobStatus.PENDING, EvaluationJobStatus.FAILED}:
            return False

        now = datetime.now(tz=timezone.utc)
        pipe = self.redis.pipeline(transaction=True)
        pipe.zrem(self._queue_global_key(), job_id)
        pipe.zrem(self._queue_key(job.model_id), job_id)
        pipe.zrem(self._delayed_key(), job_id)
        pipe.hset(
            self._job_key(job_id),
            mapping={
                "status": EvaluationJobStatus.FAILED.value,
                "updated_at": now.isoformat(),
                "completed_at": now.isoformat(),
                "error_message": "Cancelled by user",
            },
        )
        pipe.execute()

        logger.info("event=eval_job_cancelled job_id=%s", job_id)
        return True

    def get_metrics(self) -> dict[str, Any]:
        """Return queue metrics snapshot."""
        completed = int(self.redis.get(self._metric_key("completed")) or 0)
        failed = int(self.redis.get(self._metric_key("failed")) or 0)
        dlq_count = int(self.redis.llen(self._dlq_key()))
        total_ms = float(self.redis.get(self._metric_key("processing_time_total_ms")) or 0)
        total_count = int(self.redis.get(self._metric_key("processing_time_count")) or 0)
        avg_ms = total_ms / total_count if total_count else 0.0

        return {
            "queue_depth": self.get_queue_depth(),
            "active_count": self.get_active_count(),
            "completed_count": completed,
            "failed_count": failed,
            "dlq_count": dlq_count,
            "avg_processing_time_ms": avg_ms,
        }

    def _count_delayed_for_model(self, model_id: str) -> int:
        job_ids = self.redis.zrange(self._delayed_key(), 0, -1)
        count = 0
        for raw_job_id in job_ids:
            job_id = self._decode(raw_job_id)
            if not job_id:
                continue
            model_value = self.redis.hget(self._job_key(job_id), "model_id")
            if self._decode(model_value) == model_id:
                count += 1
        return count

    def _promote_due_retries(self, now_ts: float) -> None:
        due_job_ids = [
            self._decode(item)
            for item in self.redis.zrangebyscore(self._delayed_key(), "-inf", now_ts)
        ]
        for job_id in due_job_ids:
            if not job_id:
                continue
            model_id = self._decode(self.redis.hget(self._job_key(job_id), "model_id"))
            queue_score = self.redis.hget(self._job_key(job_id), "queue_score")
            if not model_id or queue_score is None:
                self.redis.zrem(self._delayed_key(), job_id)
                continue
            queue_score_float = float(self._decode(queue_score) or 0.0)
            pipe = self.redis.pipeline(transaction=True)
            pipe.zadd(self._queue_global_key(), {job_id: queue_score_float})
            pipe.zadd(self._queue_key(model_id), {job_id: queue_score_float})
            pipe.hset(self._job_key(job_id), mapping={"next_retry_at": ""})
            pipe.zrem(self._delayed_key(), job_id)
            pipe.execute()

    def _retry_delay_seconds(self, attempt_count: int) -> int:
        return int(self.config.retry_base_delay_seconds * (2 ** (attempt_count - 1)))

    def _sanitize_error(self, error: str) -> str:
        if not error:
            return "Unknown error"
        return " ".join(error.replace("\n", " ").replace("\r", " ").split())[:1000]

    def _queue_score(self, priority: int, created_at: datetime) -> float:
        base = int(created_at.timestamp() * 1000)
        return float(-(priority * 10_000_000_000_000) + base)

    def _decode(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        if isinstance(value, str):
            return value
        return str(value)

    def _job_key(self, job_id: str) -> str:
        return f"{self.config.key_prefix}:job:{job_id}"

    def _queue_key(self, model_id: str) -> str:
        return f"{self.config.key_prefix}:queue:{model_id}"

    def _queue_global_key(self) -> str:
        return f"{self.config.key_prefix}:queue:global"

    def _active_key(self, model_id: str) -> str:
        return f"{self.config.key_prefix}:active:{model_id}"

    def _active_global_key(self) -> str:
        return f"{self.config.key_prefix}:active:global"

    def _dlq_key(self) -> str:
        return f"{self.config.key_prefix}:dlq"

    def _delayed_key(self) -> str:
        return f"{self.config.key_prefix}:delayed"

    def _metric_key(self, name: str) -> str:
        return f"{self.config.key_prefix}:metrics:{name}"

    def _models_key(self) -> str:
        return f"{self.config.key_prefix}:models"

    def _dequeue_lua(self) -> str:
        return """
local queue_global = KEYS[1]
local delayed = KEYS[2]
local active_global = KEYS[3]
local models_key = KEYS[4]

local now_ts = tonumber(ARGV[1])
local max_per_model = tonumber(ARGV[2])
local max_global = tonumber(ARGV[3])
local target_model = ARGV[4]
local prefix = ARGV[5]
local now_iso = ARGV[6]

if redis.call('SCARD', active_global) >= max_global then
  return nil
end

local due_jobs = redis.call('ZRANGEBYSCORE', delayed, '-inf', now_ts, 'LIMIT', 0, 200)
for _, job_id in ipairs(due_jobs) do
  local job_key = prefix .. ':job:' .. job_id
  local model_id = redis.call('HGET', job_key, 'model_id')
  local queue_score = redis.call('HGET', job_key, 'queue_score')
  if model_id and queue_score then
    redis.call('ZADD', queue_global, queue_score, job_id)
    redis.call('ZADD', prefix .. ':queue:' .. model_id, queue_score, job_id)
    redis.call('HSET', job_key, 'next_retry_at', '')
  end
  redis.call('ZREM', delayed, job_id)
end

local candidates = {}
if target_model and target_model ~= '' then
  candidates = redis.call('ZRANGE', prefix .. ':queue:' .. target_model, 0, 200)
else
  candidates = redis.call('ZRANGE', queue_global, 0, 200)
end

for _, job_id in ipairs(candidates) do
  local job_key = prefix .. ':job:' .. job_id
  local model_id = redis.call('HGET', job_key, 'model_id')
  if model_id then
    local active_model_key = prefix .. ':active:' .. model_id
    local model_active = redis.call('SCARD', active_model_key)
    if model_active < max_per_model then
      redis.call('ZREM', queue_global, job_id)
      redis.call('ZREM', prefix .. ':queue:' .. model_id, job_id)
      redis.call('SADD', active_global, job_id)
      redis.call('SADD', active_model_key, job_id)
      redis.call('HSET', job_key,
        'status', 'active',
        'updated_at', now_iso,
        'started_at', now_iso
      )
      return job_id
    end
  end
end

return nil
"""
