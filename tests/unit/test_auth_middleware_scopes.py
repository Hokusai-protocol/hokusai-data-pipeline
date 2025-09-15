"""Unit tests for API key scope authorization in auth middleware."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request, Response

from src.middleware.auth import APIKeyAuthMiddleware, ValidationResult


class TestScopeAuthorization:
    """Test scope-based authorization in APIKeyAuthMiddleware."""

    @pytest.fixture
    def mock_app(self):
        """Create a mock ASGI app."""

        async def app(scope, receive, send):
            pass

        return app

    @pytest.fixture
    def middleware(self, mock_app):
        """Create middleware instance with test configuration."""
        return APIKeyAuthMiddleware(
            app=mock_app,
            auth_service_url="http://test-auth-service",
            cache=None,
            excluded_paths=["/health"],
        )

    @pytest.fixture
    def mock_request_read(self):
        """Create mock request for read operation."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/mlflow/api/2.0/mlflow/experiments/search"
        request.method = "GET"
        request.headers = {"authorization": "Bearer test-api-key"}
        request.query_params = {}
        request.client = MagicMock(host="127.0.0.1")
        request.state = MagicMock()
        return request

    @pytest.fixture
    def mock_request_write(self):
        """Create mock request for write operation."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/mlflow/api/2.0/mlflow/runs/create"
        request.method = "POST"
        request.headers = {"authorization": "Bearer test-api-key"}
        request.query_params = {}
        request.client = MagicMock(host="127.0.0.1")
        request.state = MagicMock()
        return request

    @pytest.fixture
    def mock_request_model_register(self):
        """Create mock request for model registration."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/mlflow/api/2.0/mlflow/registered-models/create"
        request.method = "POST"
        request.headers = {"authorization": "Bearer test-api-key"}
        request.query_params = {}
        request.client = MagicMock(host="127.0.0.1")
        request.state = MagicMock()
        return request

    @pytest.mark.asyncio
    async def test_read_operation_with_read_only_scope(self, middleware, mock_request_read):
        """Test that read operations work with read-only scope."""
        # Mock auth service response with read-only scope
        with patch.object(middleware, "validate_with_auth_service") as mock_validate:
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read", "mlflow:read"],
                rate_limit_per_hour=1000,
            )

            # Mock call_next to return success
            async def mock_call_next(request):
                return Response(content="Success", status_code=200)

            response = await middleware.dispatch(mock_request_read, mock_call_next)

            assert response.status_code == 200
            assert mock_request_read.state.scopes == ["model:read", "mlflow:read"]

    @pytest.mark.asyncio
    async def test_write_operation_with_read_only_scope_returns_403(
        self, middleware, mock_request_write
    ):
        """Test that write operations fail with read-only scope."""
        # Mock auth service response with read-only scope
        with patch.object(middleware, "validate_with_auth_service") as mock_validate:
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read", "mlflow:read"],  # No write scope
                rate_limit_per_hour=1000,
            )

            # Mock call_next (shouldn't be called)
            async def mock_call_next(request):
                return Response(content="Should not reach here", status_code=200)

            response = await middleware.dispatch(mock_request_write, mock_call_next)

            # This test will initially FAIL because the middleware doesn't check scopes yet
            assert response.status_code == 403
            assert "insufficient permissions" in response.body.decode().lower()
            assert (
                "model:write" in response.body.decode() or "mlflow:write" in response.body.decode()
            )

    @pytest.mark.asyncio
    async def test_write_operation_with_write_scope_succeeds(self, middleware, mock_request_write):
        """Test that write operations succeed with write scope."""
        # Mock auth service response with write scope
        with patch.object(middleware, "validate_with_auth_service") as mock_validate:
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read", "model:write", "mlflow:access"],
                rate_limit_per_hour=1000,
            )

            # Mock call_next to return success
            async def mock_call_next(request):
                return Response(content="Success", status_code=200)

            response = await middleware.dispatch(mock_request_write, mock_call_next)

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_model_registration_with_read_only_scope_returns_403(
        self, middleware, mock_request_model_register
    ):
        """Test that model registration fails with read-only scope."""
        # Mock auth service response with read-only scope
        with patch.object(middleware, "validate_with_auth_service") as mock_validate:
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read"],  # No write scope
                rate_limit_per_hour=1000,
            )

            # Mock call_next (shouldn't be called)
            async def mock_call_next(request):
                return Response(content="Should not reach here", status_code=200)

            response = await middleware.dispatch(mock_request_model_register, mock_call_next)

            # This test will initially FAIL because the middleware doesn't check scopes yet
            assert response.status_code == 403
            error_body = response.body.decode()
            assert (
                "insufficient permissions" in error_body.lower()
                or "forbidden" in error_body.lower()
            )

    @pytest.mark.asyncio
    async def test_empty_scopes_blocks_write_operations(self, middleware, mock_request_write):
        """Test that empty scopes block write operations."""
        # Mock auth service response with empty scopes
        with patch.object(middleware, "validate_with_auth_service") as mock_validate:
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=[],  # Empty scopes
                rate_limit_per_hour=1000,
            )

            # Mock call_next (shouldn't be called)
            async def mock_call_next(request):
                return Response(content="Should not reach here", status_code=200)

            response = await middleware.dispatch(mock_request_write, mock_call_next)

            # This test will initially FAIL because the middleware doesn't check scopes yet
            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_null_scopes_blocks_write_operations(self, middleware, mock_request_write):
        """Test that null scopes block write operations."""
        # Mock auth service response with null scopes
        with patch.object(middleware, "validate_with_auth_service") as mock_validate:
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=None,  # Null scopes
                rate_limit_per_hour=1000,
            )

            # Mock call_next (shouldn't be called)
            async def mock_call_next(request):
                return Response(content="Should not reach here", status_code=200)

            response = await middleware.dispatch(mock_request_write, mock_call_next)

            # This test will initially FAIL because the middleware doesn't check scopes yet
            assert response.status_code == 403

    def test_is_mlflow_write_operation(self, middleware):
        """Test detection of MLflow write operations."""
        # These should be detected as write operations
        write_paths = [
            "/api/mlflow/api/2.0/mlflow/runs/create",
            "/api/mlflow/api/2.0/mlflow/runs/update",
            "/api/mlflow/api/2.0/mlflow/registered-models/create",
            "/api/mlflow/api/2.0/mlflow/registered-models/update",
            "/api/mlflow/api/2.0/mlflow/registered-models/delete",
            "/api/mlflow/api/2.0/mlflow/model-versions/create",
            "/api/mlflow/api/2.0/mlflow/experiments/create",
            "/api/mlflow/api/2.0/mlflow/experiments/update",
            "/mlflow/api/2.0/mlflow/runs/log-metric",
            "/mlflow/api/2.0/mlflow/runs/log-parameter",
        ]

        # These should NOT be detected as write operations
        read_paths = [
            "/api/mlflow/api/2.0/mlflow/runs/get",
            "/api/mlflow/api/2.0/mlflow/experiments/search",
            "/api/mlflow/api/2.0/mlflow/registered-models/search",
            "/api/mlflow/api/2.0/mlflow/model-versions/search",
            "/api/mlflow/api/2.0/mlflow/experiments/get",
        ]

        # Test write operations detection (will fail initially)
        for path in write_paths:
            request = MagicMock()
            request.url.path = path
            request.method = "POST"
            assert middleware.is_mlflow_write_operation(
                request
            ), f"Failed to detect write operation: {path}"

        # Test read operations are not detected as writes
        for path in read_paths:
            request = MagicMock()
            request.url.path = path
            request.method = "GET"
            assert not middleware.is_mlflow_write_operation(
                request
            ), f"Incorrectly detected read as write: {path}"

    def test_check_scope_for_write_operation(self, middleware):
        """Test scope checking logic for write operations."""
        # Test with write scopes - should pass
        assert middleware.check_scope_for_write_operation(["model:write"]) == True
        assert middleware.check_scope_for_write_operation(["mlflow:write"]) == True
        assert middleware.check_scope_for_write_operation(["model:read", "model:write"]) == True
        assert middleware.check_scope_for_write_operation(["mlflow:access", "model:write"]) == True

        # Test without write scopes - should fail
        assert middleware.check_scope_for_write_operation(["model:read"]) == False
        assert middleware.check_scope_for_write_operation(["mlflow:read"]) == False
        assert middleware.check_scope_for_write_operation([]) == False
        assert middleware.check_scope_for_write_operation(None) == False

        # Test with admin scope - should pass
        assert middleware.check_scope_for_write_operation(["admin"]) == True
        assert middleware.check_scope_for_write_operation(["mlflow:admin"]) == True
