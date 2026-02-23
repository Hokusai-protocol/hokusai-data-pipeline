"""Integration tests for creating HEM from MLflow run data."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from src.evaluation.manifest import create_hem_from_mlflow_run


def _fake_run() -> SimpleNamespace:
    return SimpleNamespace(
        info=SimpleNamespace(run_id="run-123"),
        data=SimpleNamespace(
            tags={
                "hokusai.model_id": "model-a",
                "hokusai.eval_id": "eval-001",
                "hokusai.primary_metric": "accuracy",
                "hokusai.dataset.id": "dataset-1",
                "hokusai.dataset.hash": "sha256:abc123",
                "hokusai.dataset.num_samples": "42",
                "hokusai.provider": "mlflow_native",
            },
            params={"temperature": "0"},
            metrics={"z_metric": 0.4, "accuracy": 0.95, "f1": 0.91},
        ),
    )


def test_create_hem_from_mlflow_run_sorts_metrics_and_maps_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mlflow = SimpleNamespace(get_run=lambda _run_id: _fake_run())
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    manifest = create_hem_from_mlflow_run("run-123")

    assert manifest.eval_id == "eval-001"
    assert manifest.primary_metric["name"] == "accuracy"
    assert [metric["name"] for metric in manifest.metrics] == ["accuracy", "f1", "z_metric"]
    assert manifest.dataset == {"id": "dataset-1", "hash": "sha256:abc123", "num_samples": 42}


def test_create_hem_from_mlflow_run_allows_eval_id_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _fake_run()
    run.data.tags.pop("hokusai.eval_id")
    fake_mlflow = SimpleNamespace(get_run=lambda _run_id: run)
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    manifest = create_hem_from_mlflow_run("run-123", eval_id="eval-from-arg")

    assert manifest.eval_id == "eval-from-arg"


def test_create_hem_from_mlflow_run_rejects_non_numeric_dataset_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _fake_run()
    run.data.tags["hokusai.dataset.num_samples"] = "many"
    fake_mlflow = SimpleNamespace(get_run=lambda _run_id: run)
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    with pytest.raises(ValueError, match="Invalid dataset sample count"):
        create_hem_from_mlflow_run("run-123")
