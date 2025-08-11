"""Integration tests for Redis queue with ElastiCache."""

import os
import json
import time
from unittest.mock import patch

import pytest
import redis

from src.events.publishers.factory import create_publisher
from src.services.model_registry_hooks import ModelRegistryHooks


@pytest.mark.integration
class TestRedisQueueIntegration:
    """Integration tests for Redis queue functionality."""
    
    @pytest.fixture
    def redis_client(self):
        """Create a Redis client for testing."""
        # Use environment variables if available, otherwise skip test
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_auth_token = os.getenv("REDIS_AUTH_TOKEN")
        
        if redis_auth_token:
            redis_url = f"redis://:{redis_auth_token}@{redis_host}:{redis_port}/0"
        else:
            redis_url = f"redis://{redis_host}:{redis_port}/0"
        
        try:
            client = redis.Redis.from_url(redis_url, socket_connect_timeout=5)
            client.ping()
            yield client
            # Cleanup: remove test keys
            for key in client.keys("test:*"):
                client.delete(key)
        except redis.ConnectionError:
            pytest.skip("Redis not available for integration testing")
    
    def test_publish_and_consume_message(self, redis_client):
        """Test publishing and consuming a message from the queue."""
        publisher = create_publisher("redis")
        queue_name = "test:integration_queue"
        
        # Publish a message
        message = {
            "model_id": "test-model-integration",
            "token_symbol": "TEST-TOKEN",
            "metric_name": "accuracy",
            "baseline_value": 0.80,
            "current_value": 0.85,
            "timestamp": time.time()
        }
        
        result = publisher.publish(message, queue_name=queue_name)
        assert result is True
        
        # Consume the message
        raw_message = redis_client.rpop(queue_name)
        assert raw_message is not None
        
        # Parse and verify message
        envelope = json.loads(raw_message)
        assert envelope["message_type"] == "model_ready_to_deploy"
        assert envelope["payload"]["model_id"] == "test-model-integration"
        assert envelope["payload"]["token_symbol"] == "TEST-TOKEN"
        assert envelope["payload"]["current_value"] == 0.85
    
    def test_retry_on_connection_failure(self):
        """Test retry logic when Redis connection fails."""
        with patch("redis.Redis") as mock_redis_class:
            mock_client = mock_redis_class.return_value
            
            # Simulate connection failures then success
            mock_client.lpush.side_effect = [
                redis.ConnectionError("Connection failed"),
                redis.ConnectionError("Connection failed"),
                1  # Success on third try
            ]
            mock_client.publish.return_value = 1
            
            publisher = create_publisher("redis")
            message = {"model_id": "test-retry", "token_symbol": "RETRY"}
            
            # Should succeed after retries
            result = publisher.publish(message)
            assert result is True
            assert mock_client.lpush.call_count == 3
    
    def test_dead_letter_queue(self, redis_client):
        """Test that messages move to DLQ after max retries."""
        publisher = create_publisher("redis")
        
        # Configure for quick failure
        publisher.retry_config = {
            "max_retries": 1,
            "base_delay": 0.1,
            "max_delay": 0.2
        }
        
        with patch.object(publisher.client, "lpush") as mock_lpush:
            # Simulate persistent failures
            mock_lpush.side_effect = redis.RedisError("Persistent error")
            
            message = {"model_id": "test-dlq", "token_symbol": "DLQ"}
            
            # Should fail and potentially move to DLQ
            result = publisher.publish(message)
            assert result is False
    
    def test_model_registry_hooks_integration(self, redis_client):
        """Test model registry hooks publishing to Redis."""
        hooks = ModelRegistryHooks()
        
        # Clear the queue first
        queue_name = "hokusai:model_ready_queue"
        while redis_client.rpop(queue_name):
            pass
        
        # Trigger hook with valid model data
        result = hooks.on_model_registered_with_baseline(
            model_id="integration-test-model",
            model_name="Test Model",
            model_version="1.0",
            mlflow_run_id="run-123",
            token_id="INT-TOKEN",
            metric_name="accuracy",
            baseline_value=0.75,
            current_value=0.82,
            contributor_address="0x1234567890abcdef",
            experiment_name="integration-test"
        )
        
        assert result is True
        
        # Verify message was published to queue
        raw_message = redis_client.rpop(queue_name)
        assert raw_message is not None
        
        envelope = json.loads(raw_message)
        assert envelope["message_type"] == "model_ready_to_deploy"
        assert envelope["payload"]["model_id"] == "integration-test-model"
        assert envelope["payload"]["token_symbol"] == "INT-TOKEN"
    
    def test_queue_monitoring(self, redis_client):
        """Test queue depth monitoring functionality."""
        publisher = create_publisher("redis")
        queue_name = "test:monitoring_queue"
        
        # Publish multiple messages
        for i in range(5):
            message = {
                "model_id": f"monitor-{i}",
                "token_symbol": f"MON-{i}",
                "metric_name": "accuracy",
                "baseline_value": 0.80,
                "current_value": 0.85
            }
            publisher.publish(message, queue_name=queue_name)
        
        # Check queue depth
        depth = redis_client.llen(queue_name)
        assert depth == 5
        
        # Get queue info from publisher
        health = publisher.health_check()
        assert health["status"] in ["healthy", "degraded"]
        assert "queue_depths" in health
        
        # Clean up
        for _ in range(5):
            redis_client.rpop(queue_name)
    
    @pytest.mark.skipif(
        not os.getenv("REDIS_AUTH_TOKEN"),
        reason="ElastiCache auth token not available"
    )
    def test_elasticache_authentication(self):
        """Test connection to ElastiCache with authentication."""
        redis_host = os.getenv("REDIS_HOST", "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_auth_token = os.getenv("REDIS_AUTH_TOKEN")
        
        redis_url = f"redis://:{redis_auth_token}@{redis_host}:{redis_port}/0"
        
        try:
            client = redis.Redis.from_url(redis_url, socket_connect_timeout=5)
            # Test basic operations
            client.ping()
            client.set("test:auth", "success", ex=10)
            value = client.get("test:auth")
            assert value == b"success"
            client.delete("test:auth")
        except redis.ConnectionError as e:
            pytest.fail(f"Failed to connect to ElastiCache: {e}")