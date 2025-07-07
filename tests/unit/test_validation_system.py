"""
Unit tests for the validation system
"""
import pytest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from validation import MetricValidator, SupportedMetrics, BaselineComparator
from validation.baseline import ComparisonResult


class TestMetricValidator:
    """Test the metric validation functionality"""
    
    @pytest.fixture
    def validator(self):
        return MetricValidator()
    
    def test_validate_metric_name_valid(self, validator):
        """Test validation of valid metric names"""
        valid_metrics = ["accuracy", "auroc", "f1", "precision", "recall", 
                        "mse", "rmse", "mae", "reply_rate"]
        
        for metric in valid_metrics:
            assert validator.validate_metric_name(metric) is True
    
    def test_validate_metric_name_invalid(self, validator):
        """Test validation of invalid metric names"""
        invalid_metrics = ["invalid", "unknown_metric", "acc", ""]
        
        for metric in invalid_metrics:
            assert validator.validate_metric_name(metric) is False
    
    def test_validate_metric_value_classification(self, validator):
        """Test validation of classification metric values"""
        # Valid values
        assert validator.validate_metric_value("accuracy", 0.85) is True
        assert validator.validate_metric_value("auroc", 0.0) is True
        assert validator.validate_metric_value("f1", 1.0) is True
        
        # Invalid values
        assert validator.validate_metric_value("accuracy", -0.1) is False
        assert validator.validate_metric_value("auroc", 1.1) is False
    
    def test_validate_metric_value_regression(self, validator):
        """Test validation of regression metric values"""
        # Valid values
        assert validator.validate_metric_value("mse", 0.5) is True
        assert validator.validate_metric_value("rmse", 100.0) is True
        assert validator.validate_metric_value("r2", -0.5) is True  # R2 can be negative
        
        # Invalid values
        assert validator.validate_metric_value("mse", -0.1) is False
        assert validator.validate_metric_value("r2", 1.1) is False
    
    def test_validate_baseline(self, validator):
        """Test baseline validation"""
        # Valid baselines
        assert validator.validate_baseline("accuracy", 0.85) is True
        assert validator.validate_baseline("mse", 10.0) is True
        
        # Invalid baselines
        assert validator.validate_baseline("accuracy", 1.5) is False
        assert validator.validate_baseline("mse", -1.0) is False


class TestSupportedMetrics:
    """Test the SupportedMetrics enum"""
    
    def test_get_all_names(self):
        """Test getting all metric names"""
        names = SupportedMetrics.get_all_names()
        assert "accuracy" in names
        assert "auroc" in names
        assert "mse" in names
        assert len(names) > 10  # Should have many metrics
    
    def test_is_valid(self):
        """Test metric name validation"""
        assert SupportedMetrics.is_valid("accuracy") is True
        assert SupportedMetrics.is_valid("AUROC") is True  # Case insensitive
        assert SupportedMetrics.is_valid("invalid") is False
    
    def test_get_metric_type(self):
        """Test metric type classification"""
        assert SupportedMetrics.get_metric_type("accuracy") == "classification"
        assert SupportedMetrics.get_metric_type("mse") == "regression"
        assert SupportedMetrics.get_metric_type("reply_rate") == "custom"


class TestBaselineComparator:
    """Test the baseline comparison functionality"""
    
    @pytest.fixture
    def comparator(self):
        return BaselineComparator()
    
    def test_compare_higher_better(self, comparator):
        """Test comparison for metrics where higher is better"""
        assert comparator.compare(0.9, 0.8, "higher_better") == ComparisonResult.IMPROVED
        assert comparator.compare(0.7, 0.8, "higher_better") == ComparisonResult.DEGRADED
        assert comparator.compare(0.8, 0.8, "higher_better") == ComparisonResult.NO_CHANGE
    
    def test_compare_lower_better(self, comparator):
        """Test comparison for metrics where lower is better"""
        assert comparator.compare(0.1, 0.2, "lower_better") == ComparisonResult.IMPROVED
        assert comparator.compare(0.3, 0.2, "lower_better") == ComparisonResult.DEGRADED
        assert comparator.compare(0.2, 0.2, "lower_better") == ComparisonResult.NO_CHANGE
    
    def test_meets_threshold(self, comparator):
        """Test threshold checking"""
        # Higher is better
        assert comparator.meets_threshold(0.85, 0.80, 0.05, "higher_better") is True
        assert comparator.meets_threshold(0.84, 0.80, 0.05, "higher_better") is False
        
        # Lower is better
        assert comparator.meets_threshold(0.15, 0.20, 0.05, "lower_better") is True
        assert comparator.meets_threshold(0.16, 0.20, 0.05, "lower_better") is False
    
    def test_calculate_improvement(self, comparator):
        """Test improvement calculation"""
        # Absolute improvement
        assert comparator.calculate_improvement(0.85, 0.80) == pytest.approx(0.05)
        assert comparator.calculate_improvement(0.75, 0.80) == pytest.approx(-0.05)
        
        # Percentage improvement
        assert comparator.calculate_improvement(0.85, 0.80, as_percentage=True) == pytest.approx(6.25)
        assert comparator.calculate_improvement(0.75, 0.80, as_percentage=True) == pytest.approx(-6.25)
    
    def test_get_metric_type(self, comparator):
        """Test automatic metric type detection"""
        assert comparator.get_metric_type("accuracy") == "higher_better"
        assert comparator.get_metric_type("mse") == "lower_better"
        assert comparator.get_metric_type("mean_squared_error") == "lower_better"
        assert comparator.get_metric_type("custom_score") == "higher_better"  # Default
    
    def test_validate_improvement_comprehensive(self, comparator):
        """Test comprehensive improvement validation"""
        result = comparator.validate_improvement(
            current_value=0.85,
            baseline_value=0.80,
            metric_name="accuracy",
            required_improvement=0.03
        )
        
        assert result["metric_name"] == "accuracy"
        assert result["current_value"] == 0.85
        assert result["baseline_value"] == 0.80
        assert result["comparison"] == ComparisonResult.IMPROVED.value
        assert result["improvement"] == pytest.approx(0.05)
        assert result["meets_baseline"] is True
        assert result["meets_threshold"] is True