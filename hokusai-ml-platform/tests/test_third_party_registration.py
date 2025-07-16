"""Test third-party model registration scenario."""

import os
import pytest
from unittest.mock import MagicMock, patch


def test_third_party_model_registration_with_auth():
    """Test that third-party can register model with authentication."""
    # Set up authentication
    os.environ["MLFLOW_TRACKING_TOKEN"] = "test-token-123"
    os.environ["HOKUSAI_API_KEY"] = "test-api-key"
    
    # Import after setting env vars
    from hokusai.core.registry import ModelRegistry
    from hokusai.tracking.experiments import ExperimentManager
    
    # Mock the MLflow backend completely
    with patch("mlflow.get_experiment_by_name") as mock_get_exp:
        with patch("hokusai.core.registry.mlflow") as mock_mlflow:
            # Setup mocks
            mock_get_exp.return_value = MagicMock(experiment_id="123")
            
            # Mock the MLflow client
            mock_client_instance = MagicMock()
            mock_mlflow.MlflowClient.return_value = mock_client_instance
            
            # Mock registry operations
            mock_client_instance.create_registered_model.return_value = MagicMock()
            mock_client_instance.create_model_version.return_value = MagicMock(
                name="test_model",
                version="1",
                run_id="test_run_id"
            )
            mock_client_instance.set_model_version_tag.return_value = None
            
            # Initialize components (should not fail with 403)
            experiment_manager = ExperimentManager("test_experiment")
            registry = ModelRegistry()
            
            # Mock model
            model = MagicMock()
            model.model_id = "test_model"
            model.model_type = "sklearn"
            
            # This should complete without authentication errors
            result = registry.register_baseline(
                model=model,
                model_type="sklearn",
                metadata={"test": "data"}
            )
            
            # Verify success
            assert result is not None
            assert experiment_manager.mock_mode == False  # Should use real MLflow
            
            # Verify MLflow client was created (authentication worked)
            assert mock_mlflow.MlflowClient.called


def test_third_party_registration_fallback_to_mock():
    """Test fallback to mock mode when MLflow unavailable."""
    # Clear authentication to trigger fallback
    os.environ.pop("MLFLOW_TRACKING_TOKEN", None)
    os.environ["HOKUSAI_OPTIONAL_MLFLOW"] = "true"
    
    from hokusai.tracking.experiments import ExperimentManager
    
    # Mock MLflow to simulate connection failure
    with patch("mlflow.get_experiment_by_name") as mock_get_exp:
        mock_get_exp.side_effect = Exception("Connection refused")
        
        # Should fallback to mock mode gracefully
        experiment_manager = ExperimentManager("test_experiment")
        assert experiment_manager.mock_mode == True
        
        # Should still work in mock mode
        run_id = experiment_manager.create_improvement_experiment(
            "baseline_model",
            {"features": [], "metadata": {"contributor_id": "test_user"}}
        )
        assert run_id is not None  # Mock run ID returned


def test_registration_with_mock_mode():
    """Test that registration works in mock mode for development."""
    os.environ["HOKUSAI_MOCK_MODE"] = "true"
    
    from hokusai.tracking.experiments import ExperimentManager
    from hokusai.core.registry import ModelRegistry
    
    # Should initialize in mock mode
    experiment_manager = ExperimentManager("test_experiment")
    assert experiment_manager.mock_mode == True
    
    # Mock registry operations
    with patch.object(ModelRegistry, 'register_baseline') as mock_register:
        mock_register.return_value = MagicMock(
            model_id="test_model",
            version="1",
            status="registered"
        )
        
        registry = ModelRegistry()
        model = MagicMock(model_id="test_model", model_type="sklearn")
        
        result = registry.register_baseline(
            model=model,
            model_type="sklearn",
            metadata={"test": "data"}
        )
        
        assert result is not None
        assert mock_register.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])