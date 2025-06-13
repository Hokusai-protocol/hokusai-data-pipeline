"""
Tests for the Evaluator module
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np
import sys
import os

# Add the src directory to the path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from evaluator import Evaluator, EvaluationMetrics


class TestEvaluationMetrics:
    """Test the EvaluationMetrics class"""
    
    def test_metrics_creation(self):
        """Test creating evaluation metrics"""
        metrics = EvaluationMetrics(
            accuracy=0.95,
            precision=0.93,
            recall=0.92,
            f1_score=0.925
        )
        
        assert metrics.accuracy == 0.95
        assert metrics.precision == 0.93
        assert metrics.recall == 0.92
        assert metrics.f1_score == 0.925
    
    def test_metrics_to_dict(self):
        """Test converting metrics to dictionary"""
        metrics = EvaluationMetrics(
            accuracy=0.95,
            precision=0.93,
            recall=0.92,
            f1_score=0.925
        )
        
        metrics_dict = metrics.to_dict()
        assert metrics_dict == {
            'accuracy': 0.95,
            'precision': 0.93,
            'recall': 0.92,
            'f1_score': 0.925
        }
    
    def test_metrics_from_arrays(self):
        """Test calculating metrics from prediction arrays"""
        y_true = np.array([0, 1, 1, 0, 1, 0, 1, 0])
        y_pred = np.array([0, 1, 1, 0, 0, 0, 1, 1])
        
        metrics = EvaluationMetrics.from_predictions(y_true, y_pred)
        
        assert metrics.accuracy == 0.75  # 6/8 correct
        assert 0 < metrics.precision < 1
        assert 0 < metrics.recall < 1
        assert 0 < metrics.f1_score < 1


class TestEvaluator:
    """Test the Evaluator class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.evaluator = Evaluator()
        
        # Create mock model
        self.mock_model = Mock()
        self.mock_model.predict = Mock(return_value=np.array([0, 1, 1, 0]))
        
        # Create mock dataset
        self.mock_dataset = Mock()
        self.mock_dataset.get_features = Mock(return_value=np.random.randn(4, 10))
        self.mock_dataset.get_labels = Mock(return_value=np.array([0, 1, 1, 0]))
    
    def test_evaluator_initialization(self):
        """Test that evaluator initializes correctly"""
        assert self.evaluator is not None
        assert hasattr(self.evaluator, 'evaluate')
    
    def test_evaluate_model(self):
        """Test basic model evaluation"""
        metrics = self.evaluator.evaluate(self.mock_model, self.mock_dataset)
        
        # Verify method calls
        self.mock_dataset.get_features.assert_called_once()
        self.mock_dataset.get_labels.assert_called_once()
        self.mock_model.predict.assert_called_once()
        
        # Check metrics
        assert isinstance(metrics, EvaluationMetrics)
        assert metrics.accuracy == 1.0  # Perfect predictions in mock
    
    def test_evaluate_with_stratified_sampling(self):
        """Test evaluation with stratified sampling"""
        # Create larger dataset
        n_samples = 1000
        features = np.random.randn(n_samples, 10)
        labels = np.random.randint(0, 2, n_samples)
        
        self.mock_dataset.get_features = Mock(return_value=features)
        self.mock_dataset.get_labels = Mock(return_value=labels)
        self.mock_dataset.size = n_samples
        
        # Mock predictions
        self.mock_model.predict = Mock(side_effect=lambda x: np.random.randint(0, 2, len(x)))
        
        # Evaluate with sampling
        metrics = self.evaluator.evaluate(
            self.mock_model,
            self.mock_dataset,
            sample_size=100
        )
        
        # Verify sampling occurred
        predict_calls = self.mock_model.predict.call_args_list
        assert len(predict_calls) > 0
        # Check that we're not evaluating on all samples
        total_evaluated = sum(len(call[0][0]) for call in predict_calls)
        assert total_evaluated < n_samples
    
    def test_evaluate_with_batch_processing(self):
        """Test evaluation with batch processing"""
        n_samples = 1000
        batch_size = 32
        
        features = np.random.randn(n_samples, 10)
        labels = np.random.randint(0, 2, n_samples)
        
        self.mock_dataset.get_features = Mock(return_value=features)
        self.mock_dataset.get_labels = Mock(return_value=labels)
        
        # Mock batch predictions
        def batch_predict(x):
            return np.random.randint(0, 2, len(x))
        
        self.mock_model.predict = Mock(side_effect=batch_predict)
        
        metrics = self.evaluator.evaluate(
            self.mock_model,
            self.mock_dataset,
            batch_size=batch_size
        )
        
        # Verify batching occurred
        assert self.mock_model.predict.call_count > 1
        # Check batch sizes
        for call in self.mock_model.predict.call_args_list[:-1]:
            assert len(call[0][0]) == batch_size
    
    def test_evaluate_error_handling(self):
        """Test that evaluator handles errors gracefully"""
        # Model that raises error
        self.mock_model.predict = Mock(side_effect=Exception("Model prediction failed"))
        
        with pytest.raises(Exception, match="Model prediction failed"):
            self.evaluator.evaluate(self.mock_model, self.mock_dataset)
    
    @patch('evaluator.mlflow')
    def test_evaluate_with_mlflow_logging(self, mock_mlflow):
        """Test that evaluation logs metrics to MLflow"""
        metrics = self.evaluator.evaluate(
            self.mock_model,
            self.mock_dataset,
            log_to_mlflow=True
        )
        
        # Verify MLflow logging
        mock_mlflow.log_metrics.assert_called_once()
        logged_metrics = mock_mlflow.log_metrics.call_args[0][0]
        assert 'accuracy' in logged_metrics
        assert 'precision' in logged_metrics
        assert 'recall' in logged_metrics
        assert 'f1_score' in logged_metrics
    
    def test_evaluate_deterministic(self):
        """Test that evaluation is deterministic with fixed seed"""
        # Set random seed
        np.random.seed(42)
        
        # First evaluation
        metrics1 = self.evaluator.evaluate(self.mock_model, self.mock_dataset)
        
        # Reset seed and evaluate again
        np.random.seed(42)
        metrics2 = self.evaluator.evaluate(self.mock_model, self.mock_dataset)
        
        # Results should be identical
        assert metrics1.accuracy == metrics2.accuracy
        assert metrics1.precision == metrics2.precision
        assert metrics1.recall == metrics2.recall
        assert metrics1.f1_score == metrics2.f1_score
    
    def test_evaluate_output_format(self):
        """Test that evaluation outputs are in correct format"""
        metrics = self.evaluator.evaluate(self.mock_model, self.mock_dataset)
        
        # Convert to dict for JSON serialization
        metrics_dict = metrics.to_dict()
        
        # Verify format
        assert isinstance(metrics_dict, dict)
        assert all(isinstance(v, (int, float)) for v in metrics_dict.values())
        assert all(0 <= v <= 1 for v in metrics_dict.values())  # Metrics should be in [0, 1]