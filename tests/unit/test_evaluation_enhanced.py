"""Unit tests for enhanced model evaluation functionality."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from src.modules.evaluation import ModelEvaluator


@pytest.fixture
def evaluator() -> ModelEvaluator:
    """Create a ModelEvaluator instance for testing."""
    return ModelEvaluator(metrics=["accuracy", "precision", "recall", "f1", "auroc"])


@pytest.fixture
def sample_data() -> tuple[pd.DataFrame, pd.Series]:
    """Create sample test data."""
    np.random.seed(42)
    X_test = pd.DataFrame(
        {
            "feature_1": np.random.randn(100),
            "feature_2": np.random.randn(100),
            "feature_3": np.random.randn(100),
        }
    )
    y_test = pd.Series(np.random.choice([0, 1], size=100))
    return X_test, y_test


@pytest.fixture
def mock_model() -> dict[str, object]:
    """Create a mock model for testing."""
    return {
        "type": "mock_classifier",
        "version": "1.0.0",
        "metrics": {
            "accuracy": 0.85,
            "precision": 0.83,
            "recall": 0.87,
            "f1": 0.85,
            "auroc": 0.91,
        },
    }


@pytest.fixture
def sklearn_mock_model() -> Mock:
    """Create a mock sklearn model for testing."""
    return Mock()


@pytest.fixture
def fake_mlflow() -> Mock:
    """Create a fake MLflow module object."""
    # Production MLflow auth relies on Authorization / MLFLOW_TRACKING_TOKEN env wiring.
    mlflow = Mock()
    mlflow.active_run.return_value = object()
    mlflow.start_run.return_value = nullcontext()
    mlflow.evaluate.return_value = SimpleNamespace(
        metrics={
            "accuracy": 0.84,
            "precision": 0.82,
            "recall": 0.81,
            "f1": 0.815,
            "auroc": 0.9,
        }
    )
    return mlflow


def test_make_metric_wrappers_compute_expected_scores(evaluator: ModelEvaluator) -> None:
    """Metric functions wrapped by make_metric should produce expected values."""
    targets = pd.Series([0, 1, 0, 1])
    predictions = pd.Series([0, 1, 1, 1])

    assert evaluator._compute_accuracy(predictions, targets) == pytest.approx(0.75)
    assert evaluator._compute_precision(predictions, targets) == pytest.approx(0.8333333)
    assert evaluator._compute_recall(predictions, targets) == pytest.approx(0.75)
    assert evaluator._compute_f1(predictions, targets) == pytest.approx(0.7333333)

    auroc = evaluator._compute_auroc(
        predictions,
        targets,
        predicted_probabilities=np.array([[0.8, 0.2], [0.1, 0.9], [0.4, 0.6], [0.2, 0.8]]),
    )
    assert auroc == pytest.approx(1.0)


def test_evaluate_sklearn_model_calls_mlflow_with_extra_metrics(
    evaluator: ModelEvaluator,
    sklearn_mock_model: Mock,
    sample_data: tuple[pd.DataFrame, pd.Series],
    fake_mlflow: Mock,
) -> None:
    """MLflow evaluate is called directly with extra_metrics from make_metric."""
    metric_calls: list[dict[str, object]] = []

    def _make_metric(*, eval_fn, greater_is_better, name, **kwargs):
        metric_calls.append(
            {
                "name": name,
                "eval_fn": eval_fn,
                "greater_is_better": greater_is_better,
                "kwargs": kwargs,
            }
        )
        return SimpleNamespace(name=name)

    evaluator._load_mlflow_evaluation = Mock(return_value=(fake_mlflow, _make_metric))
    X_test, y_test = sample_data

    results = evaluator.evaluate_sklearn_model(sklearn_mock_model, X_test, y_test)

    assert results == {
        "accuracy": 0.84,
        "precision": 0.82,
        "recall": 0.81,
        "f1": 0.815,
        "auroc": 0.9,
    }

    fake_mlflow.evaluate.assert_called_once()
    call_kwargs = fake_mlflow.evaluate.call_args.kwargs
    assert call_kwargs["model"] is sklearn_mock_model
    assert call_kwargs["data"].equals(X_test)
    assert call_kwargs["targets"].equals(y_test)
    assert call_kwargs["model_type"] == "classifier"
    assert len(call_kwargs["extra_metrics"]) == 5

    metric_names = [item["name"] for item in metric_calls]
    assert metric_names == ["accuracy", "precision", "recall", "f1", "auroc"]
    assert all(item["greater_is_better"] is True for item in metric_calls)


def test_evaluate_sklearn_model_creates_run_if_not_active(
    evaluator: ModelEvaluator,
    sklearn_mock_model: Mock,
    sample_data: tuple[pd.DataFrame, pd.Series],
    fake_mlflow: Mock,
) -> None:
    """A new run should be created when there is no active MLflow run."""
    fake_mlflow.active_run.return_value = None
    evaluator._load_mlflow_evaluation = Mock(return_value=(fake_mlflow, Mock()))
    X_test, y_test = sample_data

    _ = evaluator.evaluate_sklearn_model(sklearn_mock_model, X_test, y_test)

    fake_mlflow.start_run.assert_called_once_with()


def test_evaluate_sklearn_model_raises_descriptive_error_when_mlflow_missing(
    evaluator: ModelEvaluator,
    sklearn_mock_model: Mock,
    sample_data: tuple[pd.DataFrame, pd.Series],
) -> None:
    """Missing MLflow dependency should raise a clear ImportError."""
    evaluator._load_mlflow_evaluation = Mock(
        side_effect=ImportError(
            "mlflow is required for model evaluation. Install the mlflow extra/dependency."
        )
    )
    X_test, y_test = sample_data

    with pytest.raises(ImportError, match="mlflow is required"):
        evaluator.evaluate_sklearn_model(sklearn_mock_model, X_test, y_test)


def test_evaluate_model_with_mock(
    evaluator: ModelEvaluator,
    mock_model: dict[str, object],
    sample_data: tuple[pd.DataFrame, pd.Series],
) -> None:
    """Test generic model evaluation with mock model."""
    X_test, y_test = sample_data

    results = evaluator.evaluate_model(mock_model, X_test, y_test)

    assert isinstance(results, dict)
    assert "metrics" in results
    assert "test_samples" in results
    assert "model_type" in results
    assert results["test_samples"] == len(X_test)
    assert results["model_type"] == "mock_classifier"
    assert isinstance(results["metrics"], dict)


def test_compare_models(evaluator: ModelEvaluator) -> None:
    """Test model comparison functionality."""
    baseline_metrics = {
        "accuracy": 0.80,
        "precision": 0.78,
        "recall": 0.82,
        "f1": 0.80,
        "auroc": 0.85,
    }

    new_metrics = {
        "accuracy": 0.85,
        "precision": 0.83,
        "recall": 0.87,
        "f1": 0.85,
        "auroc": 0.91,
    }

    comparison = evaluator.compare_models(baseline_metrics, new_metrics)

    assert isinstance(comparison, dict)

    for metric in evaluator.metrics:
        assert metric in comparison
        comp = comparison[metric]

        assert "baseline" in comp
        assert "new" in comp
        assert "absolute_delta" in comp
        assert "relative_delta" in comp
        assert "improved" in comp

        assert comp["baseline"] == baseline_metrics[metric]
        assert comp["new"] == new_metrics[metric]
        assert comp["absolute_delta"] == new_metrics[metric] - baseline_metrics[metric]
        assert comp["improved"] == (new_metrics[metric] > baseline_metrics[metric])


def test_calculate_delta_score_default_weights(evaluator: ModelEvaluator) -> None:
    """Test delta score calculation with default weights."""
    comparison = {
        "accuracy": {"absolute_delta": 0.05},
        "precision": {"absolute_delta": 0.03},
        "recall": {"absolute_delta": 0.02},
        "f1": {"absolute_delta": 0.04},
        "auroc": {"absolute_delta": 0.06},
    }

    delta_score = evaluator.calculate_delta_score(comparison)

    # With equal weights, should be average of deltas
    expected = (0.05 + 0.03 + 0.02 + 0.04 + 0.06) / 5
    assert delta_score == pytest.approx(expected, rel=1e-6)


def test_create_evaluation_report(evaluator: ModelEvaluator) -> None:
    """Test evaluation report creation."""
    baseline_results = {
        "metrics": {"accuracy": 0.80, "f1": 0.78},
        "model_type": "baseline_model",
        "test_samples": 1000,
    }

    new_results = {
        "metrics": {"accuracy": 0.85, "f1": 0.83},
        "model_type": "new_model",
        "test_samples": 1000,
    }

    comparison = {
        "accuracy": {
            "baseline": 0.80,
            "new": 0.85,
            "absolute_delta": 0.05,
            "relative_delta": 6.25,
            "improved": True,
        },
        "f1": {
            "baseline": 0.78,
            "new": 0.83,
            "absolute_delta": 0.05,
            "relative_delta": 6.41,
            "improved": True,
        },
    }

    delta_score = 0.05

    report = evaluator.create_evaluation_report(
        baseline_results, new_results, comparison, delta_score
    )

    assert isinstance(report, dict)
    assert "baseline_model" in report
    assert "new_model" in report
    assert "comparison" in report
    assert "delta_score" in report
    assert "summary" in report

    summary = report["summary"]
    assert summary["improved_metrics"] == ["accuracy", "f1"]
    assert summary["degraded_metrics"] == []
    assert summary["overall_improvement"] is True
