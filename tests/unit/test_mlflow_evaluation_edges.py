"""Edge-case tests for MLflow evaluation wrappers."""

from __future__ import annotations

# Auth-hook note: this suite patches MLflow imports for local-only behavior tests.
# Production MLflow auth relies on Authorization / MLFLOW_TRACKING_TOKEN env wiring.
import builtins
import math
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.modules.evaluation import ModelEvaluator


def test_load_mlflow_evaluation_imports_mlflow_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mlflow = SimpleNamespace(metrics=SimpleNamespace(make_metric=lambda **_: object()))
    monkeypatch.setitem(__import__("sys").modules, "mlflow", fake_mlflow)
    monkeypatch.setitem(__import__("sys").modules, "mlflow.metrics", fake_mlflow.metrics)

    loaded_mlflow, make_metric = ModelEvaluator._load_mlflow_evaluation()

    assert loaded_mlflow is fake_mlflow
    assert callable(make_metric)


def test_load_mlflow_evaluation_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def _import(name, glb=None, lcl=None, fromlist=(), level=0):  # noqa: ANN001
        if name == "mlflow" or name.startswith("mlflow."):
            raise ImportError("mlflow unavailable")
        return real_import(name, glb, lcl, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)

    with pytest.raises(ImportError, match="mlflow is required"):
        ModelEvaluator._load_mlflow_evaluation()


def test_compute_auroc_returns_nan_without_probabilities() -> None:
    evaluator = ModelEvaluator()
    value = evaluator._compute_auroc(predictions=pd.Series([0, 1]), targets=pd.Series([0, 1]))

    assert math.isnan(value)


def test_compute_auroc_returns_nan_when_roc_auc_raises() -> None:
    evaluator = ModelEvaluator()
    value = evaluator._compute_auroc(
        predictions=pd.Series([0, 0, 0]),
        targets=pd.Series([0, 0, 0]),
        predicted_probabilities=np.array([0.1, 0.2, 0.3]),
    )

    assert math.isnan(value)


def test_create_extra_metrics_skips_unknown_metrics() -> None:
    evaluator = ModelEvaluator(metrics=["accuracy", "unknown"])

    def _make_metric(*, eval_fn, greater_is_better, name):  # noqa: ANN001
        _ = eval_fn, greater_is_better
        return SimpleNamespace(name=name)

    metrics = evaluator._create_extra_metrics(_make_metric)

    assert [metric.name for metric in metrics] == ["accuracy"]


def test_normalize_metric_value_handles_aggregate_results_and_rejects_nan() -> None:
    evaluator = ModelEvaluator()
    aggregate = SimpleNamespace(aggregate_results={"score": 0.77})

    assert evaluator._normalize_metric_value(aggregate) == pytest.approx(0.77)
    assert evaluator._normalize_metric_value(float("nan")) is None


def test_normalize_metric_value_returns_none_for_non_numeric() -> None:
    evaluator = ModelEvaluator()
    assert evaluator._normalize_metric_value({"score": "x"}) is None
