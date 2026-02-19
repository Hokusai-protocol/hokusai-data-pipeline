"""Unit tests for 402 balance check and debit usage in auth middleware."""

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest
from fastapi import Request
from starlette.responses import Response

from src.middleware.auth import APIKeyAuthMiddleware, ValidationResult


class TestBalanceCheck:
    """Test 402 balance enforcement in dispatch()."""

    @pytest.fixture
    def mock_app(self):
        async def app(scope, receive, send):
            pass

        return app

    @pytest.fixture
    def middleware(self, mock_app):
        return APIKeyAuthMiddleware(
            app=mock_app,
            auth_service_url="http://test-auth-service",
            cache=None,
            excluded_paths=["/health"],
        )

    @pytest.fixture
    def mock_request(self):
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/models/test-model/predict"
        request.method = "POST"
        request.headers = {"authorization": "Bearer test-api-key"}
        request.query_params = {}
        request.client = MagicMock(host="127.0.0.1")
        request.state = MagicMock()
        return request

    @pytest.mark.asyncio
    async def test_402_when_insufficient_balance(self, middleware, mock_request):
        """Test that 402 is returned when has_sufficient_balance is False."""
        with patch.object(middleware, "validate_with_auth_service") as mock_validate:
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read"],
                rate_limit_per_hour=1000,
                has_sufficient_balance=False,
                balance=0.0,
            )

            call_next_called = False

            async def mock_call_next(request):
                nonlocal call_next_called
                call_next_called = True
                return Response(content="Should not reach here", status_code=200)

            response = await middleware.dispatch(mock_request, mock_call_next)

            assert response.status_code == 402
            body = json.loads(response.body.decode())
            assert body["detail"] == "Insufficient balance"
            assert not call_next_called, "Route handler should not be called for 402"

    @pytest.mark.asyncio
    async def test_request_passes_with_sufficient_balance(self, middleware, mock_request):
        """Test that requests pass through when has_sufficient_balance is True."""
        with patch.object(middleware, "validate_with_auth_service") as mock_validate:
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read"],
                rate_limit_per_hour=1000,
                has_sufficient_balance=True,
                balance=50.0,
            )

            async def mock_call_next(request):
                return Response(content="Success", status_code=200)

            response = await middleware.dispatch(mock_request, mock_call_next)
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_default_balance_fields_allow_requests(self, middleware, mock_request):
        """Test that default ValidationResult fields (backwards compat) allow requests."""
        with patch.object(middleware, "validate_with_auth_service") as mock_validate:
            # Simulate auth service that hasn't been updated yet (no balance fields)
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read"],
                rate_limit_per_hour=1000,
                # has_sufficient_balance defaults to True
                # balance defaults to 0.0
            )

            async def mock_call_next(request):
                return Response(content="Success", status_code=200)

            response = await middleware.dispatch(mock_request, mock_call_next)
            assert response.status_code == 200


class TestDebitUsage:
    """Test debit usage calls replacing old usage logging."""

    @pytest.fixture
    def mock_app(self):
        async def app(scope, receive, send):
            pass

        return app

    @pytest.fixture
    def middleware(self, mock_app):
        return APIKeyAuthMiddleware(
            app=mock_app,
            auth_service_url="http://test-auth-service",
            cache=None,
            excluded_paths=["/health"],
        )

    @pytest.mark.asyncio
    async def test_debit_called_after_successful_prediction(self, middleware):
        """Test that _debit_usage is called after a successful response."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/models/my-model/predict"
        request.method = "POST"
        request.headers = {"authorization": "Bearer test-key"}
        request.query_params = {}
        request.client = MagicMock(host="127.0.0.1")
        request.state = MagicMock()

        with (
            patch.object(middleware, "validate_with_auth_service") as mock_validate,
            patch.object(middleware, "_debit_usage", new_callable=AsyncMock) as mock_debit,
        ):
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read"],
                rate_limit_per_hour=1000,
                has_sufficient_balance=True,
                balance=10.0,
            )

            async def mock_call_next(req):
                return Response(content="OK", status_code=200)

            # Patch asyncio.create_task to run the coroutine immediately
            with patch("src.middleware.auth.asyncio.create_task") as mock_create_task:
                response = await middleware.dispatch(request, mock_call_next)

            assert response.status_code == 200
            mock_create_task.assert_called_once()
            # The coroutine should have been created from _debit_usage
            mock_debit.assert_called_once_with(
                "key123",
                "my-model",
                "/api/v1/models/my-model/predict",
                pytest.approx(0, abs=1000),  # response_time_ms is approximate
                200,
            )

    @pytest.mark.asyncio
    async def test_debit_not_called_for_5xx_response(self, middleware):
        """Test that _debit_usage is NOT called for 5xx responses."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/models/my-model/predict"
        request.method = "POST"
        request.headers = {"authorization": "Bearer test-key"}
        request.query_params = {}
        request.client = MagicMock(host="127.0.0.1")
        request.state = MagicMock()

        with patch.object(middleware, "validate_with_auth_service") as mock_validate:
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read"],
                rate_limit_per_hour=1000,
                has_sufficient_balance=True,
                balance=10.0,
            )

            async def mock_call_next(req):
                return Response(content="Internal Error", status_code=500)

            with patch("src.middleware.auth.asyncio.create_task") as mock_create_task:
                response = await middleware.dispatch(request, mock_call_next)

            assert response.status_code == 500
            mock_create_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_debit_includes_idempotency_key(self, middleware):
        """Test that debit request includes an idempotency key."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await middleware._debit_usage("key123", "model-1", "/predict", 100, 200)

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert "idempotency_key" in payload
            assert payload["idempotency_key"].startswith("key123-")
            assert payload["model_id"] == "model-1"

    @pytest.mark.asyncio
    async def test_debit_retries_on_transient_failure(self, middleware):
        """Test that debit retries up to 3 times with exponential backoff."""
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.ConnectError("Connection failed")
            response = MagicMock()
            response.status_code = 200
            return response

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_client = AsyncMock()
            mock_client.post.side_effect = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await middleware._debit_usage("key123", "model-1", "/predict", 100, 200)

            assert call_count == 3
            # Check exponential backoff: sleep(1), sleep(2)
            assert mock_sleep.call_count == 2
            mock_sleep.assert_any_call(1)  # 2^0
            mock_sleep.assert_any_call(2)  # 2^1

    @pytest.mark.asyncio
    async def test_debit_logs_warning_after_all_retries_fail(self, middleware):
        """Test that a warning is logged after all retry attempts fail."""
        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("src.middleware.auth.logger") as mock_logger,
        ):
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection failed")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await middleware._debit_usage("key123", "model-1", "/predict", 100, 200)

            mock_logger.warning.assert_called_once()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "key_id=key123" in warning_msg
            assert "3 attempts" in warning_msg

    @pytest.mark.asyncio
    async def test_debit_endpoint_url(self, middleware):
        """Test that debit calls the correct endpoint URL."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await middleware._debit_usage("key456", "model-1", "/predict", 100, 200)

            call_args = mock_client.post.call_args
            assert call_args[0][0] == "http://test-auth-service/api/v1/usage/key456/debit"

    @pytest.mark.asyncio
    async def test_debit_does_not_retry_on_client_error(self, middleware):
        """Test that debit does not retry on 4xx (client error) responses."""
        mock_response = MagicMock()
        mock_response.status_code = 400

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await middleware._debit_usage("key123", "model-1", "/predict", 100, 200)

            # Should only call once (no retry on 4xx)
            mock_client.post.assert_called_once()
            mock_sleep.assert_not_called()


