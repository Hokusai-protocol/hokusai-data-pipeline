"""Unit tests for dataset arrival worker."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from src.services.dataset_arrival_worker import DatasetArrivalWorker


def _make_sqs_message(
    bucket: str = "my-bucket",
    key: str = "datasets/model-a/v1/data.csv",
) -> dict:
    return {
        "MessageId": "msg-001",
        "ReceiptHandle": "receipt-001",
        "Body": json.dumps(
            {
                "Records": [
                    {
                        "eventSource": "aws:s3",
                        "eventName": "ObjectCreated:Put",
                        "s3": {
                            "bucket": {"name": bucket},
                            "object": {"key": key, "size": 512},
                        },
                    }
                ]
            }
        ),
    }


def test_poll_once_processes_and_deletes_message() -> None:
    handler = MagicMock()
    handler.handle_s3_event.return_value = [{"id": "arrival-1"}]

    worker = DatasetArrivalWorker(
        handler=handler,
        queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue",
    )

    msg = _make_sqs_message()
    worker._sqs = MagicMock()
    worker._sqs.receive_message.return_value = {"Messages": [msg]}

    worker._poll_once()

    handler.handle_s3_event.assert_called_once_with(msg["Body"])
    worker._sqs.delete_message.assert_called_once_with(
        QueueUrl="https://sqs.us-east-1.amazonaws.com/123/test-queue",
        ReceiptHandle="receipt-001",
    )


def test_poll_once_no_messages() -> None:
    handler = MagicMock()
    worker = DatasetArrivalWorker(
        handler=handler,
        queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue",
    )
    worker._sqs = MagicMock()
    worker._sqs.receive_message.return_value = {"Messages": []}

    worker._poll_once()

    handler.handle_s3_event.assert_not_called()


def test_poll_once_does_not_delete_on_handler_error() -> None:
    handler = MagicMock()
    handler.handle_s3_event.side_effect = RuntimeError("processing failed")

    worker = DatasetArrivalWorker(
        handler=handler,
        queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue",
    )

    msg = _make_sqs_message()
    worker._sqs = MagicMock()
    worker._sqs.receive_message.return_value = {"Messages": [msg]}

    worker._poll_once()

    worker._sqs.delete_message.assert_not_called()


def test_stop_sets_event() -> None:
    handler = MagicMock()
    worker = DatasetArrivalWorker(
        handler=handler,
        queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue",
    )
    assert not worker._stop_event.is_set()
    worker.stop()
    assert worker._stop_event.is_set()
