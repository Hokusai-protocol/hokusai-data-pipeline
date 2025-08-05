"""Unit tests for Redis publisher."""

import json
import time
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import redis

from src.events.publishers.redis_publisher import RedisPublisher
from src.events.publishers.base import PublisherException
from src.events.schemas import MessageEnvelope, ModelReadyToDeployMessage


class TestRedisPublisher:
    """Test cases for RedisPublisher."""
    
    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        with patch("redis.ConnectionPool.from_url") as mock_pool:
            mock_client = MagicMock(spec=redis.Redis)
            mock_client.ping.return_value = True
            mock_client.lpush.return_value = 1
            mock_client.llen.return_value = 5
            mock_client.info.return_value = {
                "connected_clients": 10,
                "used_memory_human": "100M"
            }
            
            with patch("redis.Redis", return_value=mock_client):
                yield mock_client
    
    def test_publisher_initialization(self, mock_redis):
        """Test publisher initialization."""
        publisher = RedisPublisher(redis_url="redis://localhost:6379/0")
        
        assert publisher.redis_url == "redis://localhost:6379/0"
        assert publisher.retry_config["max_retries"] == 3
        mock_redis.ping.assert_called_once()
    
    def test_publish_success(self, mock_redis):
        """Test successful message publishing."""
        publisher = RedisPublisher()
        
        message = {
            "model_id": "test-model-123",
            "token_symbol": "test-token",
            "metric_name": "accuracy",
            "baseline_value": 0.8,
            "current_value": 0.85,
            "model_name": "test_model",
            "model_version": "1",
            "mlflow_run_id": "abc123",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        result = publisher.publish(message)
        
        assert result is True
        mock_redis.lpush.assert_called()
        
        # Verify the message was properly enveloped
        call_args = mock_redis.lpush.call_args[0]
        queue_name = call_args[0]
        message_json = call_args[1]
        
        assert queue_name == "hokusai:model_ready_queue"
        
        # Parse and verify envelope
        envelope = json.loads(message_json)
        assert envelope["message_type"] == "model_ready_to_deploy"
        assert envelope["payload"] == message
        assert "message_id" in envelope
        assert "timestamp" in envelope
    
    def test_publish_with_retry(self, mock_redis):
        """Test publishing with retry on failure."""
        publisher = RedisPublisher(retry_config={
            "max_retries": 2,
            "base_delay": 0.1,
            "max_delay": 0.5
        })
        
        # First call fails, second succeeds
        mock_redis.lpush.side_effect = [redis.RedisError("Connection error"), 1]
        
        message = {"test": "message"}
        
        with patch("time.sleep") as mock_sleep:
            result = publisher.publish(message)
        
        assert result is True
        assert mock_redis.lpush.call_count == 2
        mock_sleep.assert_called_once()
    
    def test_publish_failure_after_retries(self, mock_redis):
        """Test publishing failure after all retries."""
        publisher = RedisPublisher(retry_config={
            "max_retries": 1,
            "base_delay": 0.1,
            "max_delay": 0.5
        })
        
        mock_redis.lpush.side_effect = redis.RedisError("Persistent error")
        
        message = {"test": "message"}
        
        with patch("time.sleep"):
            with pytest.raises(PublisherException):
                publisher.publish(message)
    
    def test_publish_model_ready(self, mock_redis):
        """Test convenience method for model_ready_to_deploy messages."""
        publisher = RedisPublisher()
        
        result = publisher.publish_model_ready(
            model_id="model-123",
            token_symbol="test-token",
            metric_name="accuracy",
            baseline_value=0.8,
            current_value=0.85,
            model_name="test_model",
            model_version="1",
            mlflow_run_id="run123",
            contributor_address="0x1234567890123456789012345678901234567890",
            experiment_name="test_experiment"
        )
        
        assert result is True
        mock_redis.lpush.assert_called()
        
        # Verify the message structure
        call_args = mock_redis.lpush.call_args[0]
        message_json = call_args[1]
        envelope = json.loads(message_json)
        
        payload = envelope["payload"]
        assert payload["model_id"] == "model-123"
        assert payload["token_symbol"] == "test-token"
        assert payload["improvement_percentage"] == 6.25  # (0.85-0.8)/0.8 * 100
    
    def test_health_check_healthy(self, mock_redis):
        """Test health check when Redis is healthy."""
        publisher = RedisPublisher()
        
        health = publisher.health_check()
        
        assert health["status"] == "healthy"
        assert "latency_ms" in health
        assert health["queue_depths"]["main"] == 5
        assert health["connected_clients"] == 10
        assert health["used_memory_human"] == "100M"
    
    def test_health_check_unhealthy(self, mock_redis):
        """Test health check when Redis is unhealthy."""
        publisher = RedisPublisher()
        mock_redis.ping.side_effect = redis.ConnectionError("Cannot connect")
        
        health = publisher.health_check()
        
        assert health["status"] == "unhealthy"
        assert "error" in health
        assert health["queue_depths"]["main"] is None
    
    def test_get_queue_depth(self, mock_redis):
        """Test getting queue depth."""
        publisher = RedisPublisher()
        
        depth = publisher.get_queue_depth("test-queue")
        
        assert depth == 5
        mock_redis.llen.assert_called_with("test-queue")
    
    def test_close_connection(self, mock_redis):
        """Test closing connections."""
        with patch("redis.ConnectionPool") as mock_pool_class:
            mock_pool = MagicMock()
            mock_pool_class.from_url.return_value = mock_pool
            
            publisher = RedisPublisher()
            publisher.pool = mock_pool
            
            publisher.close()
            
            mock_pool.disconnect.assert_called_once()
    
    def test_invalid_message_validation(self, mock_redis):
        """Test that invalid messages are rejected."""
        publisher = RedisPublisher()
        
        with pytest.raises(PublisherException, match="Invalid message format"):
            publisher.publish_model_ready(
                model_id="",  # Empty model_id should fail validation
                token_symbol="test-token",
                metric_name="accuracy",
                baseline_value=0.8,
                current_value=0.85,
                model_name="test_model",
                model_version="1",
                mlflow_run_id="run123"
            )
    
    def test_message_envelope_retry_logic(self):
        """Test MessageEnvelope retry logic."""
        envelope = MessageEnvelope(
            message_id="test-123",
            message_type="test",
            payload={"test": "data"},
            timestamp=datetime.utcnow(),
            retry_count=0,
            max_retries=3
        )
        
        assert envelope.should_retry() is True
        
        envelope.increment_retry()
        assert envelope.retry_count == 1
        assert envelope.should_retry() is True
        
        envelope.retry_count = 3
        assert envelope.should_retry() is False
    
    def test_model_ready_message_validation(self):
        """Test ModelReadyToDeployMessage validation."""
        # Valid message
        message = ModelReadyToDeployMessage(
            model_id="model-123",
            token_symbol="test-token",
            metric_name="accuracy",
            baseline_value=0.8,
            current_value=0.85,
            model_name="test_model",
            model_version="1",
            mlflow_run_id="run123"
        )
        
        assert message.validate() is True
        assert message.improvement_percentage == 6.25
        
        # Invalid token symbol
        with pytest.raises(ValueError):
            ModelReadyToDeployMessage(
                model_id="model-123",
                token_symbol="",  # Empty token symbol
                metric_name="accuracy",
                baseline_value=0.8,
                current_value=0.85,
                model_name="test_model",
                model_version="1",
                mlflow_run_id="run123"
            )