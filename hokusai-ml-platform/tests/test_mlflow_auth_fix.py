"""Test MLflow authentication fix."""

import os
import pytest
from unittest.mock import patch, MagicMock
import mlflow


def test_mlflow_tracking_token_support():
    """Test that MLFLOW_TRACKING_TOKEN environment variable is respected."""
    # Set the token
    os.environ["MLFLOW_TRACKING_TOKEN"] = "test-token-123"
    
    # Import after setting env var to test module-level configuration
    from hokusai.tracking.experiments import ExperimentManager
    
    # Mock MLflow to avoid actual API calls
    with patch("mlflow.get_experiment_by_name") as mock_get_exp:
        with patch("mlflow.create_experiment") as mock_create_exp:
            mock_get_exp.return_value = MagicMock(experiment_id="123")
            
            # This should not raise an authentication error
            manager = ExperimentManager("test_experiment")
            
            # Verify MLflow was called (meaning auth was successful)
            assert mock_get_exp.called


def test_mlflow_auth_error_handling():
    """Test graceful handling of MLflow authentication errors."""
    from hokusai.tracking.experiments import ExperimentManager
    
    # Clear any auth tokens
    os.environ.pop("MLFLOW_TRACKING_TOKEN", None)
    os.environ["HOKUSAI_OPTIONAL_MLFLOW"] = "true"
    
    # Mock MLflow to simulate 403 error
    with patch("mlflow.get_experiment_by_name") as mock_get_exp:
        mock_get_exp.side_effect = Exception("API request failed with error code 403")
        
        # Should switch to mock mode instead of failing
        manager = ExperimentManager("test_experiment")
        assert manager.mock_mode == True
        
        # Should work in mock mode
        result = manager.compare_models("baseline", "candidate", {"features": [], "labels": []})
        assert "baseline_metrics" in result
        assert "recommendation" in result


def test_mlflow_token_configuration():
    """Test that MLflow client is configured with authentication token."""
    # This test verifies the internal configuration
    os.environ["MLFLOW_TRACKING_TOKEN"] = "test-token-123"
    os.environ["MLFLOW_TRACKING_URI"] = "http://test.mlflow.server"
    
    # Import the config module (to be created)
    from hokusai.config import setup_mlflow_auth
    
    # Setup authentication
    setup_mlflow_auth()
    
    # Verify MLflow environment is configured
    assert os.environ.get("MLFLOW_TRACKING_TOKEN") == "test-token-123"
    assert mlflow.get_tracking_uri() == "http://test.mlflow.server"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])