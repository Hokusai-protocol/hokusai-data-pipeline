"""Unit tests for dataset arrival handler."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.services.dataset_arrival_handler import (
    DatasetArrivalHandler,
    extract_model_id_from_key,
    parse_s3_event_message,
)

# --- parse_s3_event_message ---


def _s3_event_body(bucket: str = "my-bucket", key: str = "datasets/model-a/v1/data.csv") -> str:
    return json.dumps(
        {
            "Records": [
                {
                    "eventSource": "aws:s3",
                    "eventName": "ObjectCreated:Put",
                    "eventTime": "2026-03-06T10:00:00.000Z",
                    "s3": {
                        "bucket": {"name": bucket},
                        "object": {"key": key, "size": 1024, "eTag": "abc123"},
                    },
                }
            ]
        }
    )


def _eventbridge_body(
    bucket: str = "my-bucket", key: str = "datasets/model-b/v2/data.parquet"
) -> str:
    return json.dumps(
        {
            "source": "aws.s3",
            "detail-type": "Object Created",
            "time": "2026-03-06T12:00:00Z",
            "detail": {
                "bucket": {"name": bucket},
                "object": {"key": key, "size": 2048, "etag": "def456"},
            },
        }
    )


def test_parse_s3_event_direct() -> None:
    records = parse_s3_event_message(_s3_event_body())
    assert len(records) == 1
    assert records[0]["bucket"] == "my-bucket"
    assert records[0]["key"] == "datasets/model-a/v1/data.csv"
    assert records[0]["size"] == 1024
    assert records[0]["etag"] == "abc123"


def test_parse_eventbridge_event() -> None:
    records = parse_s3_event_message(_eventbridge_body())
    assert len(records) == 1
    assert records[0]["bucket"] == "my-bucket"
    assert records[0]["key"] == "datasets/model-b/v2/data.parquet"
    assert records[0]["size"] == 2048


def test_parse_ignores_delete_events() -> None:
    body = json.dumps(
        {
            "Records": [
                {
                    "eventSource": "aws:s3",
                    "eventName": "ObjectRemoved:Delete",
                    "s3": {
                        "bucket": {"name": "b"},
                        "object": {"key": "k", "size": 0},
                    },
                }
            ]
        }
    )
    assert parse_s3_event_message(body) == []


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_s3_event_message("not-json")


def test_parse_unrelated_event_returns_empty() -> None:
    assert parse_s3_event_message(json.dumps({"foo": "bar"})) == []


# --- extract_model_id_from_key ---


def test_extract_model_id_valid() -> None:
    model_id, version = extract_model_id_from_key("datasets/model-abc/v1234abcd/data.csv")
    assert model_id == "model-abc"
    assert version == "v1234abcd"


def test_extract_model_id_no_match() -> None:
    model_id, version = extract_model_id_from_key("other/path/file.csv")
    assert model_id is None
    assert version is None


def test_extract_model_id_partial_match() -> None:
    model_id, version = extract_model_id_from_key("datasets/model-x/")
    assert model_id is None  # no version segment


# --- DatasetArrivalHandler ---


def _make_handler(
    has_benchmark: bool = True,
    has_eval_queue: bool = False,
) -> DatasetArrivalHandler:
    benchmark_svc = MagicMock()
    if has_benchmark:
        benchmark_svc.get_active_spec_for_model.return_value = {
            "spec_id": "spec-001",
            "metric_name": "accuracy",
            "metric_direction": "higher_is_better",
            "eval_split": "test",
        }
        benchmark_svc.update_spec_fields.return_value = {"spec_id": "spec-001"}
    else:
        benchmark_svc.get_active_spec_for_model.return_value = None

    eval_queue = MagicMock() if has_eval_queue else None

    return DatasetArrivalHandler(
        benchmark_spec_service=benchmark_svc,
        evaluation_queue_manager=eval_queue,
    )


def test_handle_s3_event_creates_arrival() -> None:
    handler = _make_handler()
    results = handler.handle_s3_event(_s3_event_body())

    assert len(results) == 1
    arrival = results[0]
    assert arrival["model_id"] == "model-a"
    assert arrival["dataset_version"] == "v1"
    assert arrival["spec_id"] == "spec-001"
    assert arrival["reeval_triggered"] is False  # no eval queue configured


def test_handle_s3_event_updates_benchmark_spec() -> None:
    handler = _make_handler()
    handler.handle_s3_event(_s3_event_body())

    handler._benchmark_spec_service.update_spec_fields.assert_called_once_with(
        "spec-001",
        {
            "dataset_id": "s3://my-bucket/datasets/model-a/v1/data.csv",
            "dataset_version": "v1",
        },
    )


def test_handle_s3_event_triggers_reeval_when_queue_available() -> None:
    handler = _make_handler(has_eval_queue=True)
    handler._evaluation_queue_manager.enqueue_with_dedup.return_value = "job-123"
    results = handler.handle_s3_event(_s3_event_body())

    assert results[0]["reeval_triggered"] is True
    handler._evaluation_queue_manager.enqueue_with_dedup.assert_called_once()

    call_kwargs = handler._evaluation_queue_manager.enqueue_with_dedup.call_args[1]
    assert call_kwargs["model_id"] == "model-a"
    assert call_kwargs["trigger_source"] == "data_arrival"
    assert call_kwargs["eval_config"]["trigger"] == "dataset_arrival"


def test_handle_s3_event_no_benchmark_spec() -> None:
    handler = _make_handler(has_benchmark=False)
    results = handler.handle_s3_event(_s3_event_body())

    assert len(results) == 1
    assert results[0]["spec_id"] is None
    assert results[0]["reeval_triggered"] is False


def test_handle_s3_event_non_dataset_key_ignored() -> None:
    body = json.dumps(
        {
            "Records": [
                {
                    "eventSource": "aws:s3",
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": "b"},
                        "object": {"key": "models/some-model/weights.bin", "size": 100},
                    },
                }
            ]
        }
    )
    handler = _make_handler()
    results = handler.handle_s3_event(body)
    assert results == []


def test_handle_eventbridge_event() -> None:
    handler = _make_handler()
    results = handler.handle_s3_event(_eventbridge_body())

    assert len(results) == 1
    assert results[0]["model_id"] == "model-b"
    assert results[0]["dataset_version"] == "v2"


def test_list_arrivals_in_memory() -> None:
    handler = _make_handler()
    handler.handle_s3_event(_s3_event_body())
    handler.handle_s3_event(_s3_event_body(key="datasets/model-c/v3/file.csv"))

    all_items = handler.list_arrivals()
    assert len(all_items) == 2

    filtered = handler.list_arrivals(model_id="model-a")
    assert len(filtered) == 1
    assert filtered[0]["model_id"] == "model-a"


def test_list_arrivals_respects_limit() -> None:
    handler = _make_handler()
    for i in range(5):
        handler.handle_s3_event(_s3_event_body(key=f"datasets/model-x/v{i}/data.csv"))

    items = handler.list_arrivals(limit=3)
    assert len(items) == 3


def test_handle_benchmark_service_error_is_recorded() -> None:
    handler = _make_handler()
    handler._benchmark_spec_service.get_active_spec_for_model.side_effect = RuntimeError("db down")

    results = handler.handle_s3_event(_s3_event_body())
    assert len(results) == 1
    assert results[0]["error_message"] == "db down"
    assert results[0]["reeval_triggered"] is False
