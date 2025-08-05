"""Integration tests for MLflow proxy routing to verify PR #60 fixes."""

import os
import pytest
import httpx
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock
import json

# Import the app after mocking environment variables
with patch.dict(os.environ, {
    "MLFLOW_SERVER_URL": "http://mlflow.test.local:5000",
    "MLFLOW_SERVE_ARTIFACTS": "true",
    "MLFLOW_PROXY_DEBUG": "true"
}):
    from src.api.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Mock authentication headers."""
    return {"Authorization": "Bearer test-api-key"}


class TestMLflowProxyIntegration:
    """Integration tests for MLflow proxy routing."""
    
    def test_mlflow_proxy_model_registration_flow(self, client, auth_headers):
        """Test the complete model registration flow through the proxy."""
        # Mock the auth middleware to accept our test key
        with patch('src.middleware.auth.APIKeyAuthMiddleware.__call__') as mock_auth:
            async def mock_call(request, call_next):
                request.state.user_id = "test-user"
                request.state.api_key_id = "test-key"
                response = await call_next(request)
                return response
            mock_auth.side_effect = mock_call
            
            # Mock httpx client for MLflow requests
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                
                # Test 1: Create registered model
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.content = json.dumps({
                    "registered_model": {
                        "name": "test-model",
                        "creation_timestamp": 1234567890
                    }
                }).encode()
                mock_response.headers = {"content-type": "application/json"}
                mock_client.request.return_value = mock_response
                
                response = client.post(
                    "/mlflow/api/2.0/mlflow/registered-models/create",
                    json={"name": "test-model"},
                    headers=auth_headers
                )
                
                assert response.status_code == 200
                assert response.json()["registered_model"]["name"] == "test-model"
                
                # Verify the request was proxied correctly
                mock_client.request.assert_called()
                call_args = mock_client.request.call_args
                assert call_args[1]['url'] == 'http://mlflow.test.local:5000/api/2.0/mlflow/registered-models/create'
                assert call_args[1]['method'] == 'post'
    
    def test_mlflow_proxy_experiment_tracking(self, client, auth_headers):
        """Test experiment tracking through the proxy."""
        with patch('src.middleware.auth.APIKeyAuthMiddleware.__call__') as mock_auth:
            async def mock_call(request, call_next):
                request.state.user_id = "test-user"
                request.state.api_key_id = "test-key"
                response = await call_next(request)
                return response
            mock_auth.side_effect = mock_call
            
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                
                # Test searching experiments
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.content = json.dumps({
                    "experiments": [
                        {"experiment_id": "1", "name": "test-exp"}
                    ]
                }).encode()
                mock_response.headers = {"content-type": "application/json"}
                mock_client.request.return_value = mock_response
                
                response = client.get(
                    "/api/mlflow/api/2.0/mlflow/experiments/search",
                    headers=auth_headers
                )
                
                assert response.status_code == 200
                assert len(response.json()["experiments"]) == 1
                
                # Verify correct API path was used (not ajax-api)
                call_args = mock_client.request.call_args
                assert "/api/2.0/mlflow/experiments/search" in call_args[1]['url']
                assert "/ajax-api/" not in call_args[1]['url']
    
    def test_mlflow_proxy_artifact_download(self, client, auth_headers):
        """Test artifact download through the proxy."""
        with patch('src.middleware.auth.APIKeyAuthMiddleware.__call__') as mock_auth:
            async def mock_call(request, call_next):
                request.state.user_id = "test-user"
                request.state.api_key_id = "test-key"
                response = await call_next(request)
                return response
            mock_auth.side_effect = mock_call
            
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                
                # Mock artifact response
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.content = b"model artifact data"
                mock_response.headers = {"content-type": "application/octet-stream"}
                mock_client.request.return_value = mock_response
                
                response = client.get(
                    "/mlflow/api/2.0/mlflow-artifacts/artifacts/run123/model.pkl",
                    headers=auth_headers
                )
                
                assert response.status_code == 200
                assert response.content == b"model artifact data"
    
    def test_mlflow_proxy_external_registry_routing(self, client, auth_headers):
        """Test routing to external MLflow registry (ajax-api conversion)."""
        with patch('src.middleware.auth.APIKeyAuthMiddleware.__call__') as mock_auth:
            async def mock_call(request, call_next):
                request.state.user_id = "test-user"
                request.state.api_key_id = "test-key"
                response = await call_next(request)
                return response
            mock_auth.side_effect = mock_call
            
            # Mock external MLflow URL
            with patch('src.api.routes.mlflow_proxy_improved.MLFLOW_SERVER_URL', 
                      'https://registry.hokus.ai/mlflow'):
                with patch('httpx.AsyncClient') as mock_client_class:
                    mock_client = AsyncMock()
                    mock_client_class.return_value.__aenter__.return_value = mock_client
                    
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.content = json.dumps({"models": []}).encode()
                    mock_response.headers = {"content-type": "application/json"}
                    mock_client.request.return_value = mock_response
                    
                    response = client.get(
                        "/mlflow/api/2.0/mlflow/registered-models/search",
                        headers=auth_headers
                    )
                    
                    assert response.status_code == 200
                    
                    # Verify ajax-api conversion happened for external URL
                    call_args = mock_client.request.call_args
                    assert "/ajax-api/2.0/mlflow/" in call_args[1]['url']
    
    def test_mlflow_proxy_user_context_headers(self, client, auth_headers):
        """Test that user context headers are added to MLflow requests."""
        with patch('src.middleware.auth.APIKeyAuthMiddleware.__call__') as mock_auth:
            async def mock_call(request, call_next):
                request.state.user_id = "user-123"
                request.state.api_key_id = "key-456"
                response = await call_next(request)
                return response
            mock_auth.side_effect = mock_call
            
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.content = b"{}"
                mock_response.headers = {}
                mock_client.request.return_value = mock_response
                
                client.get("/mlflow/api/2.0/mlflow/experiments/list", headers=auth_headers)
                
                # Verify user context headers were added
                call_args = mock_client.request.call_args
                headers = call_args[1]['headers']
                assert headers['X-Hokusai-User-Id'] == 'user-123'
                assert headers['X-Hokusai-API-Key-Id'] == 'key-456'
    
    def test_mlflow_proxy_auth_header_removal(self, client, auth_headers):
        """Test that Hokusai auth headers are not forwarded to MLflow."""
        with patch('src.middleware.auth.APIKeyAuthMiddleware.__call__') as mock_auth:
            async def mock_call(request, call_next):
                request.state.user_id = "test-user"
                request.state.api_key_id = "test-key"
                response = await call_next(request)
                return response
            mock_auth.side_effect = mock_call
            
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.content = b"{}"
                mock_response.headers = {}
                mock_client.request.return_value = mock_response
                
                # Add extra auth headers
                headers = auth_headers.copy()
                headers["X-API-Key"] = "hokusai-secret-key"
                
                client.get("/mlflow/api/2.0/mlflow/experiments/list", headers=headers)
                
                # Verify auth headers were removed
                call_args = mock_client.request.call_args
                forwarded_headers = call_args[1]['headers']
                assert 'authorization' not in forwarded_headers
                assert 'x-api-key' not in forwarded_headers
    
    def test_mlflow_health_check_endpoint(self, client):
        """Test the MLflow health check endpoint."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Mock health check responses
            mock_client.get.side_effect = [
                Mock(status_code=200),  # Basic connectivity
                Mock(status_code=200, text='{"experiments": []}')  # API check
            ]
            
            response = client.get("/mlflow/health/mlflow")
            
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'healthy'
            assert data['checks']['connectivity']['status'] == 'healthy'
            assert data['checks']['experiments_api']['status'] == 'healthy'
    
    def test_mlflow_detailed_health_check(self, client):
        """Test the detailed MLflow health check endpoint."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Mock responses for various endpoints
            mock_client.request.side_effect = [
                Mock(status_code=200, elapsed=Mock(total_seconds=lambda: 0.1)),
                Mock(status_code=200, elapsed=Mock(total_seconds=lambda: 0.2)),
                Mock(status_code=200, elapsed=Mock(total_seconds=lambda: 0.15))
            ]
            
            response = client.get("/mlflow/health/mlflow/detailed")
            
            assert response.status_code == 200
            data = response.json()
            assert data['overall_health'] is True
            assert len(data['tests']) == 3
            assert all(test['success'] for test in data['tests'])
    
    def test_mlflow_proxy_error_handling(self, client, auth_headers):
        """Test error handling in the MLflow proxy."""
        with patch('src.middleware.auth.APIKeyAuthMiddleware.__call__') as mock_auth:
            async def mock_call(request, call_next):
                request.state.user_id = "test-user"
                request.state.api_key_id = "test-key"
                response = await call_next(request)
                return response
            mock_auth.side_effect = mock_call
            
            # Test timeout error
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                mock_client.request.side_effect = httpx.TimeoutException("Timeout")
                
                response = client.get("/mlflow/api/2.0/mlflow/experiments/list", headers=auth_headers)
                assert response.status_code == 504
                assert "timeout" in response.json()["detail"].lower()
            
            # Test connection error
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                mock_client.request.side_effect = httpx.ConnectError("Connection refused")
                
                response = client.get("/mlflow/api/2.0/mlflow/experiments/list", headers=auth_headers)
                assert response.status_code == 502
                assert "Failed to connect" in response.json()["detail"]