"""End-to-end queue processing tests for evaluation worker flow."""

from __future__ import annotations

from threading import Thread

import fakeredis

from src.models.evaluation_job import EvaluationJob, EvaluationJobStatus
from src.services.evaluation_queue import EvaluationQueueConfig, EvaluationQueueManager
from src.services.evaluation_worker import EvaluationWorker


def test_queue_processing_completes_job_in_worker_loop() -> None:
    redis_client = fakeredis.FakeRedis()
    config = EvaluationQueueConfig(poll_interval_seconds=0.01)
    queue = EvaluationQueueManager(redis_client=redis_client, config=config)

    job = EvaluationJob(model_id="model-a", eval_config={"suite": "smoke"})
    queue.enqueue(job)

    def _executor(enqueued_job: EvaluationJob) -> dict[str, object]:
        return {"ok": True, "job_id": enqueued_job.id}

    worker = EvaluationWorker(queue_manager=queue, eval_executor=_executor, config=config)

    thread = Thread(target=worker.start)
    thread.start()

    for _ in range(200):
        status = queue.get_status(job.id)
        if status and status.status == EvaluationJobStatus.COMPLETED:
            break
    worker.stop()
    thread.join(timeout=2)

    final_status = queue.get_status(job.id)
    assert final_status is not None
    assert final_status.status == EvaluationJobStatus.COMPLETED
    assert final_status.result == {"ok": True, "job_id": job.id}


def test_queue_processing_marks_job_dead_after_retries() -> None:
    redis_client = fakeredis.FakeRedis()
    config = EvaluationQueueConfig(
        max_retries=1,
        retry_base_delay_seconds=0,
        poll_interval_seconds=0.01,
    )
    queue = EvaluationQueueManager(redis_client=redis_client, config=config)

    job = EvaluationJob(model_id="model-a", eval_config={"suite": "failure"}, max_attempts=1)
    queue.enqueue(job)

    def _failing_executor(_job: EvaluationJob) -> dict[str, object]:
        raise RuntimeError("boom")

    worker = EvaluationWorker(queue_manager=queue, eval_executor=_failing_executor, config=config)

    thread = Thread(target=worker.start)
    thread.start()

    for _ in range(200):
        status = queue.get_status(job.id)
        if status and status.status == EvaluationJobStatus.DEAD:
            break
    worker.stop()
    thread.join(timeout=2)

    final_status = queue.get_status(job.id)
    assert final_status is not None
    assert final_status.status == EvaluationJobStatus.DEAD
    assert "boom" in (final_status.error_message or "")
