"""Unit tests for evaluation queue manager."""

from __future__ import annotations

import time

import fakeredis

from src.models.evaluation_job import EvaluationJob, EvaluationJobPriority, EvaluationJobStatus
from src.services.evaluation_queue import EvaluationQueueConfig, EvaluationQueueManager


class TestEvaluationQueueManager:
    """Queue behavior tests using fakeredis."""

    def setup_method(self) -> None:
        self.redis = fakeredis.FakeRedis()
        self.config = EvaluationQueueConfig(
            max_concurrent_per_model=1,
            max_concurrent_global=2,
            job_timeout_seconds=1800,
            max_retries=3,
            retry_base_delay_seconds=60,
            poll_interval_seconds=0.01,
        )
        self.queue = EvaluationQueueManager(redis_client=self.redis, config=self.config)

    def test_enqueue_dequeue_respects_priority(self) -> None:
        low = EvaluationJob(model_id="gpt-4", eval_config={"suite": "a"}, priority=1)
        high = EvaluationJob(model_id="gpt-4", eval_config={"suite": "b"}, priority=20)

        self.queue.enqueue(low)
        self.queue.enqueue(high)

        first = self.queue.dequeue(model_id="gpt-4")
        assert first is not None
        assert first.id == high.id

    def test_per_model_concurrency_limit_is_enforced(self) -> None:
        job_a = EvaluationJob(model_id="gpt-4", eval_config={"suite": "a"})
        job_b = EvaluationJob(model_id="gpt-4", eval_config={"suite": "b"})
        self.queue.enqueue(job_a)
        self.queue.enqueue(job_b)

        first = self.queue.dequeue(model_id="gpt-4")
        assert first is not None
        assert self.queue.get_active_count("gpt-4") == 1

        second = self.queue.dequeue(model_id="gpt-4")
        assert second is None

    def test_retry_uses_exponential_backoff(self) -> None:
        job = EvaluationJob(model_id="gpt-4", eval_config={"suite": "retry"})
        self.queue.enqueue(job)
        active = self.queue.dequeue(model_id="gpt-4")
        assert active is not None

        start = time.time()
        self.queue.fail(job.id, "transient failure")

        delayed_key = f"{self.config.key_prefix}:delayed"
        retry_at = self.redis.zscore(delayed_key, job.id)
        assert retry_at is not None
        assert 59 <= (retry_at - start) <= 65

        queued = self.queue.get_status(job.id)
        assert queued is not None
        assert queued.attempt_count == 1
        assert queued.status == EvaluationJobStatus.PENDING

    def test_moves_to_dlq_after_max_attempts(self) -> None:
        job = EvaluationJob(model_id="gpt-4", eval_config={"suite": "dlq"}, max_attempts=2)
        self.queue.enqueue(job)

        first = self.queue.dequeue(model_id="gpt-4")
        assert first is not None
        self.queue.fail(job.id, "first failure")

        delayed_key = f"{self.config.key_prefix}:delayed"
        self.redis.zadd(delayed_key, {job.id: time.time() - 1})

        second = self.queue.dequeue(model_id="gpt-4")
        assert second is not None
        self.queue.fail(job.id, "second failure")

        status = self.queue.get_status(job.id)
        assert status is not None
        assert status.status == EvaluationJobStatus.DEAD

        dlq_jobs = self.queue.get_dlq_jobs()
        assert len(dlq_jobs) == 1
        assert dlq_jobs[0].id == job.id

    def test_status_transitions_pending_active_completed(self) -> None:
        job = EvaluationJob(model_id="gpt-4", eval_config={"suite": "status"})
        self.queue.enqueue(job)

        pending = self.queue.get_status(job.id)
        assert pending is not None
        assert pending.status == EvaluationJobStatus.PENDING

        active = self.queue.dequeue(model_id="gpt-4")
        assert active is not None
        assert active.status == EvaluationJobStatus.ACTIVE

        self.queue.complete(job.id, {"score": 0.99})
        complete = self.queue.get_status(job.id)
        assert complete is not None
        assert complete.status == EvaluationJobStatus.COMPLETED
        assert complete.result == {"score": 0.99}

    def test_cancel_removes_job_from_queue(self) -> None:
        job = EvaluationJob(model_id="gpt-4", eval_config={"suite": "cancel"})
        self.queue.enqueue(job)

        cancelled = self.queue.cancel(job.id)
        assert cancelled is True
        assert self.queue.get_queue_depth("gpt-4") == 0

        cancelled_job = self.queue.get_status(job.id)
        assert cancelled_job is not None
        assert cancelled_job.status == EvaluationJobStatus.FAILED

    def test_retry_dlq_job_requeues_pending(self) -> None:
        job = EvaluationJob(
            model_id="gpt-4",
            eval_config={"suite": "manual_retry"},
            priority=EvaluationJobPriority.HIGH.value,
            max_attempts=1,
        )
        self.queue.enqueue(job)
        active = self.queue.dequeue(model_id="gpt-4")
        assert active is not None

        self.queue.fail(job.id, "dead")
        assert self.queue.retry_dlq_job(job.id) is True

        retry_status = self.queue.get_status(job.id)
        assert retry_status is not None
        assert retry_status.status == EvaluationJobStatus.PENDING
        assert retry_status.attempt_count == 0
        assert self.queue.get_queue_depth("gpt-4") == 1
