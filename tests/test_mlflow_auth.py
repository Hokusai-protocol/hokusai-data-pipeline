"""Tests for MLflow authentication bypass and proxy functionality."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import httpx

from src.api.main import app
from src.middleware.auth import APIKeyAuthMiddleware


class TestMLflowAuthBypass:
    """Test that MLflow endpoints bypass authentication."""
    
    def test_mlflow_endpoints_excluded_from_auth(self):
        """Test that /mlflow paths are in the excluded list."""
        middleware = APIKeyAuthMiddleware(app)
        assert "/mlflow" in middleware.excluded_paths
    
    def test_mlflow_endpoint_without_auth(self):
        """Test accessing MLflow endpoint without authentication."""
        client = TestClient(app)
        
        # Mock the MLflow proxy response
        with patch('httpx.AsyncClient.request') as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b'{"experiments": []}'
            mock_response.headers = {}
            mock_request.return_value = mock_response
            
            response = client.get("/mlflow/api/2.0/mlflow/experiments/list")
            
            # Should not require authentication
            assert response.status_code == 200
    
    def test_other_endpoints_require_auth(self):
        """Test that non-MLflow endpoints still require authentication."""
        client = TestClient(app)
        
        # Try to access a protected endpoint without auth
        response = client.get("/api/v1/models")
        
        # Should require authentication
        assert response.status_code == 401
        assert "API key required" in response.json()["detail"]
    
    def test_mlflow_health_check_endpoint(self):
        """Test the MLflow health check endpoint."""
        client = TestClient(app)
        
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            response = client.get("/mlflow/health/mlflow")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "mlflow_server" in data


class TestMLflowProxy:
    """Test MLflow proxy functionality."""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_proxy_forwards_get_request(self, client):
        """Test that proxy forwards GET requests correctly."""
        with patch('httpx.AsyncClient.request') as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b'{"test": "data"}'
            mock_response.headers = {"content-type": "application/json"}
            mock_request.return_value = mock_response
            
            response = client.get("/mlflow/api/2.0/mlflow/experiments/list")
            
            # Verify request was forwarded
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            
            assert call_args[1]["method"] == "get"
            assert "api/2.0/mlflow/experiments/list" in call_args[1]["url"]
            
            # Verify response
            assert response.status_code == 200
            assert response.json() == {"test": "data"}
    
    def test_proxy_forwards_post_request_with_body(self, client):
        """Test that proxy forwards POST requests with body."""
        request_body = {"name": "test_experiment"}
        
        with patch('httpx.AsyncClient.request') as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b'{"experiment_id": "123"}'
            mock_response.headers = {}
            mock_request.return_value = mock_response
            
            response = client.post(
                "/mlflow/api/2.0/mlflow/experiments/create",
                json=request_body
            )
            
            # Verify request was forwarded with body
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            
            assert call_args[1]["method"] == "post"
            assert call_args[1]["content"] is not None
            
            # Verify response
            assert response.status_code == 200
    
    def test_proxy_strips_auth_headers(self, client):
        """Test that proxy removes authentication headers."""
        with patch('httpx.AsyncClient.request') as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b'{}'
            mock_response.headers = {}
            mock_request.return_value = mock_response
            
            # Send request with auth headers
            headers = {
                "Authorization": "Bearer test-key",
                "X-API-Key": "test-key",
                "User-Agent": "test-client"
            }
            
            response = client.get("/mlflow/test", headers=headers)
            
            # Verify auth headers were stripped
            call_args = mock_request.call_args
            forwarded_headers = call_args[1]["headers"]
            
            assert "authorization" not in forwarded_headers
            assert "x-api-key" not in forwarded_headers
            assert "user-agent" in forwarded_headers  # Other headers preserved
    
    def test_proxy_handles_mlflow_timeout(self, client):
        """Test proxy handles MLflow server timeout."""
        with patch('httpx.AsyncClient.request') as mock_request:
            mock_request.side_effect = httpx.TimeoutException("Request timed out")
            
            response = client.get("/mlflow/api/test")
            
            assert response.status_code == 504
            assert "timeout" in response.json()["detail"].lower()
    
    def test_proxy_handles_mlflow_connection_error(self, client):
        """Test proxy handles MLflow server connection error."""
        with patch('httpx.AsyncClient.request') as mock_request:
            mock_request.side_effect = httpx.ConnectError("Connection refused")
            
            response = client.get("/mlflow/api/test")
            
            assert response.status_code == 502
            assert "connect" in response.json()["detail"].lower()
    
    def test_proxy_preserves_query_parameters(self, client):
        """Test that proxy preserves query parameters."""
        with patch('httpx.AsyncClient.request') as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b'{}'
            mock_response.headers = {}
            mock_request.return_value = mock_response
            
            response = client.get("/mlflow/api/test?param1=value1&param2=value2")
            
            # Verify query params were forwarded
            call_args = mock_request.call_args
            assert call_args[1]["params"] == {"param1": "value1", "param2": "value2"}


class TestExperimentManagerMLflowConfig:
    """Test ExperimentManager MLflow configuration."""
    
    def test_experiment_manager_sets_tracking_uri(self):
        """Test that ExperimentManager configures MLflow tracking URI."""
        import sys
        import os
        
        # Add SDK to path
        sdk_path = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            "hokusai-ml-platform", 
            "src"
        )
        sys.path.insert(0, sdk_path)
        
        with patch('mlflow.set_tracking_uri') as mock_set_uri:
            with patch('mlflow.get_experiment_by_name', return_value=None):
                with patch('mlflow.create_experiment'):
                    with patch('mlflow.set_experiment'):
                        from hokusai.tracking import ExperimentManager
                        
                        # Test default URI
                        manager = ExperimentManager()
                        mock_set_uri.assert_called_with("http://registry.hokus.ai/mlflow")
                        
                        # Test custom URI
                        custom_uri = "http://custom-mlflow.com"
                        manager = ExperimentManager(mlflow_tracking_uri=custom_uri)
                        mock_set_uri.assert_called_with(custom_uri)
    
    def test_experiment_manager_mock_mode(self):
        """Test ExperimentManager in mock mode."""
        import os
        os.environ["HOKUSAI_MOCK_MODE"] = "true"
        
        try:
            import sys
            sdk_path = os.path.join(
                os.path.dirname(__file__), 
                "..", 
                "hokusai-ml-platform", 
                "src"
            )
            sys.path.insert(0, sdk_path)
            
            from hokusai.tracking import ExperimentManager
            
            # Should initialize without MLflow connection
            manager = ExperimentManager()
            assert manager.mock_mode is True
            
            # Test mock methods
            run_id = manager.create_improvement_experiment("baseline_123", {})
            assert run_id is not None
            
            comparison = manager.compare_models("model1", "model2", {"dataset_name": "test"})
            assert "baseline_metrics" in comparison
            assert "recommendation" in comparison
            
        finally:
            os.environ.pop("HOKUSAI_MOCK_MODE", None)