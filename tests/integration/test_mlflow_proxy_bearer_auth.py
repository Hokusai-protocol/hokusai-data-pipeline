"""Integration test for MLflow proxy with Bearer token authentication."""

import os
import json
from unittest.mock import Mock, patch, AsyncMock

import pytest
import httpx
from fastapi.testclient import TestClient

from src.api.main import app


class TestMLflowProxyBearerAuth:
    """Test Bearer token authentication with MLflow proxy."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def valid_api_key(self):
        """Valid API key for testing."""
        return "hk_live_test_key_123456789"
    
    @pytest.fixture
    def mock_auth_service_response(self, valid_api_key):
        """Mock successful auth service response."""
        return {
            "user_id": "user123",
            "key_id": "key123",
            "service_id": "ml-platform",
            "scopes": ["model:read", "model:write"],
            "rate_limit_per_hour": 1000
        }
    
    @pytest.fixture
    def mock_mlflow_response(self):
        """Mock MLflow experiments response."""
        return {
            "experiments": [
                {
                    "experiment_id": "1",
                    "name": "Default",
                    "artifact_location": "mlflow-artifacts:/1",
                    "lifecycle_stage": "active"
                }
            ]
        }
    
    @patch('httpx.AsyncClient.request')
    @patch('httpx.AsyncClient.post')
    async def test_mlflow_proxy_with_bearer_token(
        self,
        mock_auth_post,
        mock_mlflow_request,
        client,
        valid_api_key,
        mock_auth_service_response,
        mock_mlflow_response
    ):
        """Test that MLflow proxy works with Bearer token authentication."""
        # Mock auth service validation
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = mock_auth_service_response
        mock_auth_post.return_value = auth_response
        
        # Mock MLflow response
        mlflow_response = Mock()
        mlflow_response.status_code = 200
        mlflow_response.json.return_value = mock_mlflow_response
        mlflow_response.content = json.dumps(mock_mlflow_response).encode()
        mlflow_response.headers = {"content-type": "application/json"}
        mock_mlflow_request.return_value = mlflow_response
        
        # Make request to MLflow proxy with Bearer token
        response = client.get(
            "/mlflow/api/2.0/mlflow/experiments/search",
            headers={"Authorization": f"Bearer {valid_api_key}"}
        )
        
        # Assert authentication succeeded
        assert response.status_code == 200
        
        # Assert MLflow was called without auth headers
        mlflow_call_args = mock_mlflow_request.call_args
        headers_sent_to_mlflow = mlflow_call_args[1]["headers"]
        
        # Verify auth headers were stripped
        assert "authorization" not in headers_sent_to_mlflow
        assert "x-api-key" not in headers_sent_to_mlflow
        
        # Verify user context headers were added
        assert headers_sent_to_mlflow.get("X-Hokusai-User-Id") == "user123"
        assert headers_sent_to_mlflow.get("X-Hokusai-API-Key-Id") == "key123"
        
        # Verify response
        assert response.json() == mock_mlflow_response
    
    @patch('httpx.AsyncClient.post')
    async def test_mlflow_proxy_rejects_invalid_bearer_token(
        self,
        mock_auth_post,
        client
    ):
        """Test that MLflow proxy rejects invalid Bearer tokens."""
        # Mock auth service rejection
        auth_response = Mock()
        auth_response.status_code = 401
        mock_auth_post.return_value = auth_response
        
        # Make request with invalid token
        response = client.get(
            "/mlflow/api/2.0/mlflow/experiments/search",
            headers={"Authorization": "Bearer invalid_token"}
        )
        
        # Assert authentication failed
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or expired API key"
    
    @patch('httpx.AsyncClient.request')
    @patch('httpx.AsyncClient.post')
    async def test_mlflow_proxy_handles_streaming_responses(
        self,
        mock_auth_post,
        mock_mlflow_request,
        client,
        valid_api_key,
        mock_auth_service_response
    ):
        """Test that MLflow proxy handles large/streaming responses."""
        # Mock auth service validation
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = mock_auth_service_response
        mock_auth_post.return_value = auth_response
        
        # Mock large MLflow response
        large_content = b"x" * 1024 * 1024  # 1MB response
        mlflow_response = Mock()
        mlflow_response.status_code = 200
        mlflow_response.content = large_content
        mlflow_response.headers = {"content-type": "application/octet-stream"}
        mock_mlflow_request.return_value = mlflow_response
        
        # Make request for model download
        response = client.get(
            "/mlflow/api/2.0/mlflow/model-versions/get-download-uri",
            headers={"Authorization": f"Bearer {valid_api_key}"}
        )
        
        # Assert response handled correctly
        assert response.status_code == 200
        assert len(response.content) == len(large_content)
    
    def test_mlflow_proxy_requires_authentication(self, client):
        """Test that MLflow proxy requires authentication."""
        # Make request without auth
        response = client.get("/mlflow/api/2.0/mlflow/experiments/search")
        
        # Assert authentication required
        assert response.status_code == 401
        assert response.json()["detail"] == "API key required"
    
    @patch('httpx.AsyncClient.request')
    @patch('httpx.AsyncClient.post')
    async def test_mlflow_proxy_preserves_request_body(
        self,
        mock_auth_post,
        mock_mlflow_request,
        client,
        valid_api_key,
        mock_auth_service_response
    ):
        """Test that MLflow proxy preserves POST request body."""
        # Mock auth service validation
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = mock_auth_service_response
        mock_auth_post.return_value = auth_response
        
        # Mock MLflow response
        mlflow_response = Mock()
        mlflow_response.status_code = 200
        mlflow_response.content = b'{"status": "ok"}'
        mlflow_response.headers = {"content-type": "application/json"}
        mock_mlflow_request.return_value = mlflow_response
        
        # Request body
        request_body = {
            "name": "test-experiment",
            "artifact_location": "s3://bucket/path"
        }
        
        # Make POST request
        response = client.post(
            "/mlflow/api/2.0/mlflow/experiments/create",
            headers={"Authorization": f"Bearer {valid_api_key}"},
            json=request_body
        )
        
        # Assert request succeeded
        assert response.status_code == 200
        
        # Verify request body was forwarded
        mlflow_call_args = mock_mlflow_request.call_args
        sent_body = mlflow_call_args[1]["content"]
        assert json.loads(sent_body) == request_body
    
    @patch('httpx.AsyncClient.get')
    async def test_mlflow_health_check_endpoint(
        self,
        mock_get,
        client
    ):
        """Test MLflow health check endpoint."""
        # Mock MLflow health response
        health_response = Mock()
        health_response.status_code = 200
        mock_get.return_value = health_response
        
        # Check health endpoint (no auth required)
        response = client.get("/mlflow/health/mlflow")
        
        # Assert health check succeeded
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert "mlflow_server" in response.json()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])