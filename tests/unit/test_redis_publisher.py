"""Unit tests for Redis publisher."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import redis

from src.events.publishers.base import PublisherException
from src.events.publishers.redis_publisher import RedisPublisherWithCircuitBreaker
from src.events.schemas import MessageEnvelope, ModelReadyToDeployMessage


class TestRedisPublisher:
    """Test cases for RedisPublisherWithCircuitBreaker."""

    @pytest.fixture
    def mock_redis(self):
        with patch("redis.ConnectionPool.from_url") as mock_pool:
            mock_client = MagicMock(spec=redis.Redis)
            mock_client.ping.return_value = True
            mock_client.lpush.return_value = 1
            mock_client.llen.return_value = 5
            mock_client.info.return_value = {
                "connected_clients": 10,
                "used_memory_human": "100M",
            }
            with patch("redis.Redis", return_value=mock_client):
                with patch("src.utils.circuit_breaker.get_redis_circuit_breaker") as mock_cb:
                    cb = MagicMock()
                    cb.__enter__.return_value = None
                    cb.__exit__.return_value = None
                    cb.get_stats.return_value = {"state": "CLOSED"}
                    mock_cb.return_value = cb
                    yield mock_client

    def test_publisher_initialization(self, mock_redis):
        publisher = RedisPublisherWithCircuitBreaker(redis_url="redis://localhost:6379/0")
        assert publisher.redis_url == "redis://localhost:6379/0"
        assert publisher.retry_config["max_retries"] == 3
        mock_redis.ping.assert_called_once()

    def test_publish_success(self, mock_redis):
        publisher = RedisPublisherWithCircuitBreaker()
        message = {
            "model_id": "test-model-123",
            "token_symbol": "test-token",
            "metric_name": "accuracy",
            "baseline_value": 0.8,
            "current_value": 0.85,
            "model_name": "test_model",
            "model_version": "1",
            "mlflow_run_id": "abc123",
        }

        result = publisher.publish(message)

        assert result is True
        mock_redis.lpush.assert_called()
        queue_name, message_json = mock_redis.lpush.call_args[0]
        assert queue_name == "hokusai:model_ready_queue"

        envelope = json.loads(message_json)
        assert envelope["message_type"] == "model_ready_to_deploy"
        assert envelope["payload"] == message
        assert "message_id" in envelope

    def test_publish_failure_after_retries(self, mock_redis):
        publisher = RedisPublisherWithCircuitBreaker(
            retry_config={"max_retries": 1, "base_delay": 0.01, "max_delay": 0.01}
        )
        mock_redis.lpush.side_effect = redis.RedisError("Persistent error")

        with patch("time.sleep"):
            with pytest.raises(PublisherException):
                publisher.publish({"test": "message"})

    def test_publish_model_ready(self, mock_redis):
        publisher = RedisPublisherWithCircuitBreaker()

        with patch.object(publisher, "publish", return_value=True) as mock_publish:
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
                experiment_name="test_experiment",
            )

            assert result is True
            published_message = mock_publish.call_args[0][0]
            assert published_message["model_id"] == "model-123"
            assert published_message["token_symbol"] == "test-token"
            assert published_message["improvement_percentage"] == pytest.approx(6.25)

    def test_health_check_healthy(self, mock_redis):
        publisher = RedisPublisherWithCircuitBreaker()
        health = publisher.health_check()

        assert health["status"] == "healthy"
        assert "latency_ms" in health
        assert health["queue_depths"]["main"] == 5
        assert health["connected_clients"] == 10
        assert health["used_memory_human"] == "100M"

    def test_get_queue_depth_and_close(self, mock_redis):
        publisher = RedisPublisherWithCircuitBreaker()
        depth = publisher.get_queue_depth("test-queue")
        assert depth == 5

        with patch.object(publisher.pool, "disconnect") as mock_disconnect:
            publisher.close()
            mock_disconnect.assert_called_once()

    def test_message_envelope_retry_logic(self):
        envelope = MessageEnvelope(
            message_id="test-123",
            message_type="test",
            payload={"test": "data"},
            timestamp=datetime.utcnow(),
            retry_count=0,
            max_retries=3,
        )

        assert envelope.should_retry() is True
        envelope.increment_retry()
        assert envelope.retry_count == 1
        envelope.retry_count = 3
        assert envelope.should_retry() is False

    def test_model_ready_message_validation(self):
        message = ModelReadyToDeployMessage(
            model_id="model-123",
            token_symbol="test-token",
            metric_name="accuracy",
            baseline_value=0.8,
            current_value=0.85,
            model_name="test_model",
            model_version="1",
            mlflow_run_id="run123",
        )

        assert message.validate() is True
        assert message.improvement_percentage == pytest.approx(6.25)

        with pytest.raises(ValueError):
            ModelReadyToDeployMessage(
                model_id="model-123",
                token_symbol="",
                metric_name="accuracy",
                baseline_value=0.8,
                current_value=0.85,
                model_name="test_model",
                model_version="1",
                mlflow_run_id="run123",
            )
