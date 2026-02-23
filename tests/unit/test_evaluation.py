"""Unit tests for the evaluation module."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from src.modules.evaluation import ModelEvaluator


class TestModelEvaluator:
    """Test suite for ModelEvaluator class."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.evaluator = ModelEvaluator()

        # Create mock model
        self.mock_model = Mock()

        # Create test data
        self.X_test = pd.DataFrame(
            np.array([[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]]),
            columns=["feature1", "feature2"],
        )
        self.y_test = pd.Series(np.array([0, 1, 1, 0, 1]))

        self.metric_factory_calls: list[dict[str, object]] = []

        def _fake_make_metric(*, eval_fn, greater_is_better, name, **kwargs):
            call = {
                "eval_fn": eval_fn,
                "greater_is_better": greater_is_better,
                "name": name,
                "kwargs": kwargs,
            }
            self.metric_factory_calls.append(call)
            return SimpleNamespace(name=name)

        # Production MLflow auth relies on Authorization / MLFLOW_TRACKING_TOKEN env wiring.
        self.fake_mlflow = Mock()
        self.fake_mlflow.active_run.return_value = object()
        self.fake_mlflow.start_run.return_value = nullcontext()
        self.fake_mlflow.evaluate.return_value = SimpleNamespace(
            metrics={
                "accuracy": 1.0,
                "precision": 1.0,
                "recall": 1.0,
                "f1": 1.0,
                "auroc": 0.99,
            }
        )

        self.evaluator._load_mlflow_evaluation = Mock(
            return_value=(self.fake_mlflow, _fake_make_metric)
        )

    def test_evaluator_initialization(self) -> None:
        """Test evaluator initialization."""
        assert self.evaluator.metrics == ["accuracy", "precision", "recall", "f1", "auroc"]

        # Test with custom metrics
        custom_evaluator = ModelEvaluator(metrics=["accuracy", "f1"])
        assert custom_evaluator.metrics == ["accuracy", "f1"]

    def test_evaluate_sklearn_model_uses_mlflow_evaluate(self) -> None:
        """Test sklearn model evaluation via MLflow evaluate API."""
        results = self.evaluator.evaluate_sklearn_model(self.mock_model, self.X_test, self.y_test)

        assert results["accuracy"] == 1.0
        assert results["precision"] == 1.0
        assert results["recall"] == 1.0
        assert results["f1"] == 1.0
        assert results["auroc"] == 0.99

        self.fake_mlflow.evaluate.assert_called_once()
        evaluate_kwargs = self.fake_mlflow.evaluate.call_args.kwargs
        assert evaluate_kwargs["model"] is self.mock_model
        assert evaluate_kwargs["data"].equals(self.X_test)
        assert evaluate_kwargs["targets"].equals(self.y_test)
        assert evaluate_kwargs["model_type"] == "classifier"
        assert len(evaluate_kwargs["extra_metrics"]) == len(self.evaluator.metrics)

        metric_names = [call["name"] for call in self.metric_factory_calls]
        assert metric_names == ["accuracy", "precision", "recall", "f1", "auroc"]

    def test_evaluate_sklearn_model_starts_run_if_none_active(self) -> None:
        """Test evaluator starts a run when there is no active MLflow run."""
        self.fake_mlflow.active_run.return_value = None

        _ = self.evaluator.evaluate_sklearn_model(self.mock_model, self.X_test, self.y_test)

        self.fake_mlflow.start_run.assert_called_once_with()

    def test_evaluate_sklearn_model_sets_auroc_to_none_when_not_available(self) -> None:
        """Test AUROC gracefully degrades when MLflow cannot compute it."""
        self.fake_mlflow.evaluate.return_value = SimpleNamespace(
            metrics={
                "accuracy": 0.9,
                "precision": 0.91,
                "recall": 0.92,
                "f1": 0.93,
                "auroc": float("nan"),
            }
        )

        results = self.evaluator.evaluate_sklearn_model(self.mock_model, self.X_test, self.y_test)

        assert results["auroc"] is None

    def test_evaluate_mock_model(self) -> None:
        """Test mock model evaluation."""
        mock_model = {
            "type": "mock_baseline_model",
            "metrics": {"accuracy": 0.85, "precision": 0.83, "recall": 0.87, "f1": 0.85},
        }

        results = self.evaluator.evaluate_mock_model(mock_model, self.X_test, self.y_test)

        # Results should be close to stored metrics with small variation
        assert 0.83 <= results["accuracy"] <= 0.87
        assert "precision" in results
        assert "recall" in results
        assert "f1" in results

    def test_evaluate_model_general(self) -> None:
        """Test general evaluate_model method."""
        results = self.evaluator.evaluate_model(self.mock_model, self.X_test, self.y_test)

        assert "metrics" in results
        assert "test_samples" in results
        assert "model_type" in results
        assert results["test_samples"] == 5
        assert results["metrics"]["accuracy"] == 1.0

    def test_compare_models(self) -> None:
        """Test model comparison."""
        baseline_metrics = {"accuracy": 0.85, "precision": 0.83, "recall": 0.87, "f1": 0.85}

        new_metrics = {"accuracy": 0.88, "precision": 0.86, "recall": 0.90, "f1": 0.88}

        comparison = self.evaluator.compare_models(baseline_metrics, new_metrics)

        assert "accuracy" in comparison
        assert comparison["accuracy"]["baseline"] == 0.85
        assert comparison["accuracy"]["new"] == 0.88
        assert comparison["accuracy"]["absolute_delta"] == pytest.approx(0.03)
        assert comparison["accuracy"]["improved"] is True

    def test_calculate_delta_score(self) -> None:
        """Test delta score calculation."""
        comparison = {
            "accuracy": {
                "baseline": 0.85,
                "new": 0.88,
                "absolute_delta": 0.03,
                "relative_delta": 3.53,
                "improved": True,
            },
            "f1": {
                "baseline": 0.85,
                "new": 0.87,
                "absolute_delta": 0.02,
                "relative_delta": 2.35,
                "improved": True,
            },
        }

        # Test with equal weights
        delta_score = self.evaluator.calculate_delta_score(comparison)
        assert delta_score == pytest.approx(0.025)  # Average of 0.03 and 0.02

        # Test with custom weights
        weights = {"accuracy": 0.7, "f1": 0.3}
        delta_score = self.evaluator.calculate_delta_score(comparison, weights)
        assert delta_score == pytest.approx(0.027)  # 0.7*0.03 + 0.3*0.02

    def test_create_evaluation_report(self) -> None:
        """Test evaluation report creation."""
        baseline_results = {
            "metrics": {"accuracy": 0.85, "f1": 0.85},
            "model_type": "RandomForest",
            "test_samples": 1000,
        }

        new_results = {
            "metrics": {"accuracy": 0.88, "f1": 0.87},
            "model_type": "XGBoost",
            "test_samples": 1000,
        }

        comparison = {
            "accuracy": {"baseline": 0.85, "new": 0.88, "absolute_delta": 0.03, "improved": True},
            "f1": {"baseline": 0.85, "new": 0.87, "absolute_delta": 0.02, "improved": True},
        }

        report = self.evaluator.create_evaluation_report(
            baseline_results, new_results, comparison, 0.025
        )

        assert "baseline_model" in report
        assert "new_model" in report
        assert "comparison" in report
        assert "delta_score" in report
        assert "summary" in report
        assert report["summary"]["overall_improvement"] is True
        assert len(report["summary"]["improved_metrics"]) == 2

    def test_model_type_detection(self) -> None:
        """Test model type detection in evaluate_model."""
        # Test with mock model
        mock_model = {"type": "mock_model", "metrics": {"accuracy": 0.85}}

        results = self.evaluator.evaluate_model(mock_model, self.X_test, self.y_test)

        assert results["model_type"] == "mock_model"

        # Test with sklearn model
        results = self.evaluator.evaluate_model(self.mock_model, self.X_test, self.y_test)

        assert results["model_type"] == "Mock"
