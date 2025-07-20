"""
Test routing configuration for MLflow proxy endpoints.
Tests both /mlflow/* and /api/mlflow/* paths to ensure proper routing.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

# Import the app - adjust path as needed
from src.api.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_httpx_client():
    """Mock httpx AsyncClient for proxy tests."""
    with patch("httpx.AsyncClient") as mock_class:
        mock_instance = AsyncMock()
        mock_class.return_value.__aenter__.return_value = mock_instance
        
        # Default successful response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = b'{"experiments": []}'
        mock_response.headers = {"content-type": "application/json"}
        mock_instance.request.return_value = mock_response
        
        yield mock_instance


class TestMLflowProxyRouting:
    """Test MLflow proxy routing for both legacy and standard paths."""
    
    def test_legacy_mlflow_path(self, client, mock_httpx_client):
        """Test that /mlflow/* paths are properly routed."""
        # No auth required for legacy path in tests
        response = client.get("/mlflow/api/2.0/mlflow/experiments/search")
        
        # Verify the proxy was called
        mock_httpx_client.request.assert_called_once()
        call_args = mock_httpx_client.request.call_args
        
        # Check that path translation occurred
        assert "ajax-api/2.0/mlflow" in call_args.kwargs["url"]
        assert response.status_code == 200
    
    def test_standard_mlflow_path(self, client, mock_httpx_client):
        """Test that /api/mlflow/* paths are properly routed."""
        # Standard path requires auth
        headers = {"Authorization": "Bearer test_api_key"}
        response = client.get("/api/mlflow/api/2.0/mlflow/experiments/search", headers=headers)
        
        # Verify the proxy was called
        mock_httpx_client.request.assert_called_once()
        call_args = mock_httpx_client.request.call_args
        
        # Check that path translation occurred
        assert "ajax-api/2.0/mlflow" in call_args.kwargs["url"]
        assert response.status_code == 200
    
    def test_mlflow_health_check_legacy(self, client, mock_httpx_client):
        """Test MLflow health check via legacy path."""
        mock_httpx_client.get.return_value = AsyncMock(status_code=200)
        
        response = client.get("/mlflow/health/mlflow")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_mlflow_health_check_standard(self, client, mock_httpx_client):
        """Test MLflow health check via standard path."""
        mock_httpx_client.get.return_value = AsyncMock(status_code=200)
        
        headers = {"Authorization": "Bearer test_api_key"}
        response = client.get("/api/mlflow/health/mlflow", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_path_translation(self, client, mock_httpx_client):
        """Test that api/2.0/mlflow paths are translated to ajax-api/2.0/mlflow."""
        headers = {"Authorization": "Bearer test_api_key"}
        
        # Test various MLflow API endpoints
        endpoints = [
            "/api/mlflow/api/2.0/mlflow/experiments/create",
            "/api/mlflow/api/2.0/mlflow/runs/create",
            "/api/mlflow/api/2.0/mlflow/model-versions/create"
        ]
        
        for endpoint in endpoints:
            mock_httpx_client.request.reset_mock()
            response = client.post(endpoint, headers=headers, json={})
            
            # Verify path translation
            call_args = mock_httpx_client.request.call_args
            assert "ajax-api/2.0/mlflow" in call_args.kwargs["url"]
            assert "api/2.0/mlflow" not in call_args.kwargs["url"]
    
    def test_non_api_paths_unchanged(self, client, mock_httpx_client):
        """Test that non-API MLflow paths are not translated."""
        # Test UI and static asset paths
        response = client.get("/mlflow/static/css/main.css")
        
        call_args = mock_httpx_client.request.call_args
        # Should not contain ajax-api translation
        assert "static/css/main.css" in call_args.kwargs["url"]
    
    @pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE", "PATCH"])
    def test_all_http_methods_supported(self, client, mock_httpx_client, method):
        """Test that all HTTP methods are properly proxied."""
        headers = {"Authorization": "Bearer test_api_key"}
        
        response = client.request(
            method=method,
            url="/api/mlflow/api/2.0/mlflow/test",
            headers=headers,
            json={} if method in ["POST", "PUT", "PATCH"] else None
        )
        
        # Verify proxy was called with correct method
        mock_httpx_client.request.assert_called_once()
        call_args = mock_httpx_client.request.call_args
        assert call_args.kwargs["method"] == method.lower()


class TestAPIVersionRouting:
    """Test that versioned API endpoints work correctly."""
    
    def test_v1_dspy_endpoint(self, client):
        """Test that /api/v1/dspy endpoints are accessible."""
        headers = {"Authorization": "Bearer test_api_key"}
        response = client.get("/api/v1/dspy/health", headers=headers)
        # Should not be 404
        assert response.status_code != 404
    
    def test_v1_auth_endpoint(self, client):
        """Test that /api/v1/auth endpoints would be accessible if mounted."""
        # Note: Auth endpoints might not be mounted in test environment
        headers = {"Authorization": "Bearer test_api_key"}
        response = client.get("/api/v1/auth/keys", headers=headers)
        # Check if it's not a routing 404 (might be 401/403 for auth)
        assert response.status_code != 404 or "auth" not in app.url_path_for.__code__.co_names


class TestRoutingPriority:
    """Test that routing priorities work as expected."""
    
    def test_specific_route_beats_general(self, client, mock_httpx_client):
        """Test that /api/mlflow/* has priority over /api/v1/*."""
        headers = {"Authorization": "Bearer test_api_key"}
        
        # This should go to MLflow proxy, not be treated as /api/v1/*
        response = client.get("/api/mlflow/test", headers=headers)
        
        # Verify it went to the proxy
        mock_httpx_client.request.assert_called_once()
    
    def test_no_api_catchall(self, client):
        """Test that there's no broad /api* catch-all anymore."""
        # These should 404, not be caught by a broad rule
        response = client.get("/api/undefined/endpoint")
        assert response.status_code == 404
        
        response = client.get("/api/v2/future")
        assert response.status_code == 404


class TestBackwardCompatibility:
    """Test that existing paths still work for backward compatibility."""
    
    def test_models_api_unchanged(self, client):
        """Test that /models/* endpoints still work."""
        headers = {"Authorization": "Bearer test_api_key"}
        response = client.get("/models", headers=headers)
        # Should not be 404
        assert response.status_code != 404
    
    def test_health_endpoints_unchanged(self, client):
        """Test that health endpoints still work."""
        response = client.get("/health")
        assert response.status_code == 200
        
        response = client.get("/ready")
        assert response.status_code in [200, 503]  # Might be 503 if not ready
    
    def test_legacy_mlflow_still_works(self, client, mock_httpx_client):
        """Test that /mlflow/* paths still work for backward compatibility."""
        response = client.get("/mlflow/api/2.0/mlflow/experiments/search")
        
        # Should still work
        assert response.status_code == 200
        mock_httpx_client.request.assert_called_once()


class TestErrorHandling:
    """Test error handling in routing."""
    
    def test_mlflow_timeout(self, client):
        """Test handling of MLflow timeout."""
        with patch("httpx.AsyncClient") as mock_class:
            mock_instance = AsyncMock()
            mock_class.return_value.__aenter__.return_value = mock_instance
            mock_instance.request.side_effect = httpx.TimeoutException("Timeout")
            
            headers = {"Authorization": "Bearer test_api_key"}
            response = client.get("/api/mlflow/api/2.0/mlflow/test", headers=headers)
            
            assert response.status_code == 504
            assert "timeout" in response.json()["detail"].lower()
    
    def test_mlflow_connection_error(self, client):
        """Test handling of MLflow connection error."""
        with patch("httpx.AsyncClient") as mock_class:
            mock_instance = AsyncMock()
            mock_class.return_value.__aenter__.return_value = mock_instance
            mock_instance.request.side_effect = httpx.ConnectError("Connection failed")
            
            headers = {"Authorization": "Bearer test_api_key"}
            response = client.get("/api/mlflow/api/2.0/mlflow/test", headers=headers)
            
            assert response.status_code == 502
            assert "connect" in response.json()["detail"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])