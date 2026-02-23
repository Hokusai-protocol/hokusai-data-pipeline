from __future__ import annotations

import builtins
import sys
import types
from contextlib import nullcontext

import pytest

from src.evaluation.manifest import (
    HokusaiEvaluationManifest,
    create_hem_from_mlflow_run,
    log_hem_to_mlflow,
)


class _FakeRun:
    def __init__(self) -> None:
        self.info = types.SimpleNamespace(run_id="run-123")
        self.data = types.SimpleNamespace(
            tags={
                "hokusai.model_id": "model-a",
                "hokusai.eval_id": "eval-001",
                "hokusai.primary_metric": "accuracy",
                "hokusai.dataset.id": "dataset-1",
                "hokusai.dataset.hash": "sha256:abc123",
                "hokusai.dataset.num_samples": "100",
                "hokusai.provider": "mlflow_native",
            },
            params={"temperature": "0.0"},
            metrics={"accuracy": 0.95, "f1": 0.91},
        )


def _base_manifest() -> HokusaiEvaluationManifest:
    return HokusaiEvaluationManifest(
        model_id="model-a",
        eval_id="eval-001",
        dataset={"id": "dataset-1", "hash": "sha256:abc123", "num_samples": 100},
        primary_metric={"name": "accuracy", "value": 0.95, "higher_is_better": True},
        metrics=[{"name": "accuracy", "value": 0.95}],
        mlflow_run_id="run-123",
    )


def test_create_hem_from_mlflow_run_builds_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_mlflow = types.SimpleNamespace(get_run=lambda run_id: _FakeRun())
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    manifest = create_hem_from_mlflow_run("run-123")
    assert manifest.model_id == "model-a"
    assert manifest.eval_id == "eval-001"
    assert manifest.dataset["hash"] == "sha256:abc123"
    assert manifest.primary_metric["name"] == "accuracy"
    assert manifest.mlflow_run_id == "run-123"


def test_create_hem_from_mlflow_run_missing_required_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    run = _FakeRun()
    del run.data.tags["hokusai.dataset.hash"]
    fake_mlflow = types.SimpleNamespace(get_run=lambda run_id: run)
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    with pytest.raises(ValueError, match="dataset hash"):
        create_hem_from_mlflow_run("run-123")


def test_log_hem_to_mlflow_logs_dict_with_default_path(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[dict, str]] = []

    def _log_dict(payload: dict, artifact_file: str) -> None:
        calls.append((payload, artifact_file))

    fake_mlflow = types.SimpleNamespace(log_dict=_log_dict, start_run=lambda run_id: nullcontext())
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    log_hem_to_mlflow(_base_manifest())
    assert len(calls) == 1
    assert calls[0][1] == "hem/manifest.json"
    assert calls[0][0]["model_id"] == "model-a"


def test_log_hem_to_mlflow_uses_run_context_when_run_id_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class _Ctx:
        def __enter__(self) -> _Ctx:
            events.append("enter")
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            events.append("exit")

    def _start_run(run_id: str) -> _Ctx:
        events.append(f"start:{run_id}")
        return _Ctx()

    def _log_dict(payload: dict, artifact_file: str) -> None:
        events.append(f"log:{artifact_file}")

    fake_mlflow = types.SimpleNamespace(log_dict=_log_dict, start_run=_start_run)
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

    log_hem_to_mlflow(_base_manifest(), run_id="run-123")
    assert events == ["start:run-123", "enter", "log:hem/manifest.json", "exit"]


def test_mlflow_functions_raise_descriptive_error_when_mlflow_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "mlflow", raising=False)

    real_import = builtins.__import__

    def _import(name, glb=None, lcl=None, fromlist=(), level=0):  # noqa: ANN001
        if name == "mlflow":
            raise ImportError("mlflow unavailable")
        return real_import(name, glb, lcl, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)

    with pytest.raises(ImportError, match="mlflow is required"):
        create_hem_from_mlflow_run("run-123", eval_id="eval-001", primary_metric_name="accuracy")
