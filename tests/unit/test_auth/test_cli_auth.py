"""Unit tests for API key CLI commands."""

import datetime
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from src.cli.auth import (
    auth_group,
    create_key,
    list_keys,
    revoke_key,
    rotate_key
)


class TestAuthCLI:
    """Test cases for authentication CLI commands."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_api_key_service(self):
        """Mock API key service."""
        with patch('src.cli.auth.get_api_key_service') as mock_get_service:
            mock_service = Mock()
            mock_get_service.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_auth_config(self):
        """Mock authentication configuration."""
        with patch('src.cli.auth.get_auth_config') as mock_config:
            mock_config.return_value = {
                "user_id": "test_user_123",
                "api_endpoint": "http://localhost:8000"
            }
            yield mock_config

    def test_create_key_basic(self, runner, mock_api_key_service, mock_auth_config):
        """Test basic API key creation via CLI."""
        # Arrange
        mock_key = Mock(
            key="hk_live_new_key_123",
            key_id="key123",
            name="My API Key",
            created_at=datetime.datetime.utcnow()
        )
        mock_api_key_service.generate_api_key.return_value = mock_key
        
        # Act
        result = runner.invoke(create_key, ["--name", "My API Key"])
        
        # Assert
        assert result.exit_code == 0
        assert "API key created successfully" in result.output
        assert "hk_live_new_key_123" in result.output
        assert "Save this key securely" in result.output

    def test_create_key_with_environment(self, runner, mock_api_key_service, mock_auth_config):
        """Test creating API key with specific environment."""
        # Arrange
        mock_key = Mock(
            key="hk_test_new_key_123",
            key_id="key123",
            name="Test Key",
            created_at=datetime.datetime.utcnow()
        )
        mock_api_key_service.generate_api_key.return_value = mock_key
        
        # Act
        result = runner.invoke(create_key, [
            "--name", "Test Key",
            "--environment", "test"
        ])
        
        # Assert
        assert result.exit_code == 0
        assert "hk_test_new_key_123" in result.output
        mock_api_key_service.generate_api_key.assert_called_with(
            user_id="test_user_123",
            key_name="Test Key",
            environment="test",
            expires_at=None,
            rate_limit_per_hour=1000,
            allowed_ips=None
        )

    def test_create_key_with_rate_limit(self, runner, mock_api_key_service, mock_auth_config):
        """Test creating API key with custom rate limit."""
        # Arrange
        mock_key = Mock(
            key="hk_live_limited_key_123",
            key_id="key123",
            name="Limited Key",
            created_at=datetime.datetime.utcnow(),
            rate_limit_per_hour=500
        )
        mock_api_key_service.generate_api_key.return_value = mock_key
        
        # Act
        result = runner.invoke(create_key, [
            "--name", "Limited Key",
            "--rate-limit", "500"
        ])
        
        # Assert
        assert result.exit_code == 0
        assert "Rate limit: 500/hour" in result.output
        mock_api_key_service.generate_api_key.assert_called_with(
            user_id="test_user_123",
            key_name="Limited Key",
            environment="production",
            expires_at=None,
            rate_limit_per_hour=500,
            allowed_ips=None
        )

    def test_create_key_with_expiration(self, runner, mock_api_key_service, mock_auth_config):
        """Test creating API key with expiration."""
        # Arrange
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=30)
        mock_key = Mock(
            key="hk_live_temp_key_123",
            key_id="key123",
            name="Temporary Key",
            created_at=datetime.datetime.utcnow(),
            expires_at=expires_at
        )
        mock_api_key_service.generate_api_key.return_value = mock_key
        
        # Act
        result = runner.invoke(create_key, [
            "--name", "Temporary Key",
            "--expires-in-days", "30"
        ])
        
        # Assert
        assert result.exit_code == 0
        assert "Expires" in result.output

    def test_create_key_with_ip_restriction(self, runner, mock_api_key_service, mock_auth_config):
        """Test creating API key with IP restrictions."""
        # Arrange
        mock_key = Mock(
            key="hk_live_restricted_key_123",
            key_id="key123",
            name="IP Restricted Key",
            created_at=datetime.datetime.utcnow(),
            allowed_ips=["192.168.1.1", "10.0.0.1"]
        )
        mock_api_key_service.generate_api_key.return_value = mock_key
        
        # Act
        result = runner.invoke(create_key, [
            "--name", "IP Restricted Key",
            "--allowed-ip", "192.168.1.1",
            "--allowed-ip", "10.0.0.1"
        ])
        
        # Assert
        assert result.exit_code == 0
        assert "Allowed IPs: 192.168.1.1, 10.0.0.1" in result.output

    def test_create_key_error_handling(self, runner, mock_api_key_service, mock_auth_config):
        """Test error handling in key creation."""
        # Arrange
        mock_api_key_service.generate_api_key.side_effect = Exception("Service error")
        
        # Act
        result = runner.invoke(create_key, ["--name", "Error Key"])
        
        # Assert
        assert result.exit_code == 1
        assert "Error creating API key" in result.output

    def test_list_keys_success(self, runner, mock_api_key_service, mock_auth_config):
        """Test listing API keys."""
        # Arrange
        mock_keys = [
            Mock(
                key_id="key1",
                name="Production Key",
                key_prefix="hk_live_abc***",
                created_at=datetime.datetime(2024, 1, 1, 12, 0),
                last_used_at=datetime.datetime(2024, 1, 2, 15, 30),
                is_active=True,
                expires_at=None
            ),
            Mock(
                key_id="key2",
                name="Test Key",
                key_prefix="hk_test_def***",
                created_at=datetime.datetime(2024, 1, 1, 10, 0),
                last_used_at=None,
                is_active=True,
                expires_at=datetime.datetime(2024, 2, 1, 12, 0)
            ),
            Mock(
                key_id="key3",
                name="Revoked Key",
                key_prefix="hk_live_ghi***",
                created_at=datetime.datetime(2024, 1, 1, 8, 0),
                last_used_at=datetime.datetime(2024, 1, 1, 9, 0),
                is_active=False,
                expires_at=None
            )
        ]
        mock_api_key_service.list_api_keys.return_value = mock_keys
        
        # Act
        result = runner.invoke(list_keys)
        
        # Assert
        assert result.exit_code == 0
        assert "Production Key" in result.output
        assert "hk_live_abc***" in result.output
        assert "Active" in result.output
        assert "Test Key" in result.output
        assert "hk_test_def***" in result.output
        assert "Revoked Key" in result.output
        assert "Inactive" in result.output
        assert "API Keys (3 total)" in result.output

    def test_list_keys_empty(self, runner, mock_api_key_service, mock_auth_config):
        """Test listing when no API keys exist."""
        # Arrange
        mock_api_key_service.list_api_keys.return_value = []
        
        # Act
        result = runner.invoke(list_keys)
        
        # Assert
        assert result.exit_code == 0
        assert "No API keys found" in result.output

    def test_list_keys_active_only(self, runner, mock_api_key_service, mock_auth_config):
        """Test listing only active API keys."""
        # Arrange
        mock_keys = [
            Mock(
                key_id="key1",
                name="Active Key",
                key_prefix="hk_live_abc***",
                created_at=datetime.datetime.utcnow(),
                last_used_at=None,
                is_active=True,
                expires_at=None
            )
        ]
        mock_api_key_service.list_api_keys.return_value = mock_keys
        
        # Act
        result = runner.invoke(list_keys, ["--active-only"])
        
        # Assert
        assert result.exit_code == 0
        assert "Active Key" in result.output
        mock_api_key_service.list_api_keys.assert_called_with(
            "test_user_123",
            active_only=True
        )

    def test_revoke_key_success(self, runner, mock_api_key_service, mock_auth_config):
        """Test successful API key revocation."""
        # Arrange
        mock_api_key_service.revoke_api_key.return_value = True
        
        # Act
        result = runner.invoke(revoke_key, ["key123"], input="y\n")
        
        # Assert
        assert result.exit_code == 0
        assert "API key revoked successfully" in result.output
        mock_api_key_service.revoke_api_key.assert_called_with(
            "test_user_123",
            "key123"
        )

    def test_revoke_key_cancelled(self, runner, mock_api_key_service, mock_auth_config):
        """Test cancelled API key revocation."""
        # Act
        result = runner.invoke(revoke_key, ["key123"], input="n\n")
        
        # Assert
        assert result.exit_code == 0
        assert "Revocation cancelled" in result.output
        mock_api_key_service.revoke_api_key.assert_not_called()

    def test_revoke_key_force(self, runner, mock_api_key_service, mock_auth_config):
        """Test forced API key revocation without confirmation."""
        # Arrange
        mock_api_key_service.revoke_api_key.return_value = True
        
        # Act
        result = runner.invoke(revoke_key, ["key123", "--force"])
        
        # Assert
        assert result.exit_code == 0
        assert "API key revoked successfully" in result.output
        # No confirmation prompt with --force

    def test_revoke_key_not_found(self, runner, mock_api_key_service, mock_auth_config):
        """Test revoking non-existent API key."""
        # Arrange
        from src.auth.api_key_service import APIKeyNotFoundError
        mock_api_key_service.revoke_api_key.side_effect = APIKeyNotFoundError("Key not found")
        
        # Act
        result = runner.invoke(revoke_key, ["nonexistent"], input="y\n")
        
        # Assert
        assert result.exit_code == 1
        assert "API key not found" in result.output

    def test_rotate_key_success(self, runner, mock_api_key_service, mock_auth_config):
        """Test successful API key rotation."""
        # Arrange
        mock_new_key = Mock(
            key="hk_live_rotated_key_456",
            key_id="key456",
            name="Production Key",
            created_at=datetime.datetime.utcnow()
        )
        mock_api_key_service.rotate_api_key.return_value = mock_new_key
        
        # Act
        result = runner.invoke(rotate_key, ["key123"], input="y\n")
        
        # Assert
        assert result.exit_code == 0
        assert "API key rotated successfully" in result.output
        assert "hk_live_rotated_key_456" in result.output
        assert "Save this new key securely" in result.output

    def test_rotate_key_cancelled(self, runner, mock_api_key_service, mock_auth_config):
        """Test cancelled API key rotation."""
        # Act
        result = runner.invoke(rotate_key, ["key123"], input="n\n")
        
        # Assert
        assert result.exit_code == 0
        assert "Rotation cancelled" in result.output
        mock_api_key_service.rotate_api_key.assert_not_called()

    def test_auth_config_missing(self, runner):
        """Test handling of missing authentication configuration."""
        # Arrange
        with patch('src.cli.auth.get_auth_config') as mock_config:
            mock_config.return_value = None
            
            # Act
            result = runner.invoke(create_key, ["--name", "Test Key"])
        
        # Assert
        assert result.exit_code == 1
        assert "Authentication not configured" in result.output

    def test_cli_output_formatting(self, runner, mock_api_key_service, mock_auth_config):
        """Test CLI output formatting for better readability."""
        # Arrange
        mock_key = Mock(
            key="hk_live_formatted_key_123",
            key_id="key123",
            name="Formatted Key",
            created_at=datetime.datetime.utcnow(),
            rate_limit_per_hour=1000,
            allowed_ips=["192.168.1.1"],
            expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=30)
        )
        mock_api_key_service.generate_api_key.return_value = mock_key
        
        # Act
        result = runner.invoke(create_key, [
            "--name", "Formatted Key",
            "--rate-limit", "1000",
            "--allowed-ip", "192.168.1.1",
            "--expires-in-days", "30"
        ])
        
        # Assert
        assert result.exit_code == 0
        # Check for formatted output sections
        assert "━" in result.output  # Table borders
        assert "API Key Details" in result.output
        assert "Key ID:" in result.output
        assert "Name:" in result.output
        assert "Rate Limit:" in result.output
        assert "Allowed IPs:" in result.output
        assert "Expires:" in result.output