"""Unit tests for evaluation worker."""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import Mock

from src.models.evaluation_job import EvaluationJob
from src.services.evaluation_queue import EvaluationQueueConfig
from src.services.evaluation_worker import EvaluationWorker


class TestEvaluationWorker:
    """Behavior tests for EvaluationWorker."""

    def setup_method(self) -> None:
        self.queue = Mock()
        self.queue.config = EvaluationQueueConfig(poll_interval_seconds=0.01)
        self.worker = EvaluationWorker(queue_manager=self.queue, config=self.queue.config)

    def test_processes_job_and_calls_executor(self) -> None:
        job = EvaluationJob(model_id="gpt-4", eval_config={"suite": "a"})

        def executor(incoming: EvaluationJob) -> dict[str, object]:
            return {"job_id": incoming.id, "ok": True}

        self.worker.eval_executor = executor
        self.worker._process_job(job)

        self.queue.complete.assert_called_once()
        self.queue.fail.assert_not_called()

    def test_handles_executor_failure(self) -> None:
        job = EvaluationJob(model_id="gpt-4", eval_config={"suite": "b"})

        def executor(_: EvaluationJob) -> dict[str, object]:
            raise RuntimeError("boom")

        self.worker.eval_executor = executor
        self.worker._process_job(job)

        self.queue.fail.assert_called_once()
        self.queue.complete.assert_not_called()

    def test_enforces_timeout(self) -> None:
        job = EvaluationJob(model_id="gpt-4", eval_config={"suite": "timeout"}, timeout_seconds=1)

        async def executor(_: EvaluationJob) -> dict[str, object]:
            await asyncio.sleep(2)
            return {"ok": True}

        self.worker.eval_executor = executor
        self.worker._process_job(job)

        self.queue.fail.assert_called_once()
        self.queue.complete.assert_not_called()

    def test_graceful_shutdown(self) -> None:
        self.queue.dequeue.return_value = None

        thread = threading.Thread(target=self.worker.start)
        thread.start()
        time.sleep(0.05)
        self.worker.stop()
        thread.join(timeout=2)

        assert not thread.is_alive()
