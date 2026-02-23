"""Tests for EvaluationWorker benchmark adapter integration path."""

from __future__ import annotations

from unittest.mock import Mock

from src.evaluation import HokusaiEvaluationManifest
from src.evaluation.adapters.registry import (
    clear_benchmark_adapters,
    register_benchmark_adapter,
    register_default_benchmark_adapters,
)
from src.models.evaluation_job import EvaluationJob
from src.services.evaluation_queue import EvaluationQueueConfig
from src.services.evaluation_worker import EvaluationWorker


class DummyBenchmarkAdapter:
    def run(self, spec, model_fn, seed):  # noqa: ANN001
        prediction = model_fn("ignored")
        return HokusaiEvaluationManifest(
            model_id=spec.model_id or "model-a",
            eval_id=spec.benchmark_id,
            dataset={"id": "dataset", "hash": "sha256:abc", "num_samples": 1},
            primary_metric={"name": "accuracy", "value": 1.0, "higher_is_better": True},
            metrics=[{"name": "accuracy", "value": 1.0, "higher_is_better": True}],
            mlflow_run_id=f"run-{seed}",
            provenance={"provider": "dummy", "parameters": {"prediction": prediction}},
        )


def test_default_executor_uses_registered_benchmark_adapter() -> None:
    clear_benchmark_adapters()
    register_default_benchmark_adapters()
    register_benchmark_adapter("dummy", DummyBenchmarkAdapter())

    queue = Mock()
    queue.config = EvaluationQueueConfig(poll_interval_seconds=0.01)

    worker = EvaluationWorker(
        queue_manager=queue,
        config=queue.config,
        model_fn_resolver=lambda _job: (lambda _input: "yes"),
    )
    job = EvaluationJob(
        model_id="model-a",
        eval_config={
            "adapter_type": "dummy",
            "seed": 123,
            "dry_run": False,
            "benchmark_spec": {
                "benchmark_id": "bench-1",
                "dataset_ref": "owner/data",
                "dataset_version_hash": "hash-v1",
                "eval_split_path": "eval.csv",
                "target_column": "label",
                "metric": {"name": "accuracy", "version": "1"},
            },
        },
    )

    result = worker._default_executor(job)

    assert result["executor"] == "benchmark_adapter"
    assert result["adapter_type"] == "dummy"
    assert result["seed"] == 123
    assert result["manifest"]["eval_id"] == "bench-1"
    assert result["manifest_hash"]
