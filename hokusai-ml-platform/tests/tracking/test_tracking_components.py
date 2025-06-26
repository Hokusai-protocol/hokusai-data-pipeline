"""Tests for tracking module components."""
import pytest
from unittest.mock import MagicMock, patch
import numpy as np
from datetime import datetime


class TestExperimentManager:
    """Test suite for ExperimentManager class."""
    
    @patch('mlflow.set_experiment')
    @patch('mlflow.get_experiment_by_name')
    def test_init(self, mock_get_experiment, mock_set_experiment):
        """Test ExperimentManager initialization."""
        from hokusai.tracking.experiments import ExperimentManager
        
        mock_get_experiment.return_value = None
        
        manager = ExperimentManager(experiment_name="test_experiment")
        
        assert manager.experiment_name == "test_experiment"
        mock_set_experiment.assert_called_with("test_experiment")
    
    @patch('mlflow.start_run')
    @patch('mlflow.log_params')
    @patch('mlflow.set_tag')
    def test_create_improvement_experiment(self, mock_set_tag, mock_log_params, mock_start_run):
        """Test creating an improvement experiment."""
        from hokusai.tracking.experiments import ExperimentManager
        
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value.__enter__.return_value = mock_run
        
        manager = ExperimentManager()
        contributed_data = {
            "features": [1, 2, 3],
            "metadata": {
                "dataset_hash": "test_hash",
                "contributor_id": "test_contributor"
            }
        }
        
        experiment_id = manager.create_improvement_experiment(
            baseline_model_id="baseline_123",
            contributed_data=contributed_data
        )
        
        assert experiment_id == "test_run_id"
        mock_log_params.assert_called_once()
        assert mock_set_tag.call_count >= 2
    
    @patch('mlflow.pyfunc.load_model')
    @patch('mlflow.start_run')
    def test_compare_models(self, mock_start_run, mock_load_model):
        """Test model comparison functionality."""
        from hokusai.tracking.experiments import ExperimentManager
        
        # Mock models
        baseline_model = MagicMock()
        baseline_model.predict.return_value = np.array([0, 1, 0, 1])
        
        candidate_model = MagicMock()
        candidate_model.predict.return_value = np.array([0, 1, 1, 1])
        
        mock_load_model.side_effect = [baseline_model, candidate_model]
        
        manager = ExperimentManager()
        test_data = {
            "features": np.array([[1, 2], [3, 4], [5, 6], [7, 8]]),
            "labels": np.array([0, 1, 1, 1]),
            "dataset_name": "test_dataset"
        }
        
        result = manager.compare_models(
            baseline_id="baseline_123",
            candidate_id="candidate_456",
            test_data=test_data
        )
        
        assert "baseline_metrics" in result
        assert "candidate_metrics" in result
        assert "improvements" in result
        assert "recommendation" in result
        assert result["test_dataset"] == "test_dataset"
    
    @patch('mlflow.search_runs')
    def test_get_experiment_history(self, mock_search_runs):
        """Test getting experiment history."""
        from hokusai.tracking.experiments import ExperimentManager
        
        import pandas as pd
        mock_runs = pd.DataFrame([
            {
                "run_id": "run1",
                "params.baseline_model_id": "model1",
                "metrics.accuracy_improvement": 0.05,
                "tags.recommendation": "ACCEPT",
                "start_time": datetime.now()
            }
        ])
        mock_search_runs.return_value = mock_runs
        
        manager = ExperimentManager()
        history = manager.get_experiment_history(baseline_model_id="model1")
        
        assert len(history) == 1
        assert history[0]["run_id"] == "run1"
        assert history[0]["improvement"] == 0.05


