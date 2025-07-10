"""Unit tests for experiment manager service."""

from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pandas as pd
import pytest

from src.services.experiment_manager import ExperimentManager


class TestExperimentManager:
    """Test suite for ExperimentManager class."""

    @patch("mlflow.set_experiment")
    @patch("src.services.experiment_manager.ExperimentManager._ensure_experiment_exists")
    def test_initialization(self, mock_ensure_experiment, mock_set_experiment):
        """Test experiment manager initialization."""
        manager = ExperimentManager("test_experiment")

        assert manager.experiment_name == "test_experiment"
        mock_ensure_experiment.assert_called_once()
        mock_set_experiment.assert_called_once_with("test_experiment")

    def test_valid_metrics(self):
        """Test valid metrics constant."""
        assert "accuracy" in ExperimentManager.VALID_METRICS
        assert "auroc" in ExperimentManager.VALID_METRICS
        assert "f1_score" in ExperimentManager.VALID_METRICS
        assert "precision" in ExperimentManager.VALID_METRICS
        assert "recall" in ExperimentManager.VALID_METRICS

    @patch("mlflow.set_experiment")
    @patch("mlflow.start_run")
    @patch("mlflow.log_params")
    @patch("mlflow.set_tag")
    def test_create_improvement_experiment(
        self, mock_set_tag, mock_log_params, mock_start_run, mock_set_experiment
    ):
        """Test creating improvement experiment."""
        # Mock run context
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_123"
        mock_start_run.return_value.__enter__.return_value = mock_run

        # Mock ensure_experiment_exists
        with patch.object(ExperimentManager, "_ensure_experiment_exists"):
            manager = ExperimentManager()

        # Test data
        contributed_data = {
            "features": [1, 2, 3, 4, 5],
            "metadata": {"dataset_hash": "abc123", "contributor_id": "contributor_001"},
        }

        # Create experiment
        experiment_id = manager.create_improvement_experiment(
            "baseline_model_001", contributed_data
        )

        assert experiment_id == "test_run_123"

        # Check parameters logged
        mock_log_params.assert_called_once()
        logged_params = mock_log_params.call_args[0][0]
        assert logged_params["baseline_model_id"] == "baseline_model_001"
        assert logged_params["contributed_data_hash"] == "abc123"
        assert logged_params["contributed_data_size"] == "5"
        assert logged_params["experiment_type"] == "model_improvement"

        # Check tags set
        assert mock_set_tag.call_count == 3
        mock_set_tag.assert_any_call("experiment_type", "model_improvement")
        mock_set_tag.assert_any_call("baseline_model", "baseline_model_001")
        mock_set_tag.assert_any_call("contributor_id", "contributor_001")

    @patch("mlflow.set_experiment")
    @patch("mlflow.start_run")
    def test_create_experiment_error_handling(self, mock_start_run, mock_set_experiment):
        """Test error handling in experiment creation."""
        # Mock exception
        mock_start_run.side_effect = Exception("MLflow error")

        with patch.object(ExperimentManager, "_ensure_experiment_exists"):
            manager = ExperimentManager()

        with pytest.raises(Exception, match="MLflow error"):
            manager.create_improvement_experiment("baseline_001", {})

    @patch("mlflow.set_experiment")
    @patch("mlflow.pyfunc.load_model")
    def test_compare_models(self, mock_load_model, mock_set_experiment):
        """Test model comparison."""
        # Mock models
        mock_baseline = Mock()
        mock_candidate = Mock()

        # Mock predictions
        y_true = np.array([0, 1, 1, 0, 1, 0, 1, 1, 0, 1])
        baseline_pred = np.array([0, 1, 0, 0, 1, 0, 1, 1, 0, 1])  # 9/10 correct
        candidate_pred = np.array([0, 1, 1, 0, 0, 1, 1, 1, 0, 1])  # 8/10 correct

        mock_baseline.predict.return_value = baseline_pred
        mock_candidate.predict.return_value = candidate_pred

        mock_load_model.side_effect = [mock_baseline, mock_candidate]

        with patch.object(ExperimentManager, "_ensure_experiment_exists"):
            manager = ExperimentManager()

        # Test data
        test_data = {"features": np.random.randn(10, 5), "labels": y_true}

        # Compare models
        result = manager.compare_models("baseline_model_001", "candidate_model_002", test_data)

        assert result["baseline_id"] == "baseline_model_001"
        assert result["candidate_id"] == "candidate_model_002"
        assert "baseline_metrics" in result
        assert "candidate_metrics" in result
        assert "comparison" in result

        # Check metrics
        assert result["baseline_metrics"]["accuracy"] == 0.9
        assert result["candidate_metrics"]["accuracy"] == 0.8
        assert abs(result["comparison"]["accuracy"]["delta"] - (-0.1)) < 0.0001
        assert result["comparison"]["accuracy"]["improved"] == False

    @patch("mlflow.set_experiment")
    def test_get_experiment_history(self, mock_set_experiment):
        """Test getting experiment history."""
        with patch.object(ExperimentManager, "_ensure_experiment_exists"):
            manager = ExperimentManager()

        # Mock search runs
        mock_runs = pd.DataFrame(
            [
                {
                    "run_id": "run1",
                    "params.baseline_model_id": "model1",
                    "metrics.accuracy": 0.85,
                    "metrics.accuracy_improvement": 0.02,
                    "tags.experiment_type": "model_improvement",
                    "tags.recommendation": "ACCEPT",
                    "status": "FINISHED",
                    "start_time": pd.Timestamp("2024-01-01 10:00:00"),
                },
                {
                    "run_id": "run2",
                    "params.baseline_model_id": "model1",
                    "metrics.accuracy": 0.87,
                    "metrics.accuracy_improvement": 0.04,
                    "tags.experiment_type": "model_improvement",
                    "tags.recommendation": "ACCEPT",
                    "status": "FINISHED",
                    "start_time": pd.Timestamp("2024-01-02 10:00:00"),
                },
            ]
        )

        with patch("mlflow.search_runs", return_value=mock_runs):
            history = manager.get_experiment_history("model1")

        assert len(history) == 2
        assert history[0]["run_id"] == "run1"
        assert history[0]["baseline_model"] == "model1"
        assert history[0]["improvement"] == 0.02
        assert history[0]["recommendation"] == "ACCEPT"
        assert history[0]["timestamp"] == pd.Timestamp("2024-01-01 10:00:00")

    @patch("mlflow.set_experiment")
    def test_generate_recommendation(self, mock_set_experiment):
        """Test recommendation generation."""
        with patch.object(ExperimentManager, "_ensure_experiment_exists"):
            manager = ExperimentManager()

        # Test data - candidate is better
        comparison_results = {
            "baseline_metrics": {"accuracy": 0.85, "f1_score": 0.83, "auroc": 0.87},
            "candidate_metrics": {"accuracy": 0.88, "f1_score": 0.86, "auroc": 0.90},
            "comparison": {
                "accuracy": {"delta": 0.03, "improved": True},
                "f1_score": {"delta": 0.03, "improved": True},
                "auroc": {"delta": 0.03, "improved": True},
            },
        }

        rec = manager.generate_recommendation(comparison_results)

        assert rec["should_deploy"] is True
        assert rec["confidence"] == "high"
        assert "All metrics improved" in rec["reasoning"]
        assert rec["improvements_count"] == 3
        assert rec["regressions_count"] == 0

    @patch("mlflow.set_experiment")
    def test_generate_recommendation_no_improvement(self, mock_set_experiment):
        """Test recommendation when no improvement."""
        with patch.object(ExperimentManager, "_ensure_experiment_exists"):
            manager = ExperimentManager()

        # Test data - candidate is worse
        comparison_results = {
            "baseline_metrics": {"accuracy": 0.88, "f1_score": 0.86},
            "candidate_metrics": {"accuracy": 0.85, "f1_score": 0.83},
            "comparison": {
                "accuracy": {"delta": -0.03, "improved": False},
                "f1_score": {"delta": -0.03, "improved": False},
            },
        }

        rec = manager.generate_recommendation(comparison_results)

        assert rec["should_deploy"] is False
        assert rec["confidence"] == "high"
        assert "metric regressions" in rec["reasoning"]
        assert rec["improvements_count"] == 0
        assert rec["regressions_count"] == 2

    @patch("mlflow.set_experiment")
    def test_generate_recommendation_mixed_results(self, mock_set_experiment):
        """Test recommendation with mixed results."""
        with patch.object(ExperimentManager, "_ensure_experiment_exists"):
            manager = ExperimentManager()

        # Test data - mixed results
        comparison_results = {
            "baseline_metrics": {"accuracy": 0.85, "f1_score": 0.86, "auroc": 0.87},
            "candidate_metrics": {
                "accuracy": 0.88,  # Better
                "f1_score": 0.84,  # Worse
                "auroc": 0.87,  # Same
            },
            "comparison": {
                "accuracy": {"delta": 0.03, "improved": True},
                "f1_score": {"delta": -0.02, "improved": False},
                "auroc": {"delta": 0.0, "improved": False},
            },
        }

        rec = manager.generate_recommendation(comparison_results)

        assert rec["should_deploy"] is False  # Conservative approach
        assert rec["confidence"] == "high"  # High confidence because there's a regression
        assert "metric regressions" in rec["reasoning"]
        assert rec["improvements_count"] == 1
        assert rec["regressions_count"] == 1

    @patch("mlflow.create_experiment")
    @patch("mlflow.get_experiment_by_name")
    def test_ensure_experiment_exists(self, mock_get_experiment, mock_create_experiment):
        """Test ensuring experiment exists."""
        # Experiment doesn't exist
        mock_get_experiment.return_value = None
        mock_create_experiment.return_value = "exp_123"

        ExperimentManager("new_experiment")

        mock_get_experiment.assert_called_with("new_experiment")
        mock_create_experiment.assert_called_once_with("new_experiment")

    @patch("mlflow.create_experiment")
    @patch("mlflow.get_experiment_by_name")
    def test_ensure_experiment_exists_already_exists(self, mock_get_experiment, mock_create_experiment):
        """Test when experiment already exists."""
        # Experiment exists
        mock_experiment = Mock()
        mock_experiment.experiment_id = "existing_123"
        mock_get_experiment.return_value = mock_experiment

        ExperimentManager("existing_experiment")

        mock_get_experiment.assert_called_with("existing_experiment")
        mock_create_experiment.assert_not_called()
