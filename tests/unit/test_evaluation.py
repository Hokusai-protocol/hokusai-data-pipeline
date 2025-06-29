"""Unit tests for the evaluation module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np
import pandas as pd
from typing import Dict, List, Any
import json

from src.modules.evaluation import ModelEvaluator


class TestModelEvaluator:
    """Test suite for ModelEvaluator class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.evaluator = ModelEvaluator()
        
        # Create mock model
        self.mock_model = Mock()
        self.mock_model.predict = Mock(return_value=np.array([0, 1, 1, 0, 1]))
        self.mock_model.predict_proba = Mock(return_value=np.array([
            [0.9, 0.1],
            [0.2, 0.8],
            [0.3, 0.7],
            [0.8, 0.2],
            [0.1, 0.9]
        ]))
        
        # Create test data
        self.X_test = np.array([[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]])
        self.y_test = np.array([0, 1, 1, 0, 1])
        
    def test_evaluator_initialization(self):
        """Test evaluator initialization."""
        assert self.evaluator.metrics == ["accuracy", "precision", "recall", "f1", "auroc"]
        
        # Test with custom metrics
        custom_evaluator = ModelEvaluator(metrics=["accuracy", "f1"])
        assert custom_evaluator.metrics == ["accuracy", "f1"]
        
    def test_evaluate_sklearn_model(self):
        """Test sklearn model evaluation."""
        # Convert to pandas for consistency
        X_test_df = pd.DataFrame(self.X_test, columns=['feature1', 'feature2'])
        y_test_series = pd.Series(self.y_test)
        
        results = self.evaluator.evaluate_sklearn_model(
            self.mock_model,
            X_test_df,
            y_test_series
        )
        
        assert "accuracy" in results
        assert "precision" in results
        assert "recall" in results
        assert "f1" in results
        assert results["accuracy"] == 1.0  # Perfect predictions
        
    def test_evaluate_model_with_proba(self):
        """Test model evaluation with probability predictions."""
        # Convert to pandas
        X_test_df = pd.DataFrame(self.X_test, columns=['feature1', 'feature2'])
        y_test_series = pd.Series(self.y_test)
        
        results = self.evaluator.evaluate_sklearn_model(
            self.mock_model,
            X_test_df,
            y_test_series
        )
        
        assert "auroc" in results
        assert 0 <= results["auroc"] <= 1
        
    def test_evaluate_mock_model(self):
        """Test mock model evaluation."""
        mock_model = {
            "type": "mock_baseline_model",
            "metrics": {
                "accuracy": 0.85,
                "precision": 0.83,
                "recall": 0.87,
                "f1": 0.85
            }
        }
        
        X_test_df = pd.DataFrame(self.X_test, columns=['feature1', 'feature2'])
        y_test_series = pd.Series(self.y_test)
        
        results = self.evaluator.evaluate_mock_model(
            mock_model,
            X_test_df,
            y_test_series
        )
        
        # Results should be close to stored metrics with small variation
        assert 0.83 <= results["accuracy"] <= 0.87
        assert "precision" in results
        assert "recall" in results
        assert "f1" in results
        
    def test_evaluate_model_general(self):
        """Test general evaluate_model method."""
        X_test_df = pd.DataFrame(self.X_test, columns=['feature1', 'feature2'])
        y_test_series = pd.Series(self.y_test)
        
        # Test with sklearn model
        results = self.evaluator.evaluate_model(
            self.mock_model,
            X_test_df,
            y_test_series
        )
        
        assert "metrics" in results
        assert "test_samples" in results
        assert "model_type" in results
        assert results["test_samples"] == 5
        assert results["metrics"]["accuracy"] == 1.0
        
    def test_compare_models(self):
        """Test model comparison."""
        baseline_metrics = {
            "accuracy": 0.85,
            "precision": 0.83,
            "recall": 0.87,
            "f1": 0.85
        }
        
        new_metrics = {
            "accuracy": 0.88,
            "precision": 0.86,
            "recall": 0.90,
            "f1": 0.88
        }
        
        comparison = self.evaluator.compare_models(baseline_metrics, new_metrics)
        
        assert "accuracy" in comparison
        assert comparison["accuracy"]["baseline"] == 0.85
        assert comparison["accuracy"]["new"] == 0.88
        assert comparison["accuracy"]["absolute_delta"] == pytest.approx(0.03)
        assert comparison["accuracy"]["improved"] is True
        
    def test_calculate_delta_score(self):
        """Test delta score calculation."""
        comparison = {
            "accuracy": {
                "baseline": 0.85,
                "new": 0.88,
                "absolute_delta": 0.03,
                "relative_delta": 3.53,
                "improved": True
            },
            "f1": {
                "baseline": 0.85,
                "new": 0.87,
                "absolute_delta": 0.02,
                "relative_delta": 2.35,
                "improved": True
            }
        }
        
        # Test with equal weights
        delta_score = self.evaluator.calculate_delta_score(comparison)
        assert delta_score == pytest.approx(0.025)  # Average of 0.03 and 0.02
        
        # Test with custom weights
        weights = {"accuracy": 0.7, "f1": 0.3}
        delta_score = self.evaluator.calculate_delta_score(comparison, weights)
        assert delta_score == pytest.approx(0.027)  # 0.7*0.03 + 0.3*0.02
        
    def test_create_evaluation_report(self):
        """Test evaluation report creation."""
        baseline_results = {
            "metrics": {"accuracy": 0.85, "f1": 0.85},
            "model_type": "RandomForest",
            "test_samples": 1000
        }
        
        new_results = {
            "metrics": {"accuracy": 0.88, "f1": 0.87},
            "model_type": "XGBoost",
            "test_samples": 1000
        }
        
        comparison = {
            "accuracy": {
                "baseline": 0.85,
                "new": 0.88,
                "absolute_delta": 0.03,
                "improved": True
            },
            "f1": {
                "baseline": 0.85,
                "new": 0.87,
                "absolute_delta": 0.02,
                "improved": True
            }
        }
        
        report = self.evaluator.create_evaluation_report(
            baseline_results,
            new_results,
            comparison,
            0.025
        )
        
        assert "baseline_model" in report
        assert "new_model" in report
        assert "comparison" in report
        assert "delta_score" in report
        assert "summary" in report
        assert report["summary"]["overall_improvement"] is True
        assert len(report["summary"]["improved_metrics"]) == 2
        
    def test_model_type_detection(self):
        """Test model type detection in evaluate_model."""
        # Test with mock model
        mock_model = {"type": "mock_model", "metrics": {"accuracy": 0.85}}
        X_test_df = pd.DataFrame(self.X_test, columns=['feature1', 'feature2'])
        y_test_series = pd.Series(self.y_test)
        
        results = self.evaluator.evaluate_model(
            mock_model,
            X_test_df,
            y_test_series
        )
        
        assert results["model_type"] == "mock_model"
        
        # Test with sklearn model
        results = self.evaluator.evaluate_model(
            self.mock_model,
            X_test_df,
            y_test_series
        )
        
        assert results["model_type"] == "Mock"