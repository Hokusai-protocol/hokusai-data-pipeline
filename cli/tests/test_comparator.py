"""
Tests for the Comparator module
"""
import pytest
from unittest.mock import Mock, patch
import numpy as np
import sys
import os

# Add the src directory to the path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from comparator import Comparator, ComparisonResult


class TestComparisonResult:
    """Test the ComparisonResult class"""
    
    def test_comparison_result_creation(self):
        """Test creating comparison results"""
        result = ComparisonResult(
            model1_metrics={'accuracy': 0.93, 'f1_score': 0.91},
            model2_metrics={'accuracy': 0.95, 'f1_score': 0.94},
            improvements={'accuracy': 0.02, 'f1_score': 0.03},
            statistical_significance={'accuracy': 0.01, 'f1_score': 0.005}
        )
        
        assert result.model1_metrics['accuracy'] == 0.93
        assert result.model2_metrics['accuracy'] == 0.95
        assert result.improvements['accuracy'] == 0.02
        assert result.statistical_significance['accuracy'] == 0.01
    
    def test_comparison_result_to_dict(self):
        """Test converting comparison result to dictionary"""
        result = ComparisonResult(
            model1_metrics={'accuracy': 0.93},
            model2_metrics={'accuracy': 0.95},
            improvements={'accuracy': 0.02},
            statistical_significance={'accuracy': 0.01}
        )
        
        result_dict = result.to_dict()
        assert 'model1_metrics' in result_dict
        assert 'model2_metrics' in result_dict
        assert 'improvements' in result_dict
        assert 'statistical_significance' in result_dict
    
    def test_comparison_result_summary(self):
        """Test generating comparison summary"""
        result = ComparisonResult(
            model1_metrics={'accuracy': 0.93, 'f1_score': 0.91},
            model2_metrics={'accuracy': 0.95, 'f1_score': 0.94},
            improvements={'accuracy': 0.02, 'f1_score': 0.03},
            statistical_significance={'accuracy': 0.01, 'f1_score': 0.005}
        )
        
        summary = result.get_summary()
        assert 'better' in summary or 'worse' in summary or 'improvement' in summary
        assert isinstance(summary, str)


