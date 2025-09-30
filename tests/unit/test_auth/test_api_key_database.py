"""Unit tests for API key database operations."""

import datetime
import json
from unittest.mock import Mock

import pytest

# Skip this test file until APIKeyModel is implemented in database
pytest.skip("APIKeyModel not yet implemented in database", allow_module_level=True)

from src.database.models import APIKeyModel
from src.database.operations import APIKeyDatabaseOperations


class TestAPIKeyDatabaseModel:
    """Test cases for API key database model."""

    def test_api_key_model_creation(self):
        """Test creating an API key model."""
        # Arrange
        now = datetime.datetime.utcnow()

        # Act
        model = APIKeyModel(
            key_id="key123",
            key_hash="$2b$12$hash_value_here",
            key_prefix="hk_live_abc",
            user_id="user123",
            name="Production Key",
            created_at=now,
            expires_at=None,
            last_used_at=None,
            is_active=True,
            rate_limit_per_hour=1000,
            allowed_ips=["192.168.1.1"],
            environment="production",
        )

        # Assert
        assert model.key_id == "key123"
        assert model.key_hash == "$2b$12$hash_value_here"
        assert model.key_prefix == "hk_live_abc"
        assert model.user_id == "user123"
        assert model.name == "Production Key"
        assert model.is_active is True
        assert model.rate_limit_per_hour == 1000
        assert model.allowed_ips == ["192.168.1.1"]

    def test_api_key_model_to_dict(self):
        """Test converting API key model to dictionary."""
        # Arrange
        now = datetime.datetime.utcnow()
        expires = now + datetime.timedelta(days=30)

        model = APIKeyModel(
            key_id="key123",
            key_hash="hash123",
            key_prefix="hk_live_abc",
            user_id="user123",
            name="Test Key",
            created_at=now,
            expires_at=expires,
            last_used_at=now,
            is_active=True,
            rate_limit_per_hour=500,
            allowed_ips=["10.0.0.1"],
            environment="production",
        )

        # Act
        result = model.to_dict()

        # Assert
        assert result["key_id"] == "key123"
        assert result["key_hash"] == "hash123"
        assert result["key_prefix"] == "hk_live_abc"
        assert result["user_id"] == "user123"
        assert result["name"] == "Test Key"
        assert result["created_at"] == now.isoformat()
        assert result["expires_at"] == expires.isoformat()
        assert result["last_used_at"] == now.isoformat()
        assert result["is_active"] is True
        assert result["rate_limit_per_hour"] == 500
        assert result["allowed_ips"] == ["10.0.0.1"]

    def test_api_key_model_from_dict(self):
        """Test creating API key model from dictionary."""
        # Arrange
        now = datetime.datetime.utcnow()
        data = {
            "key_id": "key123",
            "key_hash": "hash123",
            "key_prefix": "hk_test_def",
            "user_id": "user123",
            "name": "Test Key",
            "created_at": now.isoformat(),
            "expires_at": None,
            "last_used_at": None,
            "is_active": True,
            "rate_limit_per_hour": 100,
            "allowed_ips": None,
            "environment": "test",
        }

        # Act
        model = APIKeyModel.from_dict(data)

        # Assert
        assert model.key_id == "key123"
        assert model.key_prefix == "hk_test_def"
        assert model.environment == "test"
        assert model.rate_limit_per_hour == 100
        assert model.allowed_ips is None

    def test_api_key_model_is_expired(self):
        """Test checking if API key is expired."""
        # Arrange
        now = datetime.datetime.utcnow()

        # Test non-expired key
        model1 = APIKeyModel(key_id="key1", expires_at=now + datetime.timedelta(days=1))
        assert model1.is_expired() is False

        # Test expired key
        model2 = APIKeyModel(key_id="key2", expires_at=now - datetime.timedelta(days=1))
        assert model2.is_expired() is True

        # Test key without expiration
        model3 = APIKeyModel(key_id="key3", expires_at=None)
        assert model3.is_expired() is False

    def test_api_key_model_display_info(self):
        """Test getting display information for API key."""
        # Arrange
        model = APIKeyModel(
            key_id="key123",
            key_prefix="hk_live_abc",
            name="Production Key",
            created_at=datetime.datetime.utcnow(),
            last_used_at=datetime.datetime.utcnow() - datetime.timedelta(hours=2),
            is_active=True,
        )

        # Act
        info = model.get_display_info()

        # Assert
        assert info["key_id"] == "key123"
        assert info["key_prefix"] == "hk_live_abc***"  # Masked
        assert info["name"] == "Production Key"
        assert "created_at" in info
        assert "last_used" in info
        assert info["status"] == "active"


