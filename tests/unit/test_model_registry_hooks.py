"""Unit tests for model registry hooks."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.model_registry_hooks import ModelRegistryHooks, get_registry_hooks
from src.events.publishers.base import PublisherException


class TestModelRegistryHooks:
    """Test cases for ModelRegistryHooks."""
    
    @pytest.fixture
    def mock_publisher(self):
        """Create a mock publisher."""
        with patch("src.services.model_registry_hooks.get_publisher") as mock_get_pub:
            mock_pub = MagicMock()
            mock_pub.publish_model_ready.return_value = True
            mock_get_pub.return_value = mock_pub
            yield mock_pub
    
    @pytest.fixture
    def mock_validator(self):
        """Create a mock validator."""
        with patch("src.services.model_registry_hooks.MetricValidator") as mock_val_class:
            mock_val = MagicMock()
            mock_val.validate_baseline.return_value = True
            mock_val.validate_metric_value.return_value = True
            mock_val_class.return_value = mock_val
            yield mock_val
    
    def test_on_model_registered_success(self, mock_publisher, mock_validator):
        """Test successful model registration hook."""
        hooks = ModelRegistryHooks()
        
        result = hooks.on_model_registered_with_baseline(
            model_id="model-123",
            model_name="test_model",
            model_version="1",
            mlflow_run_id="run123",
            token_id="test-token",
            metric_name="accuracy",
            baseline_value=0.8,
            current_value=0.85,
            tags={"tag1": "value1"},
            contributor_address="0x1234567890123456789012345678901234567890",
            experiment_name="test_experiment"
        )
        
        assert result is True
        
        # Verify publisher was called with correct arguments
        mock_publisher.publish_model_ready.assert_called_once_with(
            model_id="model-123",
            token_symbol="test-token",
            metric_name="accuracy",
            baseline_value=0.8,
            current_value=0.85,
            model_name="test_model",
            model_version="1",
            mlflow_run_id="run123",
            contributor_address="0x1234567890123456789012345678901234567890",
            experiment_name="test_experiment",
            tags={"tag1": "value1"}
        )
        
        # Verify validation was performed
        mock_validator.validate_baseline.assert_called_once_with("accuracy", 0.8)
        mock_validator.validate_metric_value.assert_called_once_with("accuracy", 0.85)
    
    def test_model_below_baseline(self, mock_publisher, mock_validator):
        """Test hook when model doesn't meet baseline."""
        hooks = ModelRegistryHooks()
        
        result = hooks.on_model_registered_with_baseline(
            model_id="model-123",
            model_name="test_model",
            model_version="1",
            mlflow_run_id="run123",
            token_id="test-token",
            metric_name="accuracy",
            baseline_value=0.8,
            current_value=0.75,  # Below baseline
        )
        
        assert result is False
        
        # Publisher should not be called
        mock_publisher.publish_model_ready.assert_not_called()
    
    def test_invalid_baseline_value(self, mock_publisher, mock_validator):
        """Test hook with invalid baseline value."""
        hooks = ModelRegistryHooks()
        mock_validator.validate_baseline.return_value = False
        
        result = hooks.on_model_registered_with_baseline(
            model_id="model-123",
            model_name="test_model",
            model_version="1",
            mlflow_run_id="run123",
            token_id="test-token",
            metric_name="accuracy",
            baseline_value=-0.5,  # Invalid
            current_value=0.85,
        )
        
        assert result is False
        mock_publisher.publish_model_ready.assert_not_called()
    
    def test_invalid_metric_value(self, mock_publisher, mock_validator):
        """Test hook with invalid metric value."""
        hooks = ModelRegistryHooks()
        mock_validator.validate_metric_value.return_value = False
        
        result = hooks.on_model_registered_with_baseline(
            model_id="model-123",
            model_name="test_model",
            model_version="1",
            mlflow_run_id="run123",
            token_id="test-token",
            metric_name="accuracy",
            baseline_value=0.8,
            current_value=1.5,  # Invalid for accuracy
        )
        
        assert result is False
        mock_publisher.publish_model_ready.assert_not_called()
    
    def test_publisher_exception(self, mock_publisher, mock_validator):
        """Test hook when publisher raises exception."""
        hooks = ModelRegistryHooks()
        mock_publisher.publish_model_ready.side_effect = PublisherException("Connection failed")
        
        result = hooks.on_model_registered_with_baseline(
            model_id="model-123",
            model_name="test_model",
            model_version="1",
            mlflow_run_id="run123",
            token_id="test-token",
            metric_name="accuracy",
            baseline_value=0.8,
            current_value=0.85,
        )
        
        assert result is False
    
    def test_publisher_returns_false(self, mock_publisher, mock_validator):
        """Test hook when publisher returns False."""
        hooks = ModelRegistryHooks()
        mock_publisher.publish_model_ready.return_value = False
        
        result = hooks.on_model_registered_with_baseline(
            model_id="model-123",
            model_name="test_model",
            model_version="1",
            mlflow_run_id="run123",
            token_id="test-token",
            metric_name="accuracy",
            baseline_value=0.8,
            current_value=0.85,
        )
        
        assert result is False
    
    def test_on_model_validation_failed(self, mock_publisher, mock_validator):
        """Test validation failure hook."""
        hooks = ModelRegistryHooks()
        
        # Should not raise exception
        hooks.on_model_validation_failed(
            model_id="model-123",
            reason="Baseline not met",
            metric_name="accuracy",
            metric_value=0.75,
            baseline_value=0.8
        )
        
        # Currently just logs, no assertions needed
    
    def test_get_registry_hooks_singleton(self, mock_publisher, mock_validator):
        """Test that get_registry_hooks returns singleton."""
        hooks1 = get_registry_hooks()
        hooks2 = get_registry_hooks()
        
        assert hooks1 is hooks2
    
    def test_improvement_percentage_calculation(self, mock_publisher, mock_validator):
        """Test that improvement percentage is calculated correctly."""
        hooks = ModelRegistryHooks()
        
        # Capture the log output to verify calculation
        with patch("src.services.model_registry_hooks.logger") as mock_logger:
            result = hooks.on_model_registered_with_baseline(
                model_id="model-123",
                model_name="test_model",
                model_version="1",
                mlflow_run_id="run123",
                token_id="test-token",
                metric_name="accuracy",
                baseline_value=0.8,
                current_value=0.88,  # 10% improvement
            )
            
            assert result is True
            
            # Verify log contains correct improvement percentage
            log_call = mock_logger.info.call_args[0][0]
            assert "10.00%" in log_call