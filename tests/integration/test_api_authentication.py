"""Tests for API authentication system."""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from fastapi import HTTPException
import jwt
from eth_account import Account
from eth_account.messages import encode_defunct
from datetime import datetime, timedelta


class TestAPIAuthentication:
    """Test suite for API authentication functionality."""

    @pytest.fixture
    def mock_secrets_manager(self):
        """Mock AWS Secrets Manager client."""
        with patch("boto3.client") as mock_client:
            secrets_client = Mock()
            mock_client.return_value = secrets_client
            yield secrets_client

    @pytest.fixture
    def test_eth_account(self):
        """Generate test Ethereum account."""
        account = Account.create()
        return {
            "address": account.address,
            "private_key": account.key.hex()
        }

    def test_api_key_generation(self, mock_secrets_manager):
        """Test API key generation and storage."""
        from src.api.middleware.auth import generate_api_key, store_api_key

        # Generate API key
        api_key = generate_api_key()
        assert api_key is not None
        assert len(api_key) >= 32
        assert isinstance(api_key, str)

        # Test storing in Secrets Manager
        user_id = "test_user_123"
        store_api_key(user_id, api_key)

        mock_secrets_manager.create_secret.assert_called_once()
        call_args = mock_secrets_manager.create_secret.call_args
        assert f"hokusai/api-keys/{user_id}" in call_args[1]["Name"]
        assert api_key in call_args[1]["SecretString"]

    def test_api_key_validation(self, mock_secrets_manager):
        """Test API key validation."""
        from src.api.middleware.auth import validate_api_key

        # Mock secret retrieval
        api_key = "test_api_key_123"
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": api_key
        }

        # Test valid API key
        is_valid = validate_api_key(api_key)
        assert is_valid is True

        # Test invalid API key
        is_valid = validate_api_key("invalid_key")
        assert is_valid is False

    def test_eth_address_signature_verification(self, test_eth_account):
        """Test Ethereum address signature verification."""
        from src.api.middleware.auth import verify_eth_signature

        # Create message and sign it
        message = f"Authenticate to Hokusai API at {datetime.utcnow().isoformat()}"
        message_hash = encode_defunct(text=message)

        # Sign message with private key
        account = Account.from_key(test_eth_account["private_key"])
        signature = account.sign_message(message_hash)

        # Test signature verification
        is_valid = verify_eth_signature(
            address=test_eth_account["address"],
            message=message,
            signature=signature.signature.hex()
        )
        assert is_valid is True

        # Test with wrong address
        is_valid = verify_eth_signature(
            address="0x" + "0" * 40,
            message=message,
            signature=signature.signature.hex()
        )
        assert is_valid is False

        # Test with tampered message
        is_valid = verify_eth_signature(
            address=test_eth_account["address"],
            message="Different message",
            signature=signature.signature.hex()
        )
        assert is_valid is False

    def test_authentication_middleware(self):
        """Test authentication middleware integration."""
        from src.api.main import app

        client = TestClient(app)

        # Test request without authentication
        response = client.get("/api/v1/models")
        assert response.status_code == 401
        assert "Authorization required" in response.json()["detail"]

        # Test with API key header
        headers = {"Authorization": "Bearer test_api_key"}
        with patch("src.api.middleware.auth.validate_api_key", return_value=True):
            response = client.get("/api/v1/models", headers=headers)
            assert response.status_code != 401

        # Test with ETH signature header
        headers = {
            "X-ETH-Address": "0x" + "a" * 40,
            "X-ETH-Signature": "0x" + "b" * 130,
            "X-ETH-Message": "test message"
        }
        with patch("src.api.middleware.auth.verify_eth_signature", return_value=True):
            response = client.get("/api/v1/models", headers=headers)
            assert response.status_code != 401

    def test_rate_limiting(self):
        """Test API rate limiting functionality."""
        from src.api.main import app

        client = TestClient(app)

        # Mock authentication
        headers = {"Authorization": "Bearer test_api_key"}

        with patch("src.api.middleware.auth.validate_api_key", return_value=True):
            # Make requests up to rate limit
            for _ in range(100):
                response = client.get("/api/v1/health", headers=headers)
                assert response.status_code == 200

            # Next request should be rate limited
            response = client.get("/api/v1/health", headers=headers)
            assert response.status_code == 429
            assert "Rate limit exceeded" in response.json()["detail"]

    def test_api_key_rotation(self, mock_secrets_manager):
        """Test API key rotation functionality."""
        from src.api.middleware.auth import rotate_api_key

        user_id = "test_user"
        old_key = "old_api_key"

        # Mock existing key
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": old_key
        }

        # Rotate key
        new_key = rotate_api_key(user_id)

        assert new_key != old_key
        assert len(new_key) >= 32

        # Verify update was called
        mock_secrets_manager.update_secret.assert_called_once()

    def test_eth_address_permissions_mapping(self):
        """Test ETH address to permissions mapping."""
        from src.api.middleware.auth import get_user_permissions

        # Test contributor permissions
        contributor_address = "0x" + "c" * 40
        permissions = get_user_permissions(contributor_address)
        assert "read" in permissions
        assert "contribute" in permissions
        assert "admin" not in permissions

        # Test admin permissions (mocked)
        with patch("src.api.middleware.auth.ADMIN_ADDRESSES", [contributor_address]):
            permissions = get_user_permissions(contributor_address)
            assert "admin" in permissions

    def test_jwt_token_generation(self):
        """Test JWT token generation for session management."""
        from src.api.middleware.auth import generate_jwt_token, decode_jwt_token

        user_data = {
            "user_id": "test_user",
            "eth_address": "0x" + "a" * 40,
            "permissions": ["read", "contribute"]
        }

        # Generate token
        token = generate_jwt_token(user_data)
        assert token is not None

        # Decode token
        decoded = decode_jwt_token(token)
        assert decoded["user_id"] == user_data["user_id"]
        assert decoded["eth_address"] == user_data["eth_address"]
        assert decoded["permissions"] == user_data["permissions"]

        # Test expired token
        expired_token = generate_jwt_token(user_data, expires_delta=timedelta(seconds=-1))
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_jwt_token(expired_token)

    @pytest.mark.asyncio
    async def test_async_auth_middleware(self):
        """Test async authentication middleware."""
        from src.api.middleware.auth import async_auth_required

        @async_auth_required
        async def protected_endpoint(user_info):
            return {"message": "Success", "user": user_info}

        # Test without auth
        with pytest.raises(HTTPException) as exc_info:
            await protected_endpoint()
        assert exc_info.value.status_code == 401

        # Test with valid auth (mocked)
        with patch("src.api.middleware.auth.get_current_user",
                   return_value={"user_id": "test"}):
            result = await protected_endpoint()
            assert result["message"] == "Success"
            assert result["user"]["user_id"] == "test"


