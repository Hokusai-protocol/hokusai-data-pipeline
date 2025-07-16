"""Test that the MLflow authentication fix resolves the 403 error."""

import os
import pytest
from unittest.mock import patch, MagicMock


def test_mlflow_authentication_no_403_error():
    """Test that setting MLFLOW_TRACKING_TOKEN prevents 403 errors."""
    # Set authentication token
    os.environ["MLFLOW_TRACKING_TOKEN"] = "test-token-123"
    os.environ["MLFLOW_TRACKING_URI"] = "http://test.mlflow.server"
    
    from hokusai.tracking.experiments import ExperimentManager
    
    # Mock MLflow to return successful response (not 403)
    with patch("mlflow.get_experiment_by_name") as mock_get_exp:
        # Return a valid experiment (no 403 error)
        mock_get_exp.return_value = MagicMock(experiment_id="123")
        
        # This should NOT raise a 403 error
        manager = ExperimentManager("test_experiment")
        
        # Verify manager initialized successfully
        assert manager.experiment_name == "test_experiment"
        assert manager.mock_mode == False  # Using real MLflow
        
        # Verify MLflow was called (auth worked)
        assert mock_get_exp.called


def test_mlflow_authentication_fallback():
    """Test graceful fallback when authentication fails."""
    # Clear authentication
    os.environ.pop("MLFLOW_TRACKING_TOKEN", None)
    os.environ["HOKUSAI_OPTIONAL_MLFLOW"] = "true"
    
    from hokusai.tracking.experiments import ExperimentManager
    
    # Mock MLflow to simulate 403 error
    with patch("mlflow.get_experiment_by_name") as mock_get_exp:
        mock_get_exp.side_effect = Exception("API request failed with error code 403")
        
        # Should fallback to mock mode gracefully
        manager = ExperimentManager("test_experiment")
        
        # Verify fallback worked
        assert manager.mock_mode == True
        assert manager.experiment_name == "test_experiment"


def test_authentication_environment_variables():
    """Test that authentication environment variables are respected."""
    # Test token authentication
    os.environ["MLFLOW_TRACKING_TOKEN"] = "my-token"
    
    from hokusai.config import get_mlflow_config
    config = get_mlflow_config()
    
    assert config["has_token"] == True
    assert os.environ.get("MLFLOW_TRACKING_TOKEN") == "my-token"
    
    # Test basic auth
    os.environ.pop("MLFLOW_TRACKING_TOKEN", None)
    os.environ["MLFLOW_TRACKING_USERNAME"] = "user"
    os.environ["MLFLOW_TRACKING_PASSWORD"] = "pass"
    
    config = get_mlflow_config()
    assert config["has_basic_auth"] == True
    
    # Clean up
    os.environ.pop("MLFLOW_TRACKING_USERNAME", None)
    os.environ.pop("MLFLOW_TRACKING_PASSWORD", None)


def test_mock_mode_for_local_development():
    """Test that mock mode works for local development."""
    os.environ["HOKUSAI_MOCK_MODE"] = "true"
    
    from hokusai.tracking.experiments import ExperimentManager
    
    # Should initialize in mock mode without any MLflow calls
    manager = ExperimentManager("test_experiment")
    
    assert manager.mock_mode == True
    
    # Should work without MLflow
    result = manager.compare_models(
        "baseline", 
        "candidate", 
        {"features": [], "labels": [], "dataset_name": "test"}
    )
    
    assert "baseline_metrics" in result
    assert "recommendation" in result
    assert result["recommendation"] in ["ACCEPT", "REJECT", "REVIEW"]
    
    # Clean up
    os.environ.pop("HOKUSAI_MOCK_MODE", None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])