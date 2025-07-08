"""Unit tests for enhanced model evaluation functionality."""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch
from src.modules.evaluation import ModelEvaluator


class TestModelEvaluator:
    """Test cases for the ModelEvaluator class."""

    @pytest.fixture
    def evaluator(self):
        """Create a ModelEvaluator instance for testing."""
        return ModelEvaluator(metrics=["accuracy", "precision", "recall", "f1", "auroc"])

    @pytest.fixture
    def sample_data(self):
        """Create sample test data."""
        np.random.seed(42)
        X_test = pd.DataFrame({
            "feature_1": np.random.randn(100),
            "feature_2": np.random.randn(100),
            "feature_3": np.random.randn(100)
        })
        y_test = pd.Series(np.random.choice([0, 1], size=100))
        return X_test, y_test

    @pytest.fixture
    def mock_model(self):
        """Create a mock model for testing."""
        return {
            "type": "mock_classifier",
            "version": "1.0.0",
            "metrics": {
                "accuracy": 0.85,
                "precision": 0.83,
                "recall": 0.87,
                "f1": 0.85,
                "auroc": 0.91
            }
        }

    @pytest.fixture
    def sklearn_mock_model(self):
        """Create a mock sklearn model for testing."""
        model = Mock()
        model.predict.return_value = np.array([0, 1, 0, 1] * 25)
        model.predict_proba.return_value = np.array([[0.7, 0.3], [0.2, 0.8]] * 50)
        model.classes_ = np.array([0, 1])
        return model

    def test_init(self):
        """Test ModelEvaluator initialization."""
        evaluator = ModelEvaluator()
        assert evaluator.metrics == ["accuracy", "precision", "recall", "f1", "auroc"]

        custom_metrics = ["accuracy", "f1"]
        evaluator = ModelEvaluator(metrics=custom_metrics)
        assert evaluator.metrics == custom_metrics

    def test_evaluate_mock_model(self, evaluator, mock_model, sample_data):
        """Test evaluation of mock models."""
        X_test, y_test = sample_data

        with patch("numpy.random.uniform") as mock_uniform:
            mock_uniform.return_value = 0.01  # Fixed variation for testing

            results = evaluator.evaluate_mock_model(mock_model, X_test, y_test)

            assert isinstance(results, dict)
            assert "accuracy" in results
            assert "precision" in results
            assert "recall" in results
            assert "f1" in results
            assert "auroc" in results

            # Check that values are modified from original with variation
            assert results["accuracy"] == pytest.approx(0.86, rel=1e-2)  # 0.85 + 0.01
            assert 0 <= results["accuracy"] <= 1

    def test_evaluate_sklearn_model(self, evaluator, sklearn_mock_model, sample_data):
        """Test evaluation of sklearn models."""
        X_test, y_test = sample_data

        results = evaluator.evaluate_sklearn_model(sklearn_mock_model, X_test, y_test)

        assert isinstance(results, dict)
        assert "accuracy" in results
        assert "precision" in results
        assert "recall" in results
        assert "f1" in results
        assert "auroc" in results

        # Verify model methods were called
        sklearn_mock_model.predict.assert_called_once_with(X_test)
        sklearn_mock_model.predict_proba.assert_called_once_with(X_test)

        # Check that all metric values are valid
        for metric_value in results.values():
            if metric_value is not None:
                assert 0 <= metric_value <= 1

    def test_evaluate_model_with_mock(self, evaluator, mock_model, sample_data):
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

    def test_evaluate_model_with_sklearn(self, evaluator, sklearn_mock_model, sample_data):
        """Test generic model evaluation with sklearn model."""
        X_test, y_test = sample_data

        results = evaluator.evaluate_model(sklearn_mock_model, X_test, y_test)

        assert isinstance(results, dict)
        assert "metrics" in results
        assert "test_samples" in results
        assert "model_type" in results

        assert results["test_samples"] == len(X_test)
        assert results["model_type"] == "Mock"
        assert isinstance(results["metrics"], dict)

    def test_compare_models(self, evaluator):
        """Test model comparison functionality."""
        baseline_metrics = {
            "accuracy": 0.80,
            "precision": 0.78,
            "recall": 0.82,
            "f1": 0.80,
            "auroc": 0.85
        }

        new_metrics = {
            "accuracy": 0.85,
            "precision": 0.83,
            "recall": 0.87,
            "f1": 0.85,
            "auroc": 0.91
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

    def test_calculate_delta_score_default_weights(self, evaluator):
        """Test delta score calculation with default weights."""
        comparison = {
            "accuracy": {"absolute_delta": 0.05},
            "precision": {"absolute_delta": 0.03},
            "recall": {"absolute_delta": 0.02},
            "f1": {"absolute_delta": 0.04},
            "auroc": {"absolute_delta": 0.06}
        }

        delta_score = evaluator.calculate_delta_score(comparison)

        # With equal weights, should be average of deltas
        expected = (0.05 + 0.03 + 0.02 + 0.04 + 0.06) / 5
        assert delta_score == pytest.approx(expected, rel=1e-6)

    def test_calculate_delta_score_custom_weights(self, evaluator):
        """Test delta score calculation with custom weights."""
        comparison = {
            "accuracy": {"absolute_delta": 0.05},
            "precision": {"absolute_delta": 0.03},
            "recall": {"absolute_delta": 0.02}
        }

        weights = {"accuracy": 0.5, "precision": 0.3, "recall": 0.2}
        delta_score = evaluator.calculate_delta_score(comparison, weights)

        # Weighted calculation
        expected = (0.05 * 0.5) + (0.03 * 0.3) + (0.02 * 0.2)
        assert delta_score == pytest.approx(expected, rel=1e-6)

    def test_create_evaluation_report(self, evaluator):
        """Test evaluation report creation."""
        baseline_results = {
            "metrics": {"accuracy": 0.80, "f1": 0.78},
            "model_type": "baseline_model",
            "test_samples": 1000
        }

        new_results = {
            "metrics": {"accuracy": 0.85, "f1": 0.83},
            "model_type": "new_model",
            "test_samples": 1000
        }

        comparison = {
            "accuracy": {
                "baseline": 0.80,
                "new": 0.85,
                "absolute_delta": 0.05,
                "relative_delta": 6.25,
                "improved": True
            },
            "f1": {
                "baseline": 0.78,
                "new": 0.83,
                "absolute_delta": 0.05,
                "relative_delta": 6.41,
                "improved": True
            }
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

        # Check summary
        summary = report["summary"]
        assert "improved_metrics" in summary
        assert "degraded_metrics" in summary
        assert "overall_improvement" in summary

        assert summary["improved_metrics"] == ["accuracy", "f1"]
        assert summary["degraded_metrics"] == []
        assert summary["overall_improvement"] is True

    def test_sklearn_model_without_proba(self, evaluator, sample_data):
        """Test sklearn model evaluation without predict_proba method."""
        X_test, y_test = sample_data

        model = Mock()
        model.predict.return_value = np.array([0, 1, 0, 1] * 25)
        # Model doesn't have predict_proba
        del model.predict_proba

        results = evaluator.evaluate_sklearn_model(model, X_test, y_test)

        assert "accuracy" in results
        assert "precision" in results
        assert "recall" in results
        assert "f1" in results
        # AUROC should not be calculated without probabilities
        assert "auroc" not in results or results["auroc"] is None

    def test_metrics_subset(self, sample_data):
        """Test evaluator with subset of metrics."""
        X_test, y_test = sample_data
        evaluator = ModelEvaluator(metrics=["accuracy", "f1"])

        mock_model = {
            "type": "mock_classifier",
            "metrics": {"accuracy": 0.85, "f1": 0.83, "precision": 0.80}
        }

        results = evaluator.evaluate_mock_model(mock_model, X_test, y_test)

        # Should only contain requested metrics
        assert "accuracy" in results
        assert "f1" in results
        assert "precision" not in results  # Not in evaluator.metrics
        assert "recall" not in results
        assert "auroc" not in results


class TestEvaluationIntegration:
    """Integration tests for evaluation functionality."""

    def test_full_evaluation_workflow(self):
        """Test complete evaluation workflow."""
        # Create evaluator
        evaluator = ModelEvaluator()

        # Create test data
        np.random.seed(42)
        X_test = pd.DataFrame({
            "feature_1": np.random.randn(100),
            "feature_2": np.random.randn(100)
        })
        y_test = pd.Series(np.random.choice([0, 1], size=100))

        # Create mock models
        baseline_model = {
            "type": "mock_baseline",
            "metrics": {
                "accuracy": 0.80,
                "precision": 0.78,
                "recall": 0.82,
                "f1": 0.80,
                "auroc": 0.85
            }
        }

        new_model = {
            "type": "mock_new_model",
            "metrics": {
                "accuracy": 0.85,
                "precision": 0.83,
                "recall": 0.87,
                "f1": 0.85,
                "auroc": 0.91
            }
        }

        # Evaluate both models
        baseline_results = evaluator.evaluate_model(baseline_model, X_test, y_test)
        new_results = evaluator.evaluate_model(new_model, X_test, y_test)

        # Compare models
        comparison = evaluator.compare_models(
            baseline_results["metrics"],
            new_results["metrics"]
        )

        # Calculate delta score
        delta_score = evaluator.calculate_delta_score(comparison)

        # Create report
        report = evaluator.create_evaluation_report(
            baseline_results, new_results, comparison, delta_score
        )

        # Verify results
        assert report["delta_score"] > 0  # New model should be better
        assert report["summary"]["overall_improvement"] is True
        assert len(report["summary"]["improved_metrics"]) > 0

        # Verify all metrics are present
        for metric in evaluator.metrics:
            assert metric in comparison
            assert comparison[metric]["improved"] is True  # All metrics should improve
