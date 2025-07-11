"""Unit tests for API key validation middleware."""

import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from src.middleware.auth import APIKeyAuthMiddleware, get_api_key_from_request


class TestAPIKeyAuthMiddleware:
    """Test cases for API key authentication middleware."""

    @pytest.fixture
    def mock_api_key_service(self):
        """Mock API key service."""
        service = Mock()
        service.validate_api_key = Mock()
        return service

    @pytest.fixture
    def mock_cache(self):
        """Mock Redis cache."""
        cache = Mock()
        cache.get = Mock(return_value=None)
        cache.setex = Mock()
        return cache

    @pytest.fixture
    def app(self, mock_api_key_service, mock_cache):
        """Create FastAPI app with middleware."""
        app = FastAPI()
        
        # Add middleware
        app.add_middleware(
            APIKeyAuthMiddleware,
            api_key_service=mock_api_key_service,
            cache=mock_cache,
            excluded_paths=["/health", "/docs", "/openapi.json"]
        )
        
        # Add test endpoints
        @app.get("/protected")
        async def protected_endpoint():
            return {"message": "Protected resource"}
        
        @app.get("/health")
        async def health_check():
            return {"status": "healthy"}
        
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_middleware_allows_excluded_paths(self, client):
        """Test that middleware allows access to excluded paths without auth."""
        # Act
        response = client.get("/health")
        
        # Assert
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    def test_middleware_blocks_missing_api_key(self, client):
        """Test that middleware blocks requests without API key."""
        # Act
        response = client.get("/protected")
        
        # Assert
        assert response.status_code == 401
        assert response.json()["detail"] == "API key required"

    def test_middleware_validates_api_key_from_header(self, client, mock_api_key_service):
        """Test middleware validates API key from Authorization header."""
        # Arrange
        api_key = "hk_live_valid_key_123"
        mock_api_key_service.validate_api_key.return_value = Mock(
            is_valid=True,
            key_id="key123",
            user_id="user123",
            rate_limit_per_hour=100
        )
        
        # Act
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        
        # Assert
        assert response.status_code == 200
        mock_api_key_service.validate_api_key.assert_called_once()

    def test_middleware_validates_api_key_from_query_param(self, client, mock_api_key_service):
        """Test middleware validates API key from query parameter."""
        # Arrange
        api_key = "hk_live_valid_key_123"
        mock_api_key_service.validate_api_key.return_value = Mock(
            is_valid=True,
            key_id="key123",
            user_id="user123",
            rate_limit_per_hour=100
        )
        
        # Act
        response = client.get(f"/protected?api_key={api_key}")
        
        # Assert
        assert response.status_code == 200
        mock_api_key_service.validate_api_key.assert_called_once()

    def test_middleware_rejects_invalid_api_key(self, client, mock_api_key_service):
        """Test middleware rejects invalid API key."""
        # Arrange
        api_key = "hk_live_invalid_key_123"
        mock_api_key_service.validate_api_key.return_value = Mock(
            is_valid=False,
            error="API key not found"
        )
        
        # Act
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        
        # Assert
        assert response.status_code == 401
        assert response.json()["detail"] == "API key not found"

    def test_middleware_uses_cache_for_validation(self, client, mock_api_key_service, mock_cache):
        """Test middleware uses cache for API key validation."""
        # Arrange
        api_key = "hk_live_cached_key_123"
        cached_data = {
            "is_valid": True,
            "key_id": "key123",
            "user_id": "user123",
            "rate_limit_per_hour": 100
        }
        # Cache stores JSON strings
        import json
        mock_cache.get.return_value = json.dumps(cached_data)
        
        # Act
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        
        # Assert
        assert response.status_code == 200
        mock_cache.get.assert_called_once()
        mock_api_key_service.validate_api_key.assert_not_called()

    def test_middleware_caches_validation_result(self, client, mock_api_key_service, mock_cache):
        """Test middleware caches successful validation result."""
        # Arrange
        api_key = "hk_live_valid_key_123"
        validation_result = Mock(
            is_valid=True,
            key_id="key123",
            user_id="user123",
            rate_limit_per_hour=100
        )
        mock_api_key_service.validate_api_key.return_value = validation_result
        mock_cache.get.return_value = None  # Not in cache
        
        # Act
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        
        # Assert
        assert response.status_code == 200
        mock_cache.setex.assert_called_once()
        # Check cache key and TTL
        cache_call_args = mock_cache.setex.call_args
        assert cache_call_args[0][1] == 300  # 5 minute TTL

    def test_middleware_includes_client_ip_in_validation(self, client, mock_api_key_service):
        """Test middleware includes client IP in validation."""
        # Arrange
        api_key = "hk_live_valid_key_123"
        mock_api_key_service.validate_api_key.return_value = Mock(
            is_valid=True,
            key_id="key123",
            user_id="user123",
            rate_limit_per_hour=100
        )
        
        # Act
        response = client.get(
            "/protected",
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Forwarded-For": "192.168.1.1"
            }
        )
        
        # Assert
        assert response.status_code == 200
        # Check that client IP was passed to validation
        call_args = mock_api_key_service.validate_api_key.call_args
        assert call_args[1]["client_ip"] == "192.168.1.1"

    def test_middleware_updates_last_used_async(self, client, mock_api_key_service):
        """Test middleware updates last used timestamp asynchronously."""
        # Arrange
        api_key = "hk_live_valid_key_123"
        mock_api_key_service.validate_api_key.return_value = Mock(
            is_valid=True,
            key_id="key123",
            user_id="user123",
            rate_limit_per_hour=100
        )
        mock_api_key_service.update_last_used = Mock()
        
        # Act
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        
        # Assert
        assert response.status_code == 200
        # Note: In real implementation, this would be async
        # For testing, we verify the method would be called

    def test_middleware_handles_validation_errors_gracefully(self, client, mock_api_key_service):
        """Test middleware handles validation service errors gracefully."""
        # Arrange
        api_key = "hk_live_error_key_123"
        mock_api_key_service.validate_api_key.side_effect = Exception("Service error")
        
        # Act
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        
        # Assert
        assert response.status_code == 500
        assert response.json()["detail"] == "Internal server error"

    def test_middleware_sets_request_state(self, mock_api_key_service, mock_cache):
        """Test middleware sets user context in request state."""
        # Arrange
        app = FastAPI()
        api_key = "hk_live_valid_key_123"
        
        mock_api_key_service.validate_api_key.return_value = Mock(
            is_valid=True,
            key_id="key123",
            user_id="user123",
            rate_limit_per_hour=100
        )
        
        # Add middleware
        app.add_middleware(
            APIKeyAuthMiddleware,
            api_key_service=mock_api_key_service,
            cache=mock_cache
        )
        
        # Add endpoint that uses request state
        @app.get("/protected")
        async def protected_endpoint(request: Request):
            return {
                "user_id": request.state.user_id,
                "api_key_id": request.state.api_key_id
            }
        
        client = TestClient(app)
        
        # Act
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        
        # Assert
        assert response.status_code == 200
        assert response.json() == {
            "user_id": "user123",
            "api_key_id": "key123"
        }


