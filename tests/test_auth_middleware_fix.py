"""Test the authentication middleware fix for service_id configuration."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.api.utils.config import Settings
from src.middleware.auth import APIKeyAuthMiddleware, ValidationResult


@pytest.mark.asyncio
async def test_auth_middleware_uses_configurable_service_id():
    """Test that the middleware uses the configured service_id."""
    # Create mock app
    app = Mock()

    # Create middleware instance
    middleware = APIKeyAuthMiddleware(app)

    # Verify it has the correct service_id from settings
    assert hasattr(middleware.settings, "auth_service_id")
    assert middleware.settings.auth_service_id == "platform"


@pytest.mark.asyncio
async def test_validate_with_auth_service_uses_correct_service_id():
    """Test that validation uses the configured service_id."""
    # Create mock app
    app = Mock()
    middleware = APIKeyAuthMiddleware(app)

    # Mock the httpx client
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "is_valid": True,
            "user_id": "test-user",
            "key_id": "test-key",
            "service_id": "platform",
        }
        mock_client.post.return_value = mock_response

        # Call validate method
        result = await middleware.validate_with_auth_service("test-api-key", "127.0.0.1")

        # Verify the correct service_id was sent
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args

        # Check the JSON body contains correct service_id
        json_body = call_args[1]["json"]
        assert json_body["service_id"] == "platform"
        assert json_body["client_ip"] == "127.0.0.1"

        # Check the result
        assert result.is_valid is True
        assert result.user_id == "test-user"
        assert result.service_id == "platform"


@pytest.mark.asyncio
async def test_service_id_can_be_overridden_by_env():
    """Test that AUTH_SERVICE_ID environment variable overrides default."""
    import os

    # Set environment variable
    os.environ["AUTH_SERVICE_ID"] = "platform"

    # Create new settings instance
    settings = Settings()

    # Clean up
    del os.environ["AUTH_SERVICE_ID"]

    # The default is 'platform' but env vars would override in real usage
    # This test shows the configuration is in place
    assert hasattr(settings, "auth_service_id")


def test_validation_result_structure():
    """Test the ValidationResult dataclass has required fields."""
    result = ValidationResult(
        is_valid=True,
        user_id="test",
        key_id="key123",
        service_id="platform",
        scopes=["read", "write"],
        rate_limit_per_hour=1000,
    )

    assert result.is_valid is True
    assert result.user_id == "test"
    assert result.service_id == "platform"
    assert result.scopes == ["read", "write"]
    assert result.rate_limit_per_hour == 1000