class TestAPIKeyDatabaseOperations:
    """Test cases for API key database operations."""

    @pytest.fixture
    def mock_db_connection(self):
        """Mock database connection."""
        return Mock()

    @pytest.fixture
    def db_ops(self, mock_db_connection):
        """Create database operations instance."""
        return APIKeyDatabaseOperations(db=mock_db_connection)

    def test_save_api_key(self, db_ops, mock_db_connection):
        """Test saving an API key to database."""
        # Arrange
        api_key_data = {
            "key_id": "key123",
            "key_hash": "hash123",
            "key_prefix": "hk_live_abc",
            "user_id": "user123",
            "name": "Test Key",
            "created_at": datetime.datetime.utcnow(),
            "is_active": True,
            "rate_limit_per_hour": 1000,
        }

        # Act
        db_ops.save_api_key(api_key_data)

        # Assert
        mock_db_connection.execute.assert_called_once()
        call_args = mock_db_connection.execute.call_args[0][0]
        assert "INSERT INTO api_keys" in call_args

    def test_get_api_key_by_hash(self, db_ops, mock_db_connection):
        """Test retrieving API key by hash."""
        # Arrange
        mock_result = Mock()
        mock_result.fetchone.return_value = {
            "key_id": "key123",
            "key_hash": "hash123",
            "user_id": "user123",
            "is_active": True,
            "expires_at": None,
            "rate_limit_per_hour": 1000,
            "allowed_ips": json.dumps(["192.168.1.1"]),
        }
        mock_db_connection.execute.return_value = mock_result

        # Act
        result = db_ops.get_api_key_by_hash("hash123")

        # Assert
        assert result["key_id"] == "key123"
        assert result["user_id"] == "user123"
        assert result["allowed_ips"] == ["192.168.1.1"]  # JSON decoded

        call_args = mock_db_connection.execute.call_args[0][0]
        assert "SELECT * FROM api_keys WHERE key_hash = ?" in call_args

    def test_get_api_key_by_hash_not_found(self, db_ops, mock_db_connection):
        """Test retrieving non-existent API key."""
        # Arrange
        mock_result = Mock()
        mock_result.fetchone.return_value = None
        mock_db_connection.execute.return_value = mock_result

        # Act
        result = db_ops.get_api_key_by_hash("nonexistent")

        # Assert
        assert result is None

    def test_get_api_keys_by_user(self, db_ops, mock_db_connection):
        """Test retrieving all API keys for a user."""
        # Arrange
        mock_result = Mock()
        mock_result.fetchall.return_value = [
            {
                "key_id": "key1",
                "name": "Key 1",
                "key_prefix": "hk_live_abc",
                "created_at": datetime.datetime.utcnow().isoformat(),
                "is_active": True,
            },
            {
                "key_id": "key2",
                "name": "Key 2",
                "key_prefix": "hk_test_def",
                "created_at": datetime.datetime.utcnow().isoformat(),
                "is_active": False,
            },
        ]
        mock_db_connection.execute.return_value = mock_result

        # Act
        result = db_ops.get_api_keys_by_user("user123")

        # Assert
        assert len(result) == 2
        assert result[0]["key_id"] == "key1"
        assert result[1]["key_id"] == "key2"

        call_args = mock_db_connection.execute.call_args[0][0]
        assert "SELECT * FROM api_keys WHERE user_id = ?" in call_args

    def test_update_api_key(self, db_ops, mock_db_connection):
        """Test updating an API key."""
        # Arrange
        updates = {"is_active": False, "last_used_at": datetime.datetime.utcnow()}

        # Act
        db_ops.update_api_key("key123", updates)

        # Assert
        mock_db_connection.execute.assert_called_once()
        call_args = mock_db_connection.execute.call_args[0][0]
        assert "UPDATE api_keys SET" in call_args
        assert "is_active = ?" in call_args
        assert "last_used_at = ?" in call_args
        assert "WHERE key_id = ?" in call_args

    def test_delete_api_key(self, db_ops, mock_db_connection):
        """Test deleting an API key."""
        # Act
        db_ops.delete_api_key("key123")

        # Assert
        mock_db_connection.execute.assert_called_once()
        call_args = mock_db_connection.execute.call_args[0][0]
        assert "DELETE FROM api_keys WHERE key_id = ?" in call_args

    def test_log_api_key_usage(self, db_ops, mock_db_connection):
        """Test logging API key usage."""
        # Arrange
        usage_data = {
            "api_key_id": "key123",
            "endpoint": "/api/v1/models",
            "timestamp": datetime.datetime.utcnow(),
            "response_time_ms": 150,
            "status_code": 200,
        }

        # Act
        db_ops.log_api_key_usage(usage_data)

        # Assert
        mock_db_connection.execute.assert_called_once()
        call_args = mock_db_connection.execute.call_args[0][0]
        assert "INSERT INTO api_key_usage" in call_args

    def test_get_usage_stats(self, db_ops, mock_db_connection):
        """Test getting usage statistics for an API key."""
        # Arrange
        mock_result = Mock()
        mock_result.fetchone.return_value = {
            "total_requests": 1500,
            "avg_response_time": 123.45,
            "error_count": 15,
        }
        mock_db_connection.execute.return_value = mock_result

        # Act
        result = db_ops.get_usage_stats("key123", hours=24)

        # Assert
        assert result["total_requests"] == 1500
        assert result["avg_response_time"] == 123.45
        assert result["error_rate"] == 0.01  # 15/1500

        call_args = mock_db_connection.execute.call_args[0][0]
        assert "COUNT(*) as total_requests" in call_args
        assert "AVG(response_time_ms) as avg_response_time" in call_args

    def test_cleanup_expired_keys(self, db_ops, mock_db_connection):
        """Test cleaning up expired API keys."""
        # Arrange
        mock_result = Mock()
        mock_result.rowcount = 3
        mock_db_connection.execute.return_value = mock_result

        # Act
        count = db_ops.cleanup_expired_keys()

        # Assert
        assert count == 3
        call_args = mock_db_connection.execute.call_args[0][0]
        assert "UPDATE api_keys SET is_active = ?" in call_args
        assert "WHERE expires_at < ?" in call_args
        assert "AND is_active = ?" in call_args

    def test_transaction_handling(self, db_ops, mock_db_connection):
        """Test database transaction handling."""
        # Arrange
        mock_db_connection.begin.return_value.__enter__ = Mock()
        mock_db_connection.begin.return_value.__exit__ = Mock()

        # Act
        with db_ops.transaction():
            db_ops.save_api_key({"key_id": "key1"})
            db_ops.save_api_key({"key_id": "key2"})

        # Assert
        mock_db_connection.begin.assert_called_once()
        assert mock_db_connection.execute.call_count == 2