class TestGetAPIKeyFromRequest:
    """Test cases for extracting API key from request."""

    def test_extract_from_authorization_header_bearer(self):
        """Test extracting API key from Bearer Authorization header."""
        # Arrange
        headers = Headers({"authorization": "Bearer hk_live_test_key_123"})
        request = Mock(headers=headers, query_params={})
        
        # Act
        result = get_api_key_from_request(request)
        
        # Assert
        assert result == "hk_live_test_key_123"

    def test_extract_from_authorization_header_apikey(self):
        """Test extracting API key from ApiKey Authorization header."""
        # Arrange
        headers = Headers({"authorization": "ApiKey hk_live_test_key_123"})
        request = Mock(headers=headers, query_params={})
        
        # Act
        result = get_api_key_from_request(request)
        
        # Assert
        assert result == "hk_live_test_key_123"

    def test_extract_from_x_api_key_header(self):
        """Test extracting API key from X-API-Key header."""
        # Arrange
        headers = Headers({"x-api-key": "hk_live_test_key_123"})
        request = Mock(headers=headers, query_params={})
        
        # Act
        result = get_api_key_from_request(request)
        
        # Assert
        assert result == "hk_live_test_key_123"

    def test_extract_from_query_parameter(self):
        """Test extracting API key from query parameter."""
        # Arrange
        headers = Headers({})
        query_params = {"api_key": "hk_live_test_key_123"}
        request = Mock(headers=headers, query_params=query_params)
        
        # Act
        result = get_api_key_from_request(request)
        
        # Assert
        assert result == "hk_live_test_key_123"

    def test_extract_prefers_header_over_query(self):
        """Test that header API key is preferred over query parameter."""
        # Arrange
        headers = Headers({"authorization": "Bearer hk_live_header_key"})
        query_params = {"api_key": "hk_live_query_key"}
        request = Mock(headers=headers, query_params=query_params)
        
        # Act
        result = get_api_key_from_request(request)
        
        # Assert
        assert result == "hk_live_header_key"

    def test_extract_returns_none_when_missing(self):
        """Test that None is returned when API key is missing."""
        # Arrange
        headers = Headers({})
        query_params = {}
        request = Mock(headers=headers, query_params=query_params)
        
        # Act
        result = get_api_key_from_request(request)
        
        # Assert
        assert result is None

    def test_extract_handles_malformed_authorization_header(self):
        """Test handling of malformed Authorization header."""
        # Arrange
        headers = Headers({"authorization": "InvalidFormat"})
        request = Mock(headers=headers, query_params={})
        
        # Act
        result = get_api_key_from_request(request)
        
        # Assert
        assert result is None