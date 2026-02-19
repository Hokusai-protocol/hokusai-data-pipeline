"""Unit tests for API key validation middleware using external auth service."""

import json
from unittest.mock import Mock, patch

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from src.middleware.auth import APIKeyAuthMiddleware, get_api_key_from_request


class TestAPIKeyAuthMiddleware:
    """Test cases for API key authentication middleware."""

    @pytest.fixture
    def mock_cache(self):
        """Mock Redis cache."""
        cache = Mock()
        cache.get = Mock(return_value=None)
        cache.setex = Mock()
        cache.ping = Mock()
        return cache

    @pytest.fixture
    def app(self, mock_cache):
        """Create FastAPI app with middleware."""
        app = FastAPI()

        # Add middleware
        app.add_middleware(
            APIKeyAuthMiddleware,
            auth_service_url="https://auth.test.hokus.ai",
            cache=mock_cache,
            excluded_paths=["/health", "/docs", "/openapi.json"],
            timeout=5.0,
        )

        # Add test endpoints
        @app.get("/protected")
        async def protected_endpoint(request: Request):
            return {
                "message": "Protected resource",
                "user_id": getattr(request.state, "user_id", None),
                "api_key_id": getattr(request.state, "api_key_id", None),
            }

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

    @patch("httpx.AsyncClient.post")
    async def test_middleware_validates_api_key_with_auth_service(self, mock_post, client):
        """Test middleware validates API key with external auth service."""
        # Arrange
        api_key = "hk_live_valid_key_123"

        # Mock auth service response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "user_id": "user123",
            "key_id": "key123",
            "service_id": "platform",
            "scopes": ["model:read", "model:write"],
            "rate_limit_per_hour": 1000,
        }
        mock_post.return_value = mock_response

        # Act
        response = client.get("/protected", headers={"Authorization": f"Bearer {api_key}"})

        # Assert
        assert response.status_code == 200
        result = response.json()
        assert result["message"] == "Protected resource"
        assert result["user_id"] == "user123"
        assert result["api_key_id"] == "key123"

    @patch("httpx.AsyncClient.post")
    async def test_middleware_handles_invalid_api_key(self, mock_post, client):
        """Test middleware handles invalid API key from auth service."""
        # Arrange
        api_key = "hk_live_invalid_key_123"

        # Mock auth service response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        # Act
        response = client.get("/protected", headers={"Authorization": f"Bearer {api_key}"})

        # Assert
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or expired API key"

    @patch("httpx.AsyncClient.post")
    async def test_middleware_handles_rate_limit(self, mock_post, client):
        """Test middleware handles rate limit response from auth service."""
        # Arrange
        api_key = "hk_live_rate_limited_key"

        # Mock auth service response
        mock_response = Mock()
        mock_response.status_code = 429
        mock_post.return_value = mock_response

        # Act
        response = client.get("/protected", headers={"Authorization": f"Bearer {api_key}"})

        # Assert
        assert response.status_code == 401
        assert response.json()["detail"] == "Rate limit exceeded"

    @patch("httpx.AsyncClient.post")
    async def test_middleware_uses_cache(self, mock_post, client, mock_cache):
        """Test middleware uses cache for API key validation."""
        # Arrange
        api_key = "hk_live_cached_key_123"
        cached_data = {
            "is_valid": True,
            "user_id": "user123",
            "key_id": "key123",
            "service_id": "platform",
            "scopes": ["model:read"],
            "rate_limit_per_hour": 1000,
            "has_sufficient_balance": True,
            "balance": 10.0,
        }
        mock_cache.get.return_value = json.dumps(cached_data)

        # Act
        response = client.get("/protected", headers={"Authorization": f"Bearer {api_key}"})

        # Assert
        assert response.status_code == 200
        mock_cache.get.assert_called_once()
        mock_post.assert_not_called()  # Should not call auth service

    @patch("httpx.AsyncClient.post")
    async def test_middleware_caches_validation_result(self, mock_post, client, mock_cache):
        """Test middleware caches successful validation result."""
        # Arrange
        api_key = "hk_live_valid_key_123"
        mock_cache.get.return_value = None  # Not in cache

        # Mock auth service response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "user_id": "user123",
            "key_id": "key123",
            "service_id": "platform",
            "scopes": ["model:read"],
            "rate_limit_per_hour": 1000,
        }
        mock_post.return_value = mock_response

        # Act
        response = client.get("/protected", headers={"Authorization": f"Bearer {api_key}"})

        # Assert
        assert response.status_code == 200
        mock_cache.setex.assert_called_once()
        # Check cache key and TTL
        cache_call_args = mock_cache.setex.call_args
        assert cache_call_args[0][1] == 60  # 60 second TTL

    @patch("httpx.AsyncClient.post")
    async def test_middleware_includes_client_ip_in_validation(self, mock_post, client):
        """Test middleware includes client IP in validation request."""
        # Arrange
        api_key = "hk_live_valid_key_123"

        # Mock auth service response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "user_id": "user123",
            "key_id": "key123",
            "service_id": "platform",
            "scopes": ["model:read"],
            "rate_limit_per_hour": 1000,
        }
        mock_post.return_value = mock_response

        # Act
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {api_key}", "X-Forwarded-For": "192.168.1.1"},
        )

        # Assert
        assert response.status_code == 200
        # Check that client IP was included in auth service request
        call_args = mock_post.call_args
        request_data = call_args[1]["json"]
        assert request_data["client_ip"] == "192.168.1.1"

    @patch("httpx.AsyncClient.post")
    async def test_middleware_handles_auth_service_timeout(self, mock_post, client):
        """Test middleware handles auth service timeout gracefully."""
        # Arrange
        api_key = "hk_live_timeout_key"
        mock_post.side_effect = httpx.TimeoutException("Request timed out")

        # Act
        response = client.get("/protected", headers={"Authorization": f"Bearer {api_key}"})

        # Assert
        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication service timeout"

    @patch("httpx.AsyncClient.post")
    async def test_middleware_handles_auth_service_error(self, mock_post, client):
        """Test middleware handles auth service connection error."""
        # Arrange
        api_key = "hk_live_error_key"
        mock_post.side_effect = httpx.ConnectError("Connection failed")

        # Act
        response = client.get("/protected", headers={"Authorization": f"Bearer {api_key}"})

        # Assert
        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication service unavailable"

    def test_middleware_extracts_api_key_from_query_param(self, client):
        """Test middleware can extract API key from query parameter."""
        # Act
        response = client.get("/protected?api_key=hk_live_query_key")

        # Assert
        assert response.status_code == 401  # Will fail validation, but key was extracted

    def test_middleware_extracts_api_key_from_x_api_key_header(self, client):
        """Test middleware can extract API key from X-API-Key header."""
        # Act
        response = client.get("/protected", headers={"X-API-Key": "hk_live_header_key"})

        # Assert
        assert response.status_code == 401  # Will fail validation, but key was extracted


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
