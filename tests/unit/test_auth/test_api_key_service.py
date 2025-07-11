"""Unit tests for API key generation service."""

import datetime
from unittest.mock import Mock, patch

import pytest

from src.auth.api_key_service import (
    APIKey,
    APIKeyService,
    APIKeyCreationError,
    APIKeyNotFoundError,
    APIKeyValidationError
)


class TestAPIKeyService:
    """Test cases for API key service."""

    @pytest.fixture
    def mock_db(self):
        """Mock database connection."""
        return Mock()

    @pytest.fixture
    def api_key_service(self, mock_db):
        """Create API key service instance."""
        return APIKeyService(db=mock_db)

    def test_generate_api_key_creates_secure_key(self, api_key_service, mock_db):
        """Test that API key generation creates a secure key."""
        # Arrange
        user_id = "user123"
        key_name = "Production API Key"
        
        # Act
        result = api_key_service.generate_api_key(
            user_id=user_id,
            key_name=key_name
        )
        
        # Assert
        assert result.key.startswith("hk_live_")
        assert len(result.key) > 40  # Prefix + 32 bytes encoded
        assert result.key_id is not None
        assert result.user_id == user_id
        assert result.name == key_name
        assert result.is_active is True
        assert result.created_at is not None
        
        # Verify database was called
        mock_db.save_api_key.assert_called_once()

    def test_generate_api_key_with_test_environment(self, api_key_service, mock_db):
        """Test API key generation for test environment."""
        # Arrange
        user_id = "user123"
        
        # Act
        result = api_key_service.generate_api_key(
            user_id=user_id,
            key_name="Test Key",
            environment="test"
        )
        
        # Assert
        assert result.key.startswith("hk_test_")

    def test_generate_api_key_with_expiration(self, api_key_service, mock_db):
        """Test API key generation with expiration date."""
        # Arrange
        user_id = "user123"
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=30)
        
        # Act
        result = api_key_service.generate_api_key(
            user_id=user_id,
            key_name="Temporary Key",
            expires_at=expires_at
        )
        
        # Assert
        assert result.expires_at == expires_at

    def test_generate_api_key_with_rate_limit(self, api_key_service, mock_db):
        """Test API key generation with custom rate limit."""
        # Arrange
        user_id = "user123"
        rate_limit = 1000
        
        # Act
        result = api_key_service.generate_api_key(
            user_id=user_id,
            key_name="Limited Key",
            rate_limit_per_hour=rate_limit
        )
        
        # Assert
        assert result.rate_limit_per_hour == rate_limit

    def test_generate_api_key_with_ip_allowlist(self, api_key_service, mock_db):
        """Test API key generation with IP allowlist."""
        # Arrange
        user_id = "user123"
        allowed_ips = ["192.168.1.1", "10.0.0.1"]
        
        # Act
        result = api_key_service.generate_api_key(
            user_id=user_id,
            key_name="IP Restricted Key",
            allowed_ips=allowed_ips
        )
        
        # Assert
        assert result.allowed_ips == allowed_ips

    def test_generate_api_key_handles_database_error(self, api_key_service, mock_db):
        """Test API key generation handles database errors."""
        # Arrange
        mock_db.save_api_key.side_effect = Exception("Database error")
        
        # Act & Assert
        with pytest.raises(APIKeyCreationError):
            api_key_service.generate_api_key(
                user_id="user123",
                key_name="Test Key"
            )

    def test_validate_api_key_with_valid_key(self, api_key_service, mock_db):
        """Test validation of a valid API key."""
        # Arrange
        api_key = "hk_live_valid_key_123"
        # Create a mock hash that will be returned by bcrypt
        mock_hash = "$2b$12$mocked_hash_value"
        
        # Mock the database to return a key with this hash
        mock_db.get_all_api_keys.return_value = [{
            "key_id": "key123",
            "user_id": "user123",
            "key_hash": mock_hash,
            "is_active": True,
            "expires_at": None,
            "rate_limit_per_hour": 100,
            "allowed_ips": None
        }]
        
        # Mock bcrypt to verify the key
        with patch('src.auth.api_key_service.bcrypt.checkpw', return_value=True):
            # Act
            result = api_key_service.validate_api_key(api_key)
            
            # Assert
            assert result.is_valid is True
            assert result.key_id == "key123"
            assert result.user_id == "user123"
            assert result.rate_limit_per_hour == 100

    def test_validate_api_key_with_expired_key(self, api_key_service, mock_db):
        """Test validation of an expired API key."""
        # Arrange
        api_key = "hk_live_expired_key_123"
        expired_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).isoformat()
        mock_hash = "$2b$12$mocked_hash_value"
        
        mock_db.get_all_api_keys.return_value = [{
            "key_id": "key123",
            "user_id": "user123",
            "key_hash": mock_hash,
            "is_active": True,
            "expires_at": expired_time,
            "rate_limit_per_hour": 100,
            "allowed_ips": None
        }]
        
        with patch('src.auth.api_key_service.bcrypt.checkpw', return_value=True):
            # Act
            result = api_key_service.validate_api_key(api_key)
            
            # Assert
            assert result.is_valid is False
            assert result.error == "API key has expired"

    def test_validate_api_key_with_inactive_key(self, api_key_service, mock_db):
        """Test validation of an inactive API key."""
        # Arrange
        api_key = "hk_live_inactive_key_123"
        mock_hash = "$2b$12$mocked_hash_value"
        
        mock_db.get_all_api_keys.return_value = [{
            "key_id": "key123",
            "user_id": "user123",
            "key_hash": mock_hash,
            "is_active": False,
            "expires_at": None,
            "rate_limit_per_hour": 100,
            "allowed_ips": None
        }]
        
        with patch('src.auth.api_key_service.bcrypt.checkpw', return_value=True):
            # Act
            result = api_key_service.validate_api_key(api_key)
            
            # Assert
            assert result.is_valid is False
            assert result.error == "API key is inactive"

    def test_validate_api_key_with_ip_restriction(self, api_key_service, mock_db):
        """Test validation of API key with IP restrictions."""
        # Arrange
        api_key = "hk_live_ip_restricted_key_123"
        mock_hash = "$2b$12$mocked_hash_value"
        
        mock_db.get_all_api_keys.return_value = [{
            "key_id": "key123",
            "user_id": "user123",
            "key_hash": mock_hash,
            "is_active": True,
            "expires_at": None,
            "rate_limit_per_hour": 100,
            "allowed_ips": ["192.168.1.1", "10.0.0.1"]
        }]
        
        with patch('src.auth.api_key_service.bcrypt.checkpw', return_value=True):
            # Act - Valid IP
            result = api_key_service.validate_api_key(api_key, client_ip="192.168.1.1")
            assert result.is_valid is True
            
            # Act - Invalid IP
            result = api_key_service.validate_api_key(api_key, client_ip="192.168.1.2")
            assert result.is_valid is False
            assert result.error == "IP address not allowed"

    def test_validate_api_key_not_found(self, api_key_service, mock_db):
        """Test validation of non-existent API key."""
        # Arrange
        api_key = "hk_live_not_found_key_123"
        mock_db.get_all_api_keys.return_value = []
        
        with patch('src.auth.api_key_service.bcrypt.checkpw', return_value=False):
            # Act
            result = api_key_service.validate_api_key(api_key)
            
            # Assert
            assert result.is_valid is False
            assert result.error == "API key not found"

    def test_list_api_keys_for_user(self, api_key_service, mock_db):
        """Test listing API keys for a user."""
        # Arrange
        user_id = "user123"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        mock_db.get_api_keys_by_user.return_value = [
            {
                "key_id": "key1",
                "name": "Production Key",
                "key_prefix": "hk_live_abc",
                "key_hash": "hash1",
                "user_id": user_id,
                "created_at": now,
                "last_used_at": now,
                "is_active": True,
                "expires_at": None
            },
            {
                "key_id": "key2", 
                "name": "Test Key",
                "key_prefix": "hk_test_def",
                "key_hash": "hash2",
                "user_id": user_id,
                "created_at": now,
                "last_used_at": None,
                "is_active": True,
                "expires_at": None
            }
        ]
        
        # Act
        result = api_key_service.list_api_keys(user_id)
        
        # Assert
        assert len(result) == 2
        assert result[0].key_id == "key1"
        assert result[0].name == "Production Key"
        assert result[0].key_prefix == "hk_live_abc"
        assert result[1].key_id == "key2"

    def test_revoke_api_key(self, api_key_service, mock_db):
        """Test revoking an API key."""
        # Arrange
        user_id = "user123"
        key_id = "key123"
        mock_db.get_api_key.return_value = {
            "key_id": key_id,
            "user_id": user_id,
            "is_active": True
        }
        
        # Act
        result = api_key_service.revoke_api_key(user_id, key_id)
        
        # Assert
        assert result is True
        mock_db.update_api_key.assert_called_once_with(
            key_id,
            {"is_active": False}
        )

    def test_revoke_api_key_wrong_user(self, api_key_service, mock_db):
        """Test revoking an API key by wrong user."""
        # Arrange
        mock_db.get_api_key.return_value = {
            "key_id": "key123",
            "user_id": "user123",
            "is_active": True
        }
        
        # Act & Assert
        with pytest.raises(APIKeyValidationError):
            api_key_service.revoke_api_key("wrong_user", "key123")

    def test_revoke_api_key_not_found(self, api_key_service, mock_db):
        """Test revoking non-existent API key."""
        # Arrange
        mock_db.get_api_key.return_value = None
        
        # Act & Assert
        with pytest.raises(APIKeyNotFoundError):
            api_key_service.revoke_api_key("user123", "key123")

    def test_rotate_api_key(self, api_key_service, mock_db):
        """Test rotating an API key."""
        # Arrange
        user_id = "user123"
        key_id = "key123"
        mock_db.get_api_key.return_value = {
            "key_id": key_id,
            "user_id": user_id,
            "name": "Production Key",
            "is_active": True,
            "rate_limit_per_hour": 1000,
            "allowed_ips": ["192.168.1.1"]
        }
        
        # Act
        result = api_key_service.rotate_api_key(user_id, key_id)
        
        # Assert
        assert result.key.startswith("hk_live_")
        assert result.name == "Production Key"
        assert result.rate_limit_per_hour == 1000
        assert result.allowed_ips == ["192.168.1.1"]
        
        # Verify old key was revoked
        mock_db.update_api_key.assert_called_with(
            key_id,
            {"is_active": False}
        )

    def test_rotate_api_key_preserves_settings(self, api_key_service, mock_db):
        """Test that key rotation preserves original settings."""
        # Arrange
        user_id = "user123"
        key_id = "key123"
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)
        
        mock_db.get_api_key.return_value = {
            "key_id": key_id,
            "user_id": user_id,
            "name": "Limited Key",
            "is_active": True,
            "rate_limit_per_hour": 500,
            "allowed_ips": ["10.0.0.1"],
            "expires_at": expires_at.isoformat(),
            "environment": "test"
        }
        
        # Act
        result = api_key_service.rotate_api_key(user_id, key_id)
        
        # Assert
        assert result.key.startswith("hk_test_")  # Preserves test environment
        assert result.rate_limit_per_hour == 500
        assert result.allowed_ips == ["10.0.0.1"]
        assert result.expires_at == expires_at

    def test_update_last_used_timestamp(self, api_key_service, mock_db):
        """Test updating last used timestamp."""
        # Arrange
        key_id = "key123"
        
        # Act
        api_key_service.update_last_used(key_id)
        
        # Assert
        mock_db.update_api_key.assert_called_once()
        call_args = mock_db.update_api_key.call_args
        assert call_args[0][0] == key_id
        assert "last_used_at" in call_args[0][1]
        assert isinstance(call_args[0][1]["last_used_at"], datetime.datetime)

    def test_hash_api_key(self, api_key_service):
        """Test API key hashing."""
        # Arrange
        api_key = "hk_live_test_key_123"
        
        # Act
        hash1 = api_key_service._hash_api_key(api_key)
        hash2 = api_key_service._hash_api_key(api_key)
        hash3 = api_key_service._hash_api_key("different_key")
        
        # Assert
        # Note: bcrypt produces different hashes for same input (due to salt)
        assert hash1 != hash2  # Different hashes due to different salts
        assert hash1 != hash3  # Different input produces different hash
        assert hash1.startswith('$2b$')  # bcrypt hash format
        assert len(hash1) == 60  # bcrypt hash length

    def test_verify_api_key_hash(self, api_key_service):
        """Test API key hash verification."""
        # Arrange
        api_key = "hk_live_test_key_123"
        hash_value = api_key_service._hash_api_key(api_key)
        
        # Act & Assert
        assert api_key_service._verify_api_key(api_key, hash_value) is True
        assert api_key_service._verify_api_key("wrong_key", hash_value) is False