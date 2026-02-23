"""Integration-style tests for MLflow-backed evaluation workflow."""

from __future__ import annotations

# Auth-hook note: tests use fake MLflow objects and local mocks only; no live
# Authorization header forwarding or MLFLOW_TRACKING_TOKEN exchange is expected.
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

from src.modules.baseline_loader import BaselineModelLoader
from src.modules.evaluation import ModelEvaluator


def test_model_evaluator_calls_mlflow_with_extra_metrics_not_custom_metrics() -> None:
    evaluator = ModelEvaluator(metrics=["accuracy", "f1"])
    model = Mock()
    X_test = pd.DataFrame({"feature": [1, 2, 3, 4]})
    y_test = pd.Series([0, 1, 0, 1])

    fake_mlflow = Mock()
    fake_mlflow.active_run.return_value = object()
    fake_mlflow.start_run.return_value = nullcontext()
    fake_mlflow.evaluate.return_value = SimpleNamespace(metrics={"accuracy": 0.9, "f1": 0.88})

    def _make_metric(*, eval_fn, greater_is_better, name, **kwargs):
        _ = eval_fn, greater_is_better, kwargs
        return SimpleNamespace(name=name)

    evaluator._load_mlflow_evaluation = Mock(return_value=(fake_mlflow, _make_metric))

    results = evaluator.evaluate_sklearn_model(model, X_test, y_test)

    call_kwargs = fake_mlflow.evaluate.call_args.kwargs
    assert "extra_metrics" in call_kwargs
    assert "custom_metrics" not in call_kwargs
    assert [metric.name for metric in call_kwargs["extra_metrics"]] == ["accuracy", "f1"]
    assert results == {"accuracy": 0.9, "f1": 0.88}


def test_model_evaluator_starts_run_when_no_active_run() -> None:
    evaluator = ModelEvaluator(metrics=["accuracy"])
    model = Mock()
    X_test = pd.DataFrame({"feature": [1, 2]})
    y_test = pd.Series([0, 1])

    fake_mlflow = Mock()
    fake_mlflow.active_run.return_value = None
    fake_mlflow.start_run.return_value = nullcontext()
    fake_mlflow.evaluate.return_value = SimpleNamespace(metrics={"accuracy": 1.0})
    evaluator._load_mlflow_evaluation = Mock(return_value=(fake_mlflow, Mock()))

    _ = evaluator.evaluate_sklearn_model(model, X_test, y_test)

    fake_mlflow.start_run.assert_called_once_with()


@patch("src.modules.baseline_loader.MlflowClient")
@patch("src.modules.baseline_loader.mlflow.set_tracking_uri")
def test_baseline_loader_prefers_alias_resolution(
    _mock_set_tracking_uri: Mock,
    mock_client_cls: Mock,
) -> None:
    version = SimpleNamespace(version="7", run_id="run-7", tags={"lifecycle_stage": "production"})
    client = Mock()
    client.get_model_version_by_alias.return_value = version
    mock_client_cls.return_value = client

    loader = BaselineModelLoader(mlflow_tracking_uri="http://mlflow:5000")
    selected = loader._get_latest_production_version("model-a")

    assert selected.version == "7"
    client.get_model_version_by_alias.assert_called_once_with("model-a", "production")
    client.search_model_versions.assert_not_called()
