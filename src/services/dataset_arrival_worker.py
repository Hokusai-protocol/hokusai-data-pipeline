"""Worker process that polls SQS for S3 dataset arrival events."""
# ruff: noqa: ANN101

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from typing import Any

import boto3

from src.services.dataset_arrival_handler import DatasetArrivalHandler

logger = logging.getLogger(__name__)


class DatasetArrivalWorker:
    """Polls an SQS queue for S3 event notifications and delegates to DatasetArrivalHandler."""

    def __init__(
        self,
        handler: DatasetArrivalHandler,
        queue_url: str,
        *,
        region_name: str = "us-east-1",
        wait_time_seconds: int = 20,
        max_messages: int = 10,
        visibility_timeout: int = 120,
    ) -> None:
        self._handler = handler
        self._queue_url = queue_url
        self._wait_time_seconds = wait_time_seconds
        self._max_messages = max_messages
        self._visibility_timeout = visibility_timeout
        self._sqs = boto3.client("sqs", region_name=region_name)
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Run the polling loop until stopped."""
        self._install_signal_handlers()
        logger.info("event=dataset_arrival_worker_started queue_url=%s", self._queue_url)

        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception:
                logger.exception("event=dataset_arrival_worker_poll_error")
                time.sleep(5)

        logger.info("event=dataset_arrival_worker_stopped")

    def stop(self) -> None:
        """Signal the worker to stop."""
        self._stop_event.set()

    def _poll_once(self) -> None:
        response = self._sqs.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=self._max_messages,
            WaitTimeSeconds=self._wait_time_seconds,
            VisibilityTimeout=self._visibility_timeout,
        )

        messages = response.get("Messages", [])
        if not messages:
            return

        for message in messages:
            self._process_message(message)

    def _process_message(self, message: dict[str, Any]) -> None:
        receipt_handle = message["ReceiptHandle"]
        body = message.get("Body", "{}")

        try:
            results = self._handler.handle_s3_event(body)
            logger.info(
                "event=dataset_arrival_message_processed message_id=%s arrivals=%d",
                message.get("MessageId"),
                len(results),
            )
        except Exception:
            logger.exception(
                "event=dataset_arrival_message_failed message_id=%s",
                message.get("MessageId"),
            )
            # Don't delete - let visibility timeout expire for retry
            return

        # Delete message after successful processing
        try:
            self._sqs.delete_message(
                QueueUrl=self._queue_url,
                ReceiptHandle=receipt_handle,
            )
        except Exception:
            logger.exception(
                "event=dataset_arrival_delete_failed message_id=%s",
                message.get("MessageId"),
            )

    def _install_signal_handlers(self) -> None:
        def _handler(signum: int, _frame: Any) -> None:
            logger.info("event=dataset_arrival_worker_signal signal=%s", signum)
            self.stop()

        try:
            signal.signal(signal.SIGTERM, _handler)
            signal.signal(signal.SIGINT, _handler)
        except ValueError:
            logger.debug("Signal handlers not installed (not running in main thread)")


def main() -> None:
    """Entry point for the dataset arrival worker process."""
    logging.basicConfig(level=os.getenv("PIPELINE_LOG_LEVEL", "INFO"))

    queue_url = os.environ.get("DATASET_ARRIVAL_SQS_QUEUE_URL")
    if not queue_url:
        raise ValueError("DATASET_ARRIVAL_SQS_QUEUE_URL environment variable is required")

    region = os.environ.get("AWS_REGION", "us-east-1")
    database_url = os.environ.get("DATABASE_URL")

    # Optional: wire up benchmark spec service and evaluation queue for auto-re-eval
    benchmark_spec_service = None
    evaluation_queue_manager = None

    try:
        from src.api.services.governance.benchmark_specs import BenchmarkSpecService

        benchmark_spec_service = BenchmarkSpecService(database_url=database_url)
    except Exception:
        logger.warning("event=dataset_arrival_no_benchmark_service")

    try:
        import redis as redis_lib

        from src.services.evaluation_queue import EvaluationQueueConfig, EvaluationQueueManager

        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            redis_client = redis_lib.Redis.from_url(redis_url)
            evaluation_queue_manager = EvaluationQueueManager(
                redis_client=redis_client,
                config=EvaluationQueueConfig.from_env(),
            )
    except Exception:
        logger.warning("event=dataset_arrival_no_eval_queue")

    handler = DatasetArrivalHandler(
        database_url=database_url,
        benchmark_spec_service=benchmark_spec_service,
        evaluation_queue_manager=evaluation_queue_manager,
    )

    worker = DatasetArrivalWorker(
        handler=handler,
        queue_url=queue_url,
        region_name=region,
    )
    worker.start()


if __name__ == "__main__":
    main()