class TestPerformanceTracker:
    """Test suite for PerformanceTracker class."""
    
    def test_init(self):
        """Test PerformanceTracker initialization."""
        from hokusai.tracking.performance import PerformanceTracker
        
        tracker = PerformanceTracker()
        assert tracker is not None
    
    @patch('mlflow.log_metrics')
    @patch('mlflow.log_dict')
    @patch('mlflow.log_params')
    def test_track_improvement(self, mock_log_params, mock_log_dict, mock_log_metrics):
        """Test tracking performance improvements."""
        from hokusai.tracking.performance import PerformanceTracker
        
        tracker = PerformanceTracker()
        
        baseline_metrics = {
            "accuracy": 0.85,
            "f1_score": 0.82
        }
        
        improved_metrics = {
            "accuracy": 0.88,
            "f1_score": 0.85
        }
        
        data_contribution = {
            "contributor_id": "test_contributor",
            "contributor_address": "0x123",
            "dataset_hash": "test_hash",
            "data_size": 1000,
            "data_quality_score": 0.9
        }
        
        delta, attestation = tracker.track_improvement(
            baseline_metrics=baseline_metrics,
            improved_metrics=improved_metrics,
            data_contribution=data_contribution
        )
        
        assert delta["accuracy"] == pytest.approx(0.03, abs=1e-6)
        assert delta["f1_score"] == pytest.approx(0.03, abs=1e-6)
        
        assert "version" in attestation
        assert "timestamp" in attestation
        assert "delta_metrics" in attestation
        assert "contributor_info" in attestation
        assert "data_contribution" in attestation
        assert "deltaone_value" in attestation
        assert "attestation_hash" in attestation
    
    def test_calculate_delta(self):
        """Test delta calculation between metrics."""
        from hokusai.tracking.performance import PerformanceTracker
        
        tracker = PerformanceTracker()
        
        baseline = {"accuracy": 0.80, "recall": 0.75}
        improved = {"accuracy": 0.85, "recall": 0.78}
        
        delta = tracker._calculate_delta(baseline, improved)
        
        assert delta["accuracy"] == pytest.approx(0.05, abs=1e-6)
        assert delta["recall"] == pytest.approx(0.03, abs=1e-6)
    
    def test_calculate_delta_with_percentage(self):
        """Test delta calculation with percentage improvements."""
        from hokusai.tracking.performance import PerformanceTracker
        
        tracker = PerformanceTracker()
        
        baseline = {"accuracy": 0.80}
        improved = {"accuracy": 0.88}
        
        delta = tracker._calculate_delta(baseline, improved, percentage=True)
        
        assert delta["accuracy"] == pytest.approx(0.08, abs=1e-6)
        assert delta["accuracy_pct"] == pytest.approx(10.0, abs=0.01)
    
    @patch('mlflow.log_params')
    @patch('mlflow.log_metrics')
    def test_log_contribution_impact(self, mock_log_metrics, mock_log_params):
        """Test logging contributor impact."""
        from hokusai.tracking.performance import PerformanceTracker
        
        tracker = PerformanceTracker()
        delta = {"accuracy": 0.05, "f1_score": 0.03}
        
        tracker.log_contribution_impact(
            contributor_address="0x123",
            model_id="model_456",
            delta=delta
        )
        
        mock_log_params.assert_called_once()
        mock_log_metrics.assert_called_once()
    
    def test_generate_deltaone_value(self):
        """Test DeltaOne value generation."""
        from hokusai.tracking.performance import PerformanceTracker
        
        tracker = PerformanceTracker()
        
        delta = {
            "accuracy": 0.05,
            "auroc": 0.03,
            "f1_score": 0.04
        }
        
        deltaone = tracker._generate_deltaone_value(delta)
        
        # Expected: (0.05 * 1.0 + 0.03 * 0.8 + 0.04 * 0.9) * 100
        expected = (0.05 + 0.024 + 0.036) * 100
        assert deltaone == pytest.approx(expected, abs=0.01)
    
    def test_validate_metrics(self):
        """Test metrics validation."""
        from hokusai.tracking.performance import PerformanceTracker
        
        tracker = PerformanceTracker()
        
        # Valid metrics
        valid_metrics = {"accuracy": 0.85, "recall": 0.80}
        assert tracker._validate_metrics(valid_metrics) is True
        
        # Invalid metrics - not a dict
        with pytest.raises(ValueError, match="must be a dictionary"):
            tracker._validate_metrics([0.85, 0.80])
        
        # Invalid metrics - empty
        with pytest.raises(ValueError, match="cannot be empty"):
            tracker._validate_metrics({})
        
        # Invalid metrics - non-numeric value
        with pytest.raises(ValueError, match="must be numeric"):
            tracker._validate_metrics({"accuracy": "high"})
    
    def test_get_contributor_impact(self):
        """Test getting contributor impact data."""
        from hokusai.tracking.performance import PerformanceTracker
        
        tracker = PerformanceTracker()
        impact = tracker.get_contributor_impact("0x123")
        
        assert "total_models_improved" in impact
        assert "total_improvement_score" in impact
        assert "contributions" in impact
        assert "first_contribution" in impact
        assert "last_contribution" in impact