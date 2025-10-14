"""Tests for mTLS authentication middleware enhancements."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from src.middleware.auth import APIKeyAuthMiddleware


class TestMTLSMiddlewareDetection:
    """Test internal request detection and mTLS certificate verification."""

    def setup_method(self):
        """Set up test environment."""
        self.mock_app = MagicMock()
        self.middleware = APIKeyAuthMiddleware(
            app=self.mock_app,
            auth_service_url="https://auth.hokus.ai",
            excluded_paths=["/health", "/ready"],
        )

    def test_is_internal_request_with_private_ip(self):
        """Test that requests from private IP range (10.x.x.x) are detected as internal."""
        # Test various private IP addresses in 10.0.0.0/8 range
        assert self.middleware._is_internal_request("10.0.1.5") is True
        assert self.middleware._is_internal_request("10.10.20.30") is True
        assert self.middleware._is_internal_request("10.255.255.255") is True

    def test_is_internal_request_with_public_ip(self):
        """Test that requests from public IPs are not detected as internal."""
        assert self.middleware._is_internal_request("8.8.8.8") is False
        assert self.middleware._is_internal_request("1.2.3.4") is False
        assert self.middleware._is_internal_request("192.168.1.1") is False

    def test_is_internal_request_with_localhost(self):
        """Test that localhost is not detected as internal for mTLS."""
        # Localhost should not use mTLS in tests
        assert self.middleware._is_internal_request("127.0.0.1") is False
        assert self.middleware._is_internal_request("localhost") is False

    def test_is_internal_request_with_none(self):
        """Test that None IP is handled gracefully."""
        assert self.middleware._is_internal_request(None) is False

    def test_is_internal_request_with_empty_string(self):
        """Test that empty string IP is handled gracefully."""
        assert self.middleware._is_internal_request("") is False

    def test_verify_mtls_certificate_with_verified_cert(self):
        """Test mTLS certificate verification when peer cert is verified."""
        mock_request = MagicMock(spec=Request)
        mock_request.state = MagicMock()
        mock_request.state.peer_cert_verified = True

        result = self.middleware._verify_mtls_certificate(mock_request)
        assert result is True

    def test_verify_mtls_certificate_with_unverified_cert(self):
        """Test mTLS certificate verification when peer cert is not verified."""
        mock_request = MagicMock(spec=Request)
        mock_request.state = MagicMock()
        mock_request.state.peer_cert_verified = False

        result = self.middleware._verify_mtls_certificate(mock_request)
        assert result is False

    def test_verify_mtls_certificate_without_state(self):
        """Test mTLS certificate verification when request has no state."""
        mock_request = MagicMock(spec=Request)
        # No state attribute
        del mock_request.state

        result = self.middleware._verify_mtls_certificate(mock_request)
        assert result is False

    def test_verify_mtls_certificate_without_peer_cert(self):
        """Test mTLS certificate verification when peer_cert_verified is not set."""
        from types import SimpleNamespace

        mock_request = MagicMock(spec=Request)
        # Use SimpleNamespace instead of MagicMock so hasattr works correctly
        mock_request.state = SimpleNamespace()
        # peer_cert_verified not set

        result = self.middleware._verify_mtls_certificate(mock_request)
        assert result is False


class TestMTLSAuthenticationDispatch:
    """Test hybrid authentication dispatch logic."""

    def setup_method(self):
        """Set up test environment."""
        self.mock_app = MagicMock()
        self.middleware = APIKeyAuthMiddleware(
            app=self.mock_app,
            auth_service_url="https://auth.hokus.ai",
            cache=None,  # Disable cache for tests
        )

    @pytest.mark.asyncio
    async def test_dispatch_internal_mtls_request_bypasses_auth_service(self):
        """Test that internal mTLS requests bypass external auth service."""
        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.url.path = "/mlflow/api/2.0/mlflow/runs/create"
        mock_request.headers = MagicMock()
        mock_request.headers.get.return_value = "10.0.1.5"  # Internal IP
        mock_request.client = MagicMock()
        mock_request.client.host = "10.0.1.5"
        mock_request.state = MagicMock()
        mock_request.state.peer_cert_verified = True  # Valid mTLS certificate

        # Mock call_next
        mock_call_next = AsyncMock(return_value=MagicMock())

        # Dispatch request
        await self.middleware.dispatch(mock_request, mock_call_next)

        # Verify request.state was set correctly for internal service
        assert mock_request.state.user_id == "internal_service"
        assert mock_request.state.api_key_id == "mtls_cert"
        assert mock_request.state.service_id == "hokusai_internal"
        assert "mlflow:write" in mock_request.state.scopes
        assert "mlflow:read" in mock_request.state.scopes
        assert mock_request.state.rate_limit_per_hour is None

        # Verify call_next was called
        mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_internal_without_mtls_falls_back_to_api_key(self):
        """Test that internal requests without mTLS fall back to API key auth."""
        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.url.path = "/mlflow/api/2.0/mlflow/runs/create"
        mock_request.headers = MagicMock()
        mock_request.headers.get.side_effect = lambda key, default="": {
            "authorization": "Bearer hk_test_key_123",
            "x-forwarded-for": "10.0.1.5",
        }.get(key.lower(), default)
        mock_request.client = MagicMock()
        mock_request.client.host = "10.0.1.5"
        mock_request.state = MagicMock()
        mock_request.state.peer_cert_verified = False  # No mTLS certificate
        mock_request.query_params = {}

        # Mock auth service validation
        with patch.object(
            self.middleware, "validate_with_auth_service", new_callable=AsyncMock
        ) as mock_validate:
            from src.middleware.auth import ValidationResult

            mock_validate.return_value = ValidationResult(
                is_valid=True, user_id="user123", key_id="key123", scopes=["mlflow:write"]
            )

            # Mock call_next
            mock_call_next = AsyncMock(return_value=MagicMock())

            # Dispatch request
            await self.middleware.dispatch(mock_request, mock_call_next)

            # Verify auth service was called
            mock_validate.assert_called_once()

            # Verify call_next was called
            mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_external_request_uses_api_key_auth(self):
        """Test that external requests use API key authentication."""
        # Create mock request with external IP
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.url.path = "/mlflow/api/2.0/mlflow/runs/create"
        mock_request.headers = MagicMock()
        mock_request.headers.get.side_effect = lambda key, default="": {
            "authorization": "Bearer hk_test_key_123",
            "x-forwarded-for": "8.8.8.8",  # External IP
        }.get(key.lower(), default)
        mock_request.client = MagicMock()
        mock_request.client.host = "8.8.8.8"
        mock_request.query_params = {}

        # Mock auth service validation
        with patch.object(
            self.middleware, "validate_with_auth_service", new_callable=AsyncMock
        ) as mock_validate:
            from src.middleware.auth import ValidationResult

            mock_validate.return_value = ValidationResult(
                is_valid=True, user_id="user123", key_id="key123", scopes=["mlflow:write"]
            )

            # Mock call_next
            mock_call_next = AsyncMock(return_value=MagicMock())

            # Dispatch request
            await self.middleware.dispatch(mock_request, mock_call_next)

            # Verify auth service was called
            mock_validate.assert_called_once_with("hk_test_key_123", "8.8.8.8")

    @pytest.mark.asyncio
    async def test_dispatch_excluded_path_skips_auth(self):
        """Test that excluded paths skip authentication."""
        # Create mock request for health check
        mock_request = MagicMock(spec=Request)
        mock_request.method = "GET"
        mock_request.url.path = "/health"
        mock_request.headers = MagicMock()

        # Mock call_next
        mock_call_next = AsyncMock(return_value=MagicMock())

        # Dispatch request
        await self.middleware.dispatch(mock_request, mock_call_next)

        # Verify call_next was called without auth
        mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_options_request_skips_auth(self):
        """Test that CORS preflight OPTIONS requests skip authentication."""
        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.method = "OPTIONS"
        mock_request.url.path = "/mlflow/api/2.0/mlflow/runs/create"
        mock_request.headers = MagicMock()

        # Mock call_next
        mock_call_next = AsyncMock(return_value=MagicMock())

        # Dispatch request
        await self.middleware.dispatch(mock_request, mock_call_next)

        # Verify call_next was called without auth
        mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_logs_internal_mtls_authentication(self):
        """Test that internal mTLS authentication is logged."""
        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.url.path = "/mlflow/api/2.0/mlflow/runs/create"
        mock_request.headers = MagicMock()
        mock_request.headers.get.return_value = "10.0.1.5"
        mock_request.client = MagicMock()
        mock_request.client.host = "10.0.1.5"
        mock_request.state = MagicMock()
        mock_request.state.peer_cert_verified = True

        # Mock call_next
        mock_call_next = AsyncMock(return_value=MagicMock())

        # Mock logger
        with patch("src.middleware.auth.logger") as mock_logger:
            # Dispatch request
            await self.middleware.dispatch(mock_request, mock_call_next)

            # Verify debug log was called
            mock_logger.debug.assert_called_with("Internal mTLS request authenticated")

    @pytest.mark.asyncio
    async def test_dispatch_warns_on_internal_without_mtls(self):
        """Test that warning is logged for internal requests without mTLS."""
        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.url.path = "/mlflow/api/2.0/mlflow/runs/create"
        mock_request.headers = MagicMock()
        mock_request.headers.get.side_effect = lambda key, default="": {
            "authorization": "Bearer hk_test_key_123",
            "x-forwarded-for": "10.0.1.5",
        }.get(key.lower(), default)
        mock_request.client = MagicMock()
        mock_request.client.host = "10.0.1.5"
        mock_request.state = MagicMock()
        mock_request.state.peer_cert_verified = False
        mock_request.query_params = {}

        # Mock auth service
        with patch.object(
            self.middleware, "validate_with_auth_service", new_callable=AsyncMock
        ) as mock_validate:
            from src.middleware.auth import ValidationResult

            mock_validate.return_value = ValidationResult(
                is_valid=True, user_id="user123", key_id="key123", scopes=["mlflow:write"]
            )

            # Mock logger
            with patch("src.middleware.auth.logger") as mock_logger:
                # Mock call_next
                mock_call_next = AsyncMock(return_value=MagicMock())

                # Dispatch request
                await self.middleware.dispatch(mock_request, mock_call_next)

                # Verify warning was logged
                mock_logger.warning.assert_called_with(
                    "Internal request from 10.0.1.5 without valid mTLS certificate"
                )

    @pytest.mark.asyncio
    async def test_dispatch_internal_mtls_no_rate_limit(self):
        """Test that internal mTLS requests have no rate limit."""
        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.method = "GET"
        mock_request.url.path = "/mlflow/api/2.0/mlflow/experiments/list"
        mock_request.headers = MagicMock()
        mock_request.headers.get.return_value = "10.0.2.100"
        mock_request.client = MagicMock()
        mock_request.client.host = "10.0.2.100"
        mock_request.state = MagicMock()
        mock_request.state.peer_cert_verified = True

        # Mock call_next
        mock_call_next = AsyncMock(return_value=MagicMock())

        # Dispatch request
        await self.middleware.dispatch(mock_request, mock_call_next)

        # Verify rate limit is None for internal requests
        assert mock_request.state.rate_limit_per_hour is None


class TestMTLSRequestStateAttributes:
    """Test that request state is set correctly for mTLS requests."""

    def setup_method(self):
        """Set up test environment."""
        self.mock_app = MagicMock()
        self.middleware = APIKeyAuthMiddleware(
            app=self.mock_app, auth_service_url="https://auth.hokus.ai", cache=None
        )

    @pytest.mark.asyncio
    async def test_mtls_request_sets_all_required_attributes(self):
        """Test that mTLS requests set all required request.state attributes."""
        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.url.path = "/mlflow/api/2.0/mlflow/runs/create"
        mock_request.headers = MagicMock()
        mock_request.headers.get.return_value = "10.0.1.5"
        mock_request.client = MagicMock()
        mock_request.client.host = "10.0.1.5"
        mock_request.state = MagicMock()
        mock_request.state.peer_cert_verified = True

        # Mock call_next
        mock_call_next = AsyncMock(return_value=MagicMock())

        # Dispatch request
        await self.middleware.dispatch(mock_request, mock_call_next)

        # Verify all required attributes are set
        assert hasattr(mock_request.state, "user_id")
        assert hasattr(mock_request.state, "api_key_id")
        assert hasattr(mock_request.state, "service_id")
        assert hasattr(mock_request.state, "scopes")
        assert hasattr(mock_request.state, "rate_limit_per_hour")

    @pytest.mark.asyncio
    async def test_mtls_request_scopes_include_read_and_write(self):
        """Test that mTLS requests have both read and write scopes."""
        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.url.path = "/mlflow/api/2.0/mlflow/runs/create"
        mock_request.headers = MagicMock()
        mock_request.headers.get.return_value = "10.0.1.5"
        mock_request.client = MagicMock()
        mock_request.client.host = "10.0.1.5"
        mock_request.state = MagicMock()
        mock_request.state.peer_cert_verified = True

        # Mock call_next
        mock_call_next = AsyncMock(return_value=MagicMock())

        # Dispatch request
        await self.middleware.dispatch(mock_request, mock_call_next)

        # Verify scopes include both read and write
        assert "mlflow:read" in mock_request.state.scopes
        assert "mlflow:write" in mock_request.state.scopes
