"""Unit tests for the ExperimentManager service."""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import mlflow
from datetime import datetime
import numpy as np

from src.services.experiment_manager import ExperimentManager


class TestExperimentManager:
    """Test cases for ExperimentManager class."""
    
    @pytest.fixture
    def manager(self):
        """Create an experiment manager instance for testing."""
        with patch('mlflow.set_experiment'):
            return ExperimentManager()
    
    @pytest.fixture
    def mock_baseline_model(self):
        """Create a mock baseline model."""
        model = Mock()
        model.predict = Mock(return_value=np.array([0.2, 0.8, 0.6, 0.9]))
        return model
    
    @pytest.fixture
    def mock_contributed_data(self):
        """Create mock contributed data."""
        return {
            "features": np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]]),
            "labels": np.array([0, 1, 1]),
            "metadata": {
                "contributor_id": "contrib_001",
                "dataset_hash": "0xabc123"
            }
        }
    
    @pytest.fixture
    def mock_test_data(self):
        """Create mock test data for model comparison."""
        return {
            "features": np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]]),
            "labels": np.array([0, 1, 1, 0]),
            "dataset_name": "standard_test_set"
        }
    
    def test_init_default(self):
        """Test ExperimentManager initialization with defaults."""
        with patch('mlflow.set_experiment') as mock_set_exp:
            manager = ExperimentManager()
            assert manager.experiment_name == "hokusai_model_improvements"
            mock_set_exp.assert_called_once_with("hokusai_model_improvements")
    
    def test_init_custom_experiment(self):
        """Test ExperimentManager initialization with custom experiment name."""
        with patch('mlflow.set_experiment') as mock_set_exp:
            manager = ExperimentManager(experiment_name="custom_experiment")
            assert manager.experiment_name == "custom_experiment"
            mock_set_exp.assert_called_once_with("custom_experiment")
    
    @patch('mlflow.start_run')
    @patch('mlflow.log_params')
    @patch('mlflow.set_tag')
    def test_create_improvement_experiment_success(self, mock_set_tag, mock_log_params, 
                                                 mock_start_run, manager, 
                                                 mock_contributed_data):
        """Test successful creation of improvement experiment."""
        # Setup mocks
        mock_run = Mock()
        mock_run.info.run_id = "experiment_123"
        mock_run.info.experiment_id = "exp_456"
        mock_start_run.return_value.__enter__ = Mock(return_value=mock_run)
        mock_start_run.return_value.__exit__ = Mock(return_value=None)
        
        baseline_model_id = "baseline_model/1"
        
        # Execute
        experiment_id = manager.create_improvement_experiment(
            baseline_model_id=baseline_model_id,
            contributed_data=mock_contributed_data
        )
        
        # Verify
        assert experiment_id == "experiment_123"
        
        # Check logged parameters
        mock_log_params.assert_called()
        params = mock_log_params.call_args[0][0]
        assert params["baseline_model_id"] == baseline_model_id
        assert params["contributed_data_hash"] == mock_contributed_data["metadata"]["dataset_hash"]
        assert params["contributed_data_size"] == "3"
        
        # Check tags
        mock_set_tag.assert_any_call("experiment_type", "model_improvement")
        mock_set_tag.assert_any_call("contributor_id", "contrib_001")
    
    @patch('mlflow.pyfunc.load_model')
    @patch('mlflow.start_run')
    @patch('mlflow.log_metrics')
    def test_compare_models_success(self, mock_log_metrics, mock_start_run, 
                                  mock_load_model, manager, mock_test_data):
        """Test successful model comparison."""
        # Setup baseline model
        baseline_model = Mock()
        baseline_preds = np.array([0.2, 0.8, 0.7, 0.3])
        baseline_model.predict = Mock(return_value=baseline_preds)
        
        # Setup candidate model
        candidate_model = Mock()
        candidate_preds = np.array([0.1, 0.9, 0.85, 0.2])
        candidate_model.predict = Mock(return_value=candidate_preds)
        
        # Mock model loading
        def load_model_side_effect(model_uri):
            if "baseline" in model_uri:
                return baseline_model
            else:
                return candidate_model
        
        mock_load_model.side_effect = load_model_side_effect
        
        # Setup run context
        mock_run = Mock()
        mock_start_run.return_value.__enter__ = Mock(return_value=mock_run)
        mock_start_run.return_value.__exit__ = Mock(return_value=None)
        
        # Execute
        comparison_result = manager.compare_models(
            baseline_id="baseline_model/1",
            candidate_id="candidate_model/2",
            test_data=mock_test_data
        )
        
        # Verify results structure
        assert "baseline_metrics" in comparison_result
        assert "candidate_metrics" in comparison_result
        assert "improvements" in comparison_result
        assert "recommendation" in comparison_result
        
        # Check that metrics were calculated
        assert comparison_result["baseline_metrics"]["accuracy"] is not None
        assert comparison_result["candidate_metrics"]["accuracy"] is not None
        
        # Verify MLflow logging
        mock_log_metrics.assert_called()
        logged_metrics = {}
        for call in mock_log_metrics.call_args_list:
            logged_metrics.update(call[0][0])
        
        assert "baseline_accuracy" in logged_metrics
        assert "candidate_accuracy" in logged_metrics
        assert "accuracy_improvement" in logged_metrics
    
    @patch('src.services.experiment_manager.accuracy_score')
    @patch('src.services.experiment_manager.roc_auc_score')
    @patch('src.services.experiment_manager.f1_score')
    @patch('src.services.experiment_manager.precision_score')
    @patch('src.services.experiment_manager.recall_score')
    def test_calculate_metrics(self, mock_recall, mock_precision, mock_f1, 
                             mock_roc_auc, mock_accuracy, manager):
        """Test metrics calculation from predictions."""
        # Setup mock returns
        mock_accuracy.return_value = 0.85
        mock_roc_auc.return_value = 0.90
        mock_f1.return_value = 0.83
        mock_precision.return_value = 0.84
        mock_recall.return_value = 0.82
        
        y_true = np.array([0, 1, 1, 0, 1])
        y_pred = np.array([0.2, 0.8, 0.7, 0.3, 0.9])
        
        metrics = manager._calculate_metrics(y_true, y_pred, threshold=0.5)
        
        assert "accuracy" in metrics
        assert "auroc" in metrics
        assert "f1_score" in metrics
        assert "precision" in metrics
        assert "recall" in metrics
        
        # Check metric ranges
        for metric_value in metrics.values():
            assert 0 <= metric_value <= 1
    
    @patch('src.services.experiment_manager.accuracy_score', return_value=1.0)
    @patch('src.services.experiment_manager.roc_auc_score', return_value=1.0)
    @patch('src.services.experiment_manager.f1_score', return_value=1.0)
    @patch('src.services.experiment_manager.precision_score', return_value=1.0)
    @patch('src.services.experiment_manager.recall_score', return_value=1.0)
    def test_calculate_metrics_perfect_predictions(self, mock_recall, mock_precision, 
                                                 mock_f1, mock_roc_auc, mock_accuracy, 
                                                 manager):
        """Test metrics calculation with perfect predictions."""
        y_true = np.array([0, 1, 1, 0])
        y_pred = np.array([0.1, 0.9, 0.8, 0.2])
        
        metrics = manager._calculate_metrics(y_true, y_pred, threshold=0.5)
        
        assert metrics["accuracy"] == 1.0
        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["f1_score"] == 1.0
    
    @patch('mlflow.search_runs')
    def test_get_experiment_history_success(self, mock_search_runs, manager):
        """Test retrieving experiment history."""
        # Mock run data
        mock_runs = Mock()
        mock_runs.iterrows.return_value = [
            (0, {"run_id": "run1", "params.baseline_model_id": "model/1", 
                 "metrics.accuracy_improvement": 0.02, "start_time": "2024-01-01"}),
            (1, {"run_id": "run2", "params.baseline_model_id": "model/1", 
                 "metrics.accuracy_improvement": 0.03, "start_time": "2024-01-02"})
        ]
        mock_search_runs.return_value = mock_runs
        
        # Execute
        history = manager.get_experiment_history(baseline_model_id="model/1")
        
        # Verify
        assert len(history) == 2
        assert history[0]["run_id"] == "run1"
        assert history[0]["improvement"] == 0.02
        assert history[1]["improvement"] == 0.03
    
    def test_validate_experiment_config(self, manager):
        """Test experiment configuration validation."""
        valid_config = {
            "test_size": 0.2,
            "random_seed": 42,
            "metrics": ["accuracy", "auroc"],
            "comparison_threshold": 0.01
        }
        
        assert manager._validate_config(valid_config) == True
        
        # Invalid configs
        with pytest.raises(ValueError, match="test_size must be between"):
            manager._validate_config({"test_size": 1.5})
        
        with pytest.raises(ValueError, match="Invalid metric"):
            manager._validate_config({"metrics": ["invalid_metric"]})
    
    @patch('mlflow.log_artifact')
    def test_log_experiment_artifacts(self, mock_log_artifact, manager):
        """Test logging experiment artifacts."""
        artifacts = {
            "confusion_matrix": "path/to/confusion_matrix.png",
            "roc_curve": "path/to/roc_curve.png",
            "experiment_report": "path/to/report.html"
        }
        
        manager._log_artifacts(artifacts)
        
        assert mock_log_artifact.call_count == 3
        for artifact_path in artifacts.values():
            mock_log_artifact.assert_any_call(artifact_path)
    
    def test_determine_recommendation(self, manager):
        """Test recommendation logic based on improvements."""
        # Significant improvement
        improvements = {"accuracy": 0.05, "auroc": 0.04}
        recommendation = manager._determine_recommendation(improvements, threshold=0.01)
        assert recommendation == "ACCEPT"
        
        # No improvement
        improvements = {"accuracy": -0.02, "auroc": -0.01}
        recommendation = manager._determine_recommendation(improvements, threshold=0.01)
        assert recommendation == "REJECT"
        
        # Mixed results
        improvements = {"accuracy": 0.03, "auroc": -0.01}
        recommendation = manager._determine_recommendation(improvements, threshold=0.01)
        assert recommendation == "REVIEW"
    
    @patch('mlflow.create_experiment')
    @patch('mlflow.get_experiment_by_name')
    def test_create_experiment_if_not_exists(self, mock_get_exp, mock_create_exp, manager):
        """Test experiment creation when it doesn't exist."""
        mock_get_exp.return_value = None
        mock_create_exp.return_value = "123"
        
        with patch('mlflow.set_experiment'):
            manager = ExperimentManager(experiment_name="new_experiment")
        
        mock_create_exp.assert_called_once_with("new_experiment")
    
    def test_format_comparison_report(self, manager):
        """Test formatting comparison report for display."""
        comparison_result = {
            "baseline_metrics": {"accuracy": 0.85, "auroc": 0.82},
            "candidate_metrics": {"accuracy": 0.88, "auroc": 0.85},
            "improvements": {"accuracy": 0.03, "auroc": 0.03},
            "recommendation": "ACCEPT"
        }
        
        report = manager._format_report(comparison_result)
        
        assert "Model Comparison Report" in report
        assert "Baseline" in report
        assert "Candidate" in report
        assert "Improvement" in report
        assert "ACCEPT" in report