class TestAuthenticationIntegration:
    """Integration tests for authentication system."""

    def test_full_api_key_flow(self, mock_secrets_manager):
        """Test complete API key authentication flow."""
        from src.api.main import app
        from src.api.middleware.auth import generate_api_key, store_api_key

        client = TestClient(app)

        # Generate and store API key
        user_id = "integration_test_user"
        api_key = generate_api_key()
        store_api_key(user_id, api_key)

        # Mock secret retrieval
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": api_key
        }

        # Test authenticated request
        headers = {"Authorization": f"Bearer {api_key}"}
        response = client.get("/api/v1/models", headers=headers)
        assert response.status_code == 200

    def test_full_eth_signature_flow(self, test_eth_account):
        """Test complete ETH signature authentication flow."""
        from src.api.main import app
        from eth_account.messages import encode_defunct

        client = TestClient(app)

        # Create and sign message
        message = f"Authenticate to Hokusai API at {datetime.utcnow().isoformat()}"
        account = Account.from_key(test_eth_account["private_key"])
        message_hash = encode_defunct(text=message)
        signature = account.sign_message(message_hash)

        # Test authenticated request
        headers = {
            "X-ETH-Address": test_eth_account["address"],
            "X-ETH-Signature": signature.signature.hex(),
            "X-ETH-Message": message
        }

        response = client.get("/api/v1/models", headers=headers)
        assert response.status_code == 200
