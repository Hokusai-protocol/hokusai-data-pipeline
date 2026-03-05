"""Unit tests for benchmark specification service and model immutability."""

from __future__ import annotations

import pytest

from src.api.models.benchmark_spec import _prevent_benchmark_spec_update
from src.api.services.governance.benchmark_specs import (
    BenchmarkSpecConflictError,
    BenchmarkSpecImmutableError,
    BenchmarkSpecService,
)


def test_register_and_list_benchmark_specs() -> None:
    service = BenchmarkSpecService()

    created = service.register_spec(
        model_id="model-a",
        dataset_id="kaggle/mmlu",
        dataset_version="sha256:" + "a" * 64,
        eval_split="test",
        metric_name="accuracy",
        metric_direction="higher_is_better",
        input_schema={"dataset_metadata": {"min_examples": 900}},
        output_schema={"fields": ["prediction"]},
    )

    listed = service.list_specs(model_id="model-a")

    assert created["model_id"] == "model-a"
    assert created["dataset_id"] == "kaggle/mmlu"
    assert len(listed) == 1
    assert listed[0]["spec_id"] == created["spec_id"]


def test_register_rejects_duplicate_model_dataset_version() -> None:
    service = BenchmarkSpecService()

    payload = {
        "model_id": "model-a",
        "dataset_id": "kaggle/mmlu",
        "dataset_version": "sha256:" + "b" * 64,
        "eval_split": "test",
        "metric_name": "accuracy",
        "metric_direction": "higher_is_better",
        "input_schema": {},
        "output_schema": {},
    }
    service.register_spec(**payload)

    with pytest.raises(BenchmarkSpecConflictError):
        service.register_spec(**payload)


def test_service_update_is_immutable() -> None:
    service = BenchmarkSpecService()

    with pytest.raises(BenchmarkSpecImmutableError):
        service.update_spec("spec-123", {"metric_name": "f1_macro"})


def test_register_with_explicit_provider() -> None:
    service = BenchmarkSpecService()

    created = service.register_spec(
        model_id="model-kaggle",
        dataset_id="kaggle/arc",
        dataset_version="sha256:" + "c" * 64,
        eval_split="test",
        metric_name="accuracy",
        metric_direction="higher_is_better",
        input_schema={},
        output_schema={},
        provider="kaggle",
    )

    assert created["provider"] == "kaggle"


def test_register_defaults_provider_to_hokusai() -> None:
    service = BenchmarkSpecService()

    created = service.register_spec(
        model_id="model-default",
        dataset_id="hokusai/test",
        dataset_version="sha256:" + "d" * 64,
        eval_split="test",
        metric_name="accuracy",
        metric_direction="higher_is_better",
        input_schema={},
        output_schema={},
    )

    assert created["provider"] == "hokusai"


def test_register_rejects_invalid_provider() -> None:
    service = BenchmarkSpecService()

    with pytest.raises(ValueError, match="provider must be one of"):
        service.register_spec(
            model_id="model-bad",
            dataset_id="bad/dataset",
            dataset_version="sha256:" + "e" * 64,
            eval_split="test",
            metric_name="accuracy",
            metric_direction="higher_is_better",
            input_schema={},
            output_schema={},
            provider="invalid",
        )


def test_model_update_hook_raises_immutable_error() -> None:
    with pytest.raises(ValueError, match="immutable"):
        _prevent_benchmark_spec_update(None, None, None)
