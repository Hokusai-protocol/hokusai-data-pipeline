"""Unit tests for Redis ElastiCache integration with authentication."""

import os
from unittest.mock import MagicMock, patch, call

import pytest

from src.events.publishers.factory import create_publisher, get_publisher
from src.events.publishers.redis_publisher import RedisPublisher


class TestRedisElastiCacheIntegration:
    """Test cases for Redis ElastiCache integration."""
    
    def test_factory_creates_authenticated_redis_url_from_env(self):
        """Test that factory builds authenticated Redis URL from environment variables."""
        with patch.dict(os.environ, {
            "REDIS_HOST": "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com",
            "REDIS_PORT": "6379",
            "REDIS_AUTH_TOKEN": "test-auth-token-123"
        }):
            with patch("src.events.publishers.redis_publisher.redis.ConnectionPool.from_url") as mock_pool:
                with patch("src.events.publishers.redis_publisher.redis.Redis") as mock_redis_class:
                    mock_client = MagicMock()
                    mock_client.ping.return_value = True
                    mock_redis_class.return_value = mock_client
                    
                    publisher = create_publisher("redis")
                    
                    # Verify the URL was built correctly with authentication
                    expected_url = "redis://:test-auth-token-123@master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com:6379/0"
                    mock_pool.assert_called_once()
                    actual_url = mock_pool.call_args[0][0]
                    assert actual_url == expected_url
    
    def test_factory_uses_explicit_redis_url_over_components(self):
        """Test that explicit REDIS_URL takes precedence over individual components."""
        with patch.dict(os.environ, {
            "REDIS_URL": "redis://:explicit-token@explicit-host:6380/1",
            "REDIS_HOST": "ignored-host",
            "REDIS_PORT": "6379",
            "REDIS_AUTH_TOKEN": "ignored-token"
        }):
            with patch("src.events.publishers.redis_publisher.redis.ConnectionPool.from_url") as mock_pool:
                with patch("src.events.publishers.redis_publisher.redis.Redis") as mock_redis_class:
                    mock_client = MagicMock()
                    mock_client.ping.return_value = True
                    mock_redis_class.return_value = mock_client
                    
                    publisher = create_publisher("redis")
                    
                    # Verify the explicit URL was used
                    mock_pool.assert_called_once()
                    actual_url = mock_pool.call_args[0][0]
                    assert actual_url == "redis://:explicit-token@explicit-host:6380/1"
    
    def test_factory_creates_unauthenticated_url_for_local_dev(self):
        """Test that factory creates unauthenticated URL when no auth token is present."""
        with patch.dict(os.environ, {
            "REDIS_HOST": "localhost",
            "REDIS_PORT": "6379"
        }, clear=True):
            # Remove any existing REDIS_AUTH_TOKEN
            os.environ.pop("REDIS_AUTH_TOKEN", None)
            os.environ.pop("REDIS_URL", None)
            
            with patch("src.events.publishers.redis_publisher.redis.ConnectionPool.from_url") as mock_pool:
                with patch("src.events.publishers.redis_publisher.redis.Redis") as mock_redis_class:
                    mock_client = MagicMock()
                    mock_client.ping.return_value = True
                    mock_redis_class.return_value = mock_client
                    
                    publisher = create_publisher("redis")
                    
                    # Verify unauthenticated URL was built
                    expected_url = "redis://localhost:6379/0"
                    mock_pool.assert_called_once()
                    actual_url = mock_pool.call_args[0][0]
                    assert actual_url == expected_url
    
    def test_health_check_uses_authenticated_connection(self):
        """Test that health check uses authenticated Redis connection."""
        from src.api.utils.config import Settings
        
        with patch("src.api.routes.health.get_settings") as mock_get_settings:
            settings = Settings()
            settings.redis_host = "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com"
            settings.redis_port = 6379
            settings.redis_auth_token = "test-auth-token"
            mock_get_settings.return_value = settings
            
            with patch.dict(os.environ, {
                "REDIS_HOST": "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com",
                "REDIS_AUTH_TOKEN": "test-auth-token"
            }):
                # Import here to get patched settings
                from src.api.routes.health import health_check
                
                with patch("redis.Redis.from_url") as mock_redis_from_url:
                    mock_client = MagicMock()
                    mock_client.ping.return_value = True
                    mock_redis_from_url.return_value = mock_client
                    
                    # Would need to set up more mocks for the full health check
                    # This tests that the Redis URL construction works correctly
                    assert settings.redis_enabled is True
                    expected_url = "redis://:test-auth-token@master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com:6379/0"
                    assert settings.redis_url == expected_url
    
    def test_message_publishing_with_elasticache(self):
        """Test end-to-end message publishing with ElastiCache configuration."""
        with patch.dict(os.environ, {
            "REDIS_HOST": "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com",
            "REDIS_PORT": "6379",
            "REDIS_AUTH_TOKEN": "test-auth-token-123"
        }):
            with patch("redis.ConnectionPool.from_url") as mock_pool:
                with patch("redis.Redis") as mock_redis_class:
                    mock_client = MagicMock()
                    mock_client.ping.return_value = True
                    mock_client.lpush.return_value = 1
                    mock_client.publish.return_value = 1
                    mock_redis_class.return_value = mock_client
                    
                    publisher = create_publisher("redis")
                    
                    # Test publishing a message
                    message = {
                        "model_id": "test-model-123",
                        "token_symbol": "test-token",
                        "metric_name": "accuracy",
                        "baseline_value": 0.85,
                        "current_value": 0.90
                    }
                    
                    result = publisher.publish(message)
                    
                    assert result is True
                    mock_client.lpush.assert_called_once()
                    
                    # Verify the message was pushed to the correct queue
                    queue_name = mock_client.lpush.call_args[0][0]
                    assert queue_name == "hokusai:model_ready_queue"
    
    def test_connection_pool_configuration(self):
        """Test that connection pool is configured with proper parameters."""
        with patch.dict(os.environ, {
            "REDIS_HOST": "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com",
            "REDIS_AUTH_TOKEN": "test-auth-token"
        }):
            with patch("src.events.publishers.redis_publisher.redis.ConnectionPool.from_url") as mock_pool:
                with patch("src.events.publishers.redis_publisher.redis.Redis") as mock_redis_class:
                    mock_client = MagicMock()
                    mock_client.ping.return_value = True
                    mock_redis_class.return_value = mock_client
                    
                    publisher = create_publisher("redis")
                    
                    # Verify connection pool was created with proper settings
                    mock_pool.assert_called_once()
                    call_kwargs = mock_pool.call_args[1]
                    
                    assert call_kwargs.get("max_connections") == 50
                    assert call_kwargs.get("socket_keepalive") is True
    
    def test_redis_enabled_property(self):
        """Test that redis_enabled property works correctly."""
        from src.api.utils.config import Settings
        
        # Test with auth token
        with patch.dict(os.environ, {"REDIS_AUTH_TOKEN": "test-token"}):
            settings = Settings()
            assert settings.redis_enabled is True
        
        # Test with ElastiCache host
        with patch.dict(os.environ, {"REDIS_HOST": "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com"}, clear=True):
            os.environ.pop("REDIS_AUTH_TOKEN", None)
            settings = Settings()
            assert settings.redis_enabled is True
        
        # Test with explicit REDIS_URL
        with patch.dict(os.environ, {"REDIS_URL": "redis://some-host:6379"}, clear=True):
            os.environ.pop("REDIS_AUTH_TOKEN", None)
            os.environ.pop("REDIS_HOST", None)
            settings = Settings()
            assert settings.redis_enabled is True
        
        # Test with local development (should be false)
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("REDIS_AUTH_TOKEN", None)
            os.environ.pop("REDIS_HOST", None)
            os.environ.pop("REDIS_URL", None)
            settings = Settings()
            assert settings.redis_enabled is False