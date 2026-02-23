"""Integration tests for evaluation queue manager with real Redis."""

from __future__ import annotations

import os
import time

import pytest
import redis
from redis.exceptions import RedisError

from src.models.evaluation_job import EvaluationJob, EvaluationJobStatus
from src.services.evaluation_queue import EvaluationQueueConfig, EvaluationQueueManager

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _redis_available() -> bool:
    try:
        redis.Redis.from_url(REDIS_URL).ping()
        return True
    except RedisError:
        return False


pytestmark = pytest.mark.skipif(not _redis_available(), reason="Redis is not available")


class TestEvaluationQueueIntegration:
    """Integration coverage for queue lifecycle."""

    def setup_method(self) -> None:
        self.redis = redis.Redis.from_url(REDIS_URL)
        self.config = EvaluationQueueConfig(
            max_concurrent_per_model=2,
            max_concurrent_global=3,
            retry_base_delay_seconds=1,
            poll_interval_seconds=0.01,
            key_prefix=f"hokusai:eval:v1:test:{int(time.time() * 1000)}",
        )
        self.queue = EvaluationQueueManager(self.redis, self.config)

    def test_full_enqueue_dequeue_complete_flow(self) -> None:
        job = EvaluationJob(model_id="gpt-4", eval_config={"suite": "integration"})
        job_id = self.queue.enqueue(job)

        active = self.queue.dequeue(model_id="gpt-4")
        assert active is not None
        assert active.id == job_id

        self.queue.complete(job_id, {"score": 0.91})
        stored = self.queue.get_status(job_id)

        assert stored is not None
        assert stored.status == EvaluationJobStatus.COMPLETED
        assert stored.result == {"score": 0.91}

    def test_dlq_end_to_end_and_manual_retry(self) -> None:
        job = EvaluationJob(model_id="gpt-4", eval_config={"suite": "dlq"}, max_attempts=1)
        self.queue.enqueue(job)

        active = self.queue.dequeue(model_id="gpt-4")
        assert active is not None

        self.queue.fail(job.id, "fatal")
        dead = self.queue.get_status(job.id)
        assert dead is not None
        assert dead.status == EvaluationJobStatus.DEAD

        dlq_jobs = self.queue.get_dlq_jobs()
        assert [j.id for j in dlq_jobs] == [job.id]

        assert self.queue.retry_dlq_job(job.id) is True
        retried = self.queue.get_status(job.id)
        assert retried is not None
        assert retried.status == EvaluationJobStatus.PENDING