class TestExtractModelId:
    """Test model ID extraction from URL paths."""

    @pytest.fixture
    def mock_app(self):
        async def app(scope, receive, send):
            pass

        return app

    @pytest.fixture
    def middleware(self, mock_app):
        return APIKeyAuthMiddleware(
            app=mock_app,
            auth_service_url="http://test-auth-service",
            cache=None,
            excluded_paths=["/health"],
        )

    def test_extract_model_id_from_predict_path(self, middleware):
        assert middleware._extract_model_id("/api/v1/models/my-model/predict") == "my-model"

    def test_extract_model_id_from_model_detail_path(self, middleware):
        assert middleware._extract_model_id("/api/v1/models/model-123") == "model-123"

    def test_extract_model_id_returns_none_for_non_model_path(self, middleware):
        assert middleware._extract_model_id("/api/v1/health") is None

    def test_extract_model_id_returns_none_for_models_list(self, middleware):
        # /api/v1/models has no model_id segment after it
        assert middleware._extract_model_id("/api/v1/models") is None


class TestCacheTTL:
    """Test that cache TTL is set to 60 seconds."""

    @pytest.fixture
    def mock_cache(self):
        cache = Mock()
        cache.get = Mock(return_value=None)
        cache.setex = Mock()
        cache.ping = Mock()
        return cache

    @pytest.fixture
    def mock_app(self):
        async def app(scope, receive, send):
            pass

        return app

    @pytest.fixture
    def middleware(self, mock_app, mock_cache):
        mw = APIKeyAuthMiddleware(
            app=mock_app,
            auth_service_url="http://test-auth-service",
            cache=mock_cache,
            excluded_paths=["/health"],
        )
        return mw

    @pytest.mark.asyncio
    async def test_cache_ttl_is_60_seconds(self, middleware, mock_cache):
        """Test that validation results are cached with 60 second TTL."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/models/test/predict"
        request.method = "POST"
        request.headers = {"authorization": "Bearer test-key"}
        request.query_params = {}
        request.client = MagicMock(host="127.0.0.1")
        request.state = MagicMock()

        with patch.object(middleware, "validate_with_auth_service") as mock_validate:
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read"],
                rate_limit_per_hour=1000,
                has_sufficient_balance=True,
                balance=10.0,
            )

            async def mock_call_next(req):
                return Response(content="OK", status_code=200)

            with patch("src.middleware.auth.asyncio.create_task"):
                await middleware.dispatch(request, mock_call_next)

        mock_cache.setex.assert_called_once()
        cache_call_args = mock_cache.setex.call_args
        assert cache_call_args[0][1] == 60

    @pytest.mark.asyncio
    async def test_cache_includes_balance_fields(self, middleware, mock_cache):
        """Test that cached data includes has_sufficient_balance and balance."""
        request = MagicMock(spec=Request)
        request.url.path = "/protected"
        request.method = "GET"
        request.headers = {"authorization": "Bearer test-key"}
        request.query_params = {}
        request.client = MagicMock(host="127.0.0.1")
        request.state = MagicMock()

        with patch.object(middleware, "validate_with_auth_service") as mock_validate:
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read"],
                rate_limit_per_hour=1000,
                has_sufficient_balance=True,
                balance=25.50,
            )

            async def mock_call_next(req):
                return Response(content="OK", status_code=200)

            with patch("src.middleware.auth.asyncio.create_task"):
                await middleware.dispatch(request, mock_call_next)

        cache_call_args = mock_cache.setex.call_args
        cached_json = json.loads(cache_call_args[0][2])
        assert cached_json["has_sufficient_balance"] is True
        assert cached_json["balance"] == 25.50
