"""Tests for MLflow error handling and retry logic."""

import pytest
from unittest.mock import patch, MagicMock, call
import time
import os
import sys

# Add SDK to path for testing
sdk_path = os.path.join(os.path.dirname(__file__), "..", "hokusai-ml-platform", "src")
sys.path.insert(0, sdk_path)


class TestMLflowErrorHandling:
    """Test error handling for MLflow connections."""
    
    def test_experiment_manager_handles_403_error(self):
        """Test that ExperimentManager properly handles 403 authentication errors."""
        from hokusai.tracking import ExperimentManager
        
        with patch('mlflow.get_experiment_by_name') as mock_get_exp:
            # Simulate 403 error
            mock_get_exp.side_effect = Exception("API request failed with error code 403 != 200")
            
            with pytest.raises(Exception) as exc_info:
                ExperimentManager()
            
            assert "403" in str(exc_info.value)
    
    def test_experiment_manager_retries_on_connection_error(self):
        """Test that ExperimentManager retries on transient connection errors."""
        from hokusai.tracking import ExperimentManager
        
        with patch('mlflow.get_experiment_by_name') as mock_get_exp:
            with patch('mlflow.create_experiment'):
                with patch('mlflow.set_experiment'):
                    with patch('time.sleep'):  # Speed up test
                        # Fail twice, then succeed
                        mock_get_exp.side_effect = [
                            Exception("Connection error"),
                            Exception("Timeout"),
                            None  # Success
                        ]
                        
                        manager = ExperimentManager()
                        
                        # Should have been called 3 times
                        assert mock_get_exp.call_count == 3
    
    def test_experiment_manager_max_retries(self):
        """Test that ExperimentManager fails after max retries."""
        from hokusai.tracking import ExperimentManager
        
        with patch('mlflow.get_experiment_by_name') as mock_get_exp:
            with patch('time.sleep'):  # Speed up test
                # Always fail
                mock_get_exp.side_effect = Exception("Connection error")
                
                with pytest.raises(Exception) as exc_info:
                    ExperimentManager()
                
                # Should have tried 3 times
                assert mock_get_exp.call_count == 3
                assert "3 attempts" in str(exc_info.value)
    
    def test_experiment_manager_error_messages(self):
        """Test that error messages are informative."""
        from hokusai.tracking import ExperimentManager
        
        # Test 403 error message
        with patch('mlflow.get_experiment_by_name') as mock_get_exp:
            mock_get_exp.side_effect = Exception("error code 403")
            
            with pytest.raises(Exception):
                ExperimentManager()
            
            # Check logs would contain helpful messages
            # (In real test, would capture logs)
    
    def test_mock_mode_bypasses_mlflow_errors(self):
        """Test that mock mode bypasses all MLflow connection errors."""
        os.environ["HOKUSAI_MOCK_MODE"] = "true"
        
        try:
            from hokusai.tracking import ExperimentManager
            
            # Should not call MLflow at all
            with patch('mlflow.get_experiment_by_name') as mock_get_exp:
                mock_get_exp.side_effect = Exception("Should not be called")
                
                manager = ExperimentManager()
                assert manager.mock_mode is True
                
                # MLflow should not have been called
                mock_get_exp.assert_not_called()
                
        finally:
            os.environ.pop("HOKUSAI_MOCK_MODE", None)


class TestMLflowProxyErrorHandling:
    """Test error handling in MLflow proxy."""
    
    def test_proxy_timeout_handling(self):
        """Test proxy handles timeout with appropriate status code."""
        from fastapi.testclient import TestClient
        from src.api.main import app
        import httpx
        
        client = TestClient(app)
        
        with patch('httpx.AsyncClient.request') as mock_request:
            mock_request.side_effect = httpx.TimeoutException("Timeout")
            
            response = client.get("/mlflow/api/test")
            
            assert response.status_code == 504
            assert "timeout" in response.json()["detail"].lower()
    
    def test_proxy_connection_error_handling(self):
        """Test proxy handles connection errors."""
        from fastapi.testclient import TestClient
        from src.api.main import app
        import httpx
        
        client = TestClient(app)
        
        with patch('httpx.AsyncClient.request') as mock_request:
            mock_request.side_effect = httpx.ConnectError("Connection refused")
            
            response = client.get("/mlflow/api/test")
            
            assert response.status_code == 502
            assert "connect" in response.json()["detail"].lower()
    
    def test_proxy_generic_error_handling(self):
        """Test proxy handles unexpected errors."""
        from fastapi.testclient import TestClient
        from src.api.main import app
        
        client = TestClient(app)
        
        with patch('httpx.AsyncClient.request') as mock_request:
            mock_request.side_effect = Exception("Unexpected error")
            
            response = client.get("/mlflow/api/test")
            
            assert response.status_code == 500
            assert "internal server error" in response.json()["detail"].lower()


class TestConfigurationValidation:
    """Test configuration validation and error messages."""
    
    def test_invalid_tracking_uri_format(self):
        """Test handling of invalid tracking URI format."""
        from hokusai.tracking import ExperimentManager
        
        with patch('mlflow.set_tracking_uri'):
            with patch('mlflow.get_experiment_by_name') as mock_get_exp:
                # Simulate invalid URI error
                mock_get_exp.side_effect = Exception("Invalid URI scheme")
                
                with pytest.raises(Exception):
                    ExperimentManager(mlflow_tracking_uri="invalid://uri")
    
    def test_environment_variable_precedence(self):
        """Test that environment variables take precedence."""
        custom_uri = "http://env-mlflow-server.com"
        os.environ["MLFLOW_TRACKING_URI"] = custom_uri
        
        try:
            from hokusai.tracking import ExperimentManager
            
            with patch('mlflow.set_tracking_uri') as mock_set_uri:
                with patch('mlflow.get_experiment_by_name', return_value=None):
                    with patch('mlflow.create_experiment'):
                        with patch('mlflow.set_experiment'):
                            manager = ExperimentManager()
                            
                            # Should use env var
                            mock_set_uri.assert_called_with(custom_uri)
                            
        finally:
            os.environ.pop("MLFLOW_TRACKING_URI", None)


def test_comprehensive_error_scenario():
    """Test a comprehensive error scenario with multiple issues."""
    from hokusai.tracking import ExperimentManager
    
    # Scenario: MLflow server is down, then comes back with auth issues
    with patch('mlflow.get_experiment_by_name') as mock_get_exp:
        with patch('time.sleep'):
            # First attempt: connection error
            # Second attempt: still connection error  
            # Third attempt: 403 auth error
            mock_get_exp.side_effect = [
                Exception("Connection refused"),
                Exception("Connection refused"),
                Exception("error code 403")
            ]
            
            with pytest.raises(Exception) as exc_info:
                ExperimentManager()
            
            # Should fail with 403 error after retries
            assert "403" in str(exc_info.value)