class TestComparator:
    """Test the Comparator class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.comparator = Comparator()
        
        # Create mock models
        self.mock_model1 = Mock()
        self.mock_model1.predict = Mock(return_value=np.array([0, 1, 1, 0, 1]))
        
        self.mock_model2 = Mock()
        self.mock_model2.predict = Mock(return_value=np.array([0, 1, 1, 0, 0]))
        
        # Create mock dataset
        self.mock_dataset = Mock()
        self.mock_dataset.get_features = Mock(return_value=np.random.randn(5, 10))
        self.mock_dataset.get_labels = Mock(return_value=np.array([0, 1, 1, 0, 1]))
    
    def test_comparator_initialization(self):
        """Test that comparator initializes correctly"""
        assert self.comparator is not None
        assert hasattr(self.comparator, 'compare')
    
    @patch('comparator.Evaluator')
    def test_compare_models(self, mock_evaluator_class):
        """Test basic model comparison"""
        # Set up mock evaluator
        mock_evaluator = Mock()
        mock_evaluator_class.return_value = mock_evaluator
        
        # Mock evaluation results
        mock_metrics1 = Mock()
        mock_metrics1.to_dict.return_value = {
            'accuracy': 0.93,
            'precision': 0.92,
            'recall': 0.91,
            'f1_score': 0.915
        }
        
        mock_metrics2 = Mock()
        mock_metrics2.to_dict.return_value = {
            'accuracy': 0.95,
            'precision': 0.94,
            'recall': 0.93,
            'f1_score': 0.935
        }
        
        mock_evaluator.evaluate.side_effect = [mock_metrics1, mock_metrics2]
        
        # Perform comparison
        result = self.comparator.compare(
            self.mock_model1,
            self.mock_model2,
            self.mock_dataset
        )
        
        # Verify evaluations were performed
        assert mock_evaluator.evaluate.call_count == 2
        
        # Check result
        assert isinstance(result, ComparisonResult)
        assert result.improvements['accuracy'] == pytest.approx(0.02, abs=0.001)
        assert result.improvements['f1_score'] == pytest.approx(0.02, abs=0.001)
    
    def test_compare_with_statistical_test(self):
        """Test comparison with statistical significance testing"""
        # Create datasets with known differences
        n_samples = 100
        features = np.random.randn(n_samples, 10)
        labels = np.random.randint(0, 2, n_samples)
        
        self.mock_dataset.get_features = Mock(return_value=features)
        self.mock_dataset.get_labels = Mock(return_value=labels)
        
        # Model 1: Random predictions
        self.mock_model1.predict = Mock(
            side_effect=lambda x: np.random.randint(0, 2, len(x))
        )
        
        # Model 2: Slightly better predictions
        def better_predict(x):
            preds = np.random.randint(0, 2, len(x))
            # Make 10% of predictions match true labels
            true_labels = labels[:len(x)]
            mask = np.random.random(len(x)) < 0.1
            preds[mask] = true_labels[mask]
            return preds
        
        self.mock_model2.predict = Mock(side_effect=better_predict)
        
        result = self.comparator.compare(
            self.mock_model1,
            self.mock_model2,
            self.mock_dataset,
            n_bootstrap=10  # Small number for testing
        )
        
        # Check that statistical significance was calculated
        assert 'accuracy' in result.statistical_significance
        assert isinstance(result.statistical_significance['accuracy'], float)
        assert 0 <= result.statistical_significance['accuracy'] <= 1
    
    def test_compare_with_cross_validation(self):
        """Test comparison using cross-validation"""
        result = self.comparator.compare(
            self.mock_model1,
            self.mock_model2,
            self.mock_dataset,
            cv_folds=3
        )
        
        # Should have performed multiple evaluations
        assert isinstance(result, ComparisonResult)
        # Results should include variance estimates
        assert hasattr(result, 'model1_variance') or 'variance' in str(result.to_dict())
    
    def test_compare_output_format(self):
        """Test that comparison outputs are in correct format"""
        result = self.comparator.compare(
            self.mock_model1,
            self.mock_model2,
            self.mock_dataset
        )
        
        # Convert to dict for JSON serialization
        result_dict = result.to_dict()
        
        # Verify format
        assert isinstance(result_dict, dict)
        assert 'model1_metrics' in result_dict
        assert 'model2_metrics' in result_dict
        assert 'improvements' in result_dict
        
        # Check metric values are numeric
        for metrics in [result_dict['model1_metrics'], result_dict['model2_metrics']]:
            assert all(isinstance(v, (int, float)) for v in metrics.values())
    
    @patch('comparator.mlflow')
    def test_compare_with_mlflow_logging(self, mock_mlflow):
        """Test that comparison logs to MLflow"""
        result = self.comparator.compare(
            self.mock_model1,
            self.mock_model2,
            self.mock_dataset,
            log_to_mlflow=True
        )
        
        # Verify MLflow logging
        assert mock_mlflow.log_metrics.called
        # Should log comparison metrics
        logged_calls = mock_mlflow.log_metrics.call_args_list
        assert any('improvement' in str(call) for call in logged_calls)
    
    def test_compare_error_handling(self):
        """Test that comparator handles errors gracefully"""
        # Model that raises error
        self.mock_model1.predict = Mock(side_effect=Exception("Model 1 failed"))
        
        with pytest.raises(Exception, match="Model 1 failed"):
            self.comparator.compare(
                self.mock_model1,
                self.mock_model2,
                self.mock_dataset
            )
    
    def test_compare_identical_models(self):
        """Test comparing identical models"""
        # Both models make same predictions
        same_predictions = np.array([0, 1, 1, 0, 1])
        self.mock_model1.predict = Mock(return_value=same_predictions)
        self.mock_model2.predict = Mock(return_value=same_predictions)
        
        result = self.comparator.compare(
            self.mock_model1,
            self.mock_model2,
            self.mock_dataset
        )
        
        # Improvements should be zero
        assert all(v == 0 for v in result.improvements.values())
        
        # Statistical significance should indicate no difference
        if hasattr(result, 'statistical_significance'):
            assert all(v > 0.05 for v in result.statistical_significance.values())