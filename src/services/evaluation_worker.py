"""Worker process for consuming and executing evaluation jobs."""
# ruff: noqa: ANN101

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import signal
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

import redis
from redis.exceptions import RedisError

from src.models.evaluation_job import EvaluationJob
from src.services.evaluation_queue import EvaluationQueueConfig, EvaluationQueueManager

logger = logging.getLogger(__name__)


EvalExecutor = Callable[[EvaluationJob], dict[str, Any] | Awaitable[dict[str, Any]]]


class EvaluationWorker:
    """Single-process worker for evaluation queue jobs."""

    def __init__(
        self,
        queue_manager: EvaluationQueueManager,
        eval_executor: EvalExecutor | None = None,
        config: EvaluationQueueConfig | None = None,
    ) -> None:
        """Initialize worker with queue and executor."""
        self.queue_manager = queue_manager
        self.config = config or queue_manager.config
        self.eval_executor = eval_executor or self._default_executor
        self._stop_event = threading.Event()
        self._redis_retry_delay = 1.0

    def start(self) -> None:
        """Run worker loop until stopped."""
        self._install_signal_handlers()
        logger.info("event=eval_worker_started")

        while not self._stop_event.is_set():
            try:
                job = self.queue_manager.dequeue()
                self._redis_retry_delay = 1.0
            except RedisError as exc:
                logger.error("event=eval_worker_redis_error error=%s", str(exc))
                self._sleep_with_backoff()
                continue

            if job is None:
                time.sleep(self.config.poll_interval_seconds)
                continue

            self._process_job(job)

        logger.info("event=eval_worker_stopped")

    def stop(self) -> None:
        """Signal worker loop to shut down."""
        self._stop_event.set()

    def _process_job(self, job: EvaluationJob) -> None:
        """Execute one job with timeout enforcement."""
        start = time.monotonic()
        try:
            result = asyncio.run(
                asyncio.wait_for(self._run_executor(job), timeout=float(job.timeout_seconds))
            )
            elapsed_ms = (time.monotonic() - start) * 1000
            self.queue_manager.complete(job.id, result, processing_time_ms=elapsed_ms)
        except TimeoutError:
            self._handle_timeout(job)
        except Exception as exc:  # noqa: BLE001
            self.queue_manager.fail(job.id, str(exc))
            logger.exception("event=eval_worker_job_failed job_id=%s", job.id)

    def _handle_timeout(self, job: EvaluationJob) -> None:
        """Handle job timeouts as failures."""
        self.queue_manager.fail(job.id, f"Job timed out after {job.timeout_seconds} seconds")
        logger.error("event=eval_worker_job_timeout job_id=%s", job.id)

    async def _run_executor(self, job: EvaluationJob) -> dict[str, Any]:
        maybe_result = self.eval_executor(job)
        if inspect.isawaitable(maybe_result):
            return await cast(Awaitable[dict[str, Any]], maybe_result)
        return cast(dict[str, Any], maybe_result)

    def _install_signal_handlers(self) -> None:
        """Set SIGINT/SIGTERM handlers for graceful shutdown."""

        def _handler(signum: int, _frame: Any) -> None:
            logger.info("event=eval_worker_signal_received signal=%s", signum)
            self.stop()

        try:
            signal.signal(signal.SIGTERM, _handler)
            signal.signal(signal.SIGINT, _handler)
        except ValueError:
            logger.debug("Signal handlers not installed (not running in main thread)")

    def _sleep_with_backoff(self) -> None:
        time.sleep(self._redis_retry_delay)
        self._redis_retry_delay = min(self._redis_retry_delay * 2, 30.0)

    def _default_executor(self, job: EvaluationJob) -> dict[str, Any]:
        """Return the placeholder result for an evaluation job."""
        logger.info("event=eval_worker_mock_execute job_id=%s model_id=%s", job.id, job.model_id)
        return {
            "status": "ok",
            "executor": "placeholder",
            "job_id": job.id,
            "model_id": job.model_id,
            "attempt_count": job.attempt_count,
        }


def _build_redis_client() -> redis.Redis:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.Redis.from_url(redis_url)


def main() -> None:
    """Run the evaluation worker module entrypoint."""
    logging.basicConfig(level=os.getenv("PIPELINE_LOG_LEVEL", "INFO"))
    queue_config = EvaluationQueueConfig.from_env()
    queue_manager = EvaluationQueueManager(redis_client=_build_redis_client(), config=queue_config)
    worker = EvaluationWorker(queue_manager=queue_manager, config=queue_config)
    worker.start()


if __name__ == "__main__":
    main()
