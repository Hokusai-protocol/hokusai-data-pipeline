"""Unit tests for WebhookPublisher."""

import asyncio
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import httpx
import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from events.publishers.base import PublisherException
from events.publishers.webhook_publisher import WebhookPublisher
from events.schemas import ModelReadyToDeployMessage


class TestWebhookPublisher:
    """Test WebhookPublisher functionality."""

    @pytest.fixture
    def webhook_url(self):
        """Test webhook URL."""
        return "https://api.example.com/webhooks/model-ready"

    @pytest.fixture
    def secret_key(self):
        """Test secret key for HMAC signatures."""
        return "test-webhook-secret-key"

    @pytest.fixture
    def webhook_config(self):
        """Test webhook configuration."""
        return {
            "timeout": 30.0,
            "retry_delays": [0.01, 0.01, 0.01],
            "circuit_breaker": {
                "failure_threshold": 5,
                "recovery_timeout": 60,
                "expected_exception": httpx.RequestError,
            },
        }

    @pytest.fixture
    def publisher(self, webhook_url, secret_key, webhook_config):
        """Create WebhookPublisher instance."""
        return WebhookPublisher(
            webhook_url=webhook_url, secret_key=secret_key, config=webhook_config
        )

    @pytest.fixture
    def sample_message(self):
        """Sample ModelReadyToDeployMessage."""
        return ModelReadyToDeployMessage(
            model_id="test-model-123",
            token_symbol="test-token",
            metric_name="accuracy",
            baseline_value=0.85,
            current_value=0.92,
            model_name="test_model",
            model_version="v1.0.0",
            mlflow_run_id="run-123",
            improvement_percentage=8.2,
            contributor_address="0x1234567890123456789012345678901234567890",
            experiment_name="test_experiment",
            tags={"env": "test", "team": "ml"},
        )

    @pytest.fixture
    def sample_payload(self, sample_message):
        """Sample webhook payload."""
        return {
            "model_id": sample_message.model_id,
            "idempotency_key": str(UUID("12345678-1234-5678-1234-567812345678")),
            "registered_version": sample_message.model_version,
            "timestamp": sample_message.timestamp.isoformat(),
            "token_symbol": sample_message.token_symbol,
            "baseline_metrics": {sample_message.metric_name: sample_message.baseline_value},
            "metadata": {
                "model_name": sample_message.model_name,
                "mlflow_run_id": sample_message.mlflow_run_id,
                "improvement_percentage": sample_message.improvement_percentage,
                "contributor_address": sample_message.contributor_address,
                "experiment_name": sample_message.experiment_name,
                "tags": sample_message.tags,
            },
        }

    def test_init_with_defaults(self, webhook_url):
        """Test WebhookPublisher initialization with defaults."""
        publisher = WebhookPublisher(webhook_url=webhook_url)

        assert publisher.webhook_url == webhook_url
        assert publisher.secret_key is None
        assert publisher.timeout == 30.0
        assert publisher.retry_delays == [2, 4, 8, 16, 32]
        assert publisher.circuit_breaker is not None
        assert publisher._client is not None
        assert not publisher._closed

    def test_init_with_custom_config(self, webhook_url, secret_key, webhook_config):
        """Test WebhookPublisher initialization with custom config."""
        publisher = WebhookPublisher(
            webhook_url=webhook_url, secret_key=secret_key, config=webhook_config
        )

        assert publisher.webhook_url == webhook_url
        assert publisher.secret_key == secret_key
        assert publisher.timeout == webhook_config["timeout"]
        assert publisher.retry_delays == webhook_config["retry_delays"]

    def test_init_invalid_url(self):
        """Test initialization with invalid URL."""
        with pytest.raises(ValueError, match="Invalid webhook URL"):
            WebhookPublisher(webhook_url="not-a-url")

    def test_generate_signature(self, publisher, secret_key):
        """Test HMAC signature generation."""
        payload = {"test": "data"}
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        signature = publisher._generate_signature(payload_bytes)

        # Verify signature format
        assert signature.startswith("sha256=")

        # Verify signature is correct
        expected_sig = hmac.new(
            secret_key.encode("utf-8"), payload_bytes, hashlib.sha256
        ).hexdigest()
        assert signature == f"sha256={expected_sig}"

    def test_generate_signature_no_secret(self, webhook_url):
        """Test signature generation without secret key."""
        publisher = WebhookPublisher(webhook_url=webhook_url)
        payload = {"test": "data"}
        payload_bytes = json.dumps(payload).encode("utf-8")

        signature = publisher._generate_signature(payload_bytes)
        assert signature is None

    def test_validate_payload_valid(self, publisher, sample_payload):
        """Test payload validation with valid data."""
        assert publisher._validate_payload(sample_payload) is True

    def test_validate_payload_missing_fields(self, publisher):
        """Test payload validation with missing required fields."""
        invalid_payload = {"model_id": "test"}

        with pytest.raises(ValueError, match="Missing required field"):
            publisher._validate_payload(invalid_payload)

    def test_validate_payload_invalid_types(self, publisher, sample_payload):
        """Test payload validation with invalid field types."""
        sample_payload["timestamp"] = "not-a-valid-timestamp"

        with pytest.raises(ValueError, match="Invalid timestamp format"):
            publisher._validate_payload(sample_payload)

    @pytest.mark.asyncio
    async def test_publish_success(self, publisher, sample_payload):
        """Test successful webhook publishing."""
        with patch.object(publisher._client, "post", new_callable=AsyncMock) as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_response.json.return_value = {"status": "received"}
            mock_post.return_value = mock_response

            result = await publisher._send_webhook(sample_payload)

            assert result is True
            mock_post.assert_called_once()

            # Verify call parameters
            call_args = mock_post.call_args
            assert call_args[0][0] == publisher.webhook_url  # First positional arg is URL
            assert call_args[1]["timeout"] == publisher.timeout
            assert "X-Hokusai-Signature" in call_args[1]["headers"]
            assert "X-Hokusai-Idempotency-Key" in call_args[1]["headers"]

    @pytest.mark.asyncio
    async def test_publish_with_signature(self, publisher, sample_payload):
        """Test webhook publishing includes correct signature."""
        with patch.object(publisher._client, "post", new_callable=AsyncMock) as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            await publisher._send_webhook(sample_payload)

            call_args = mock_post.call_args
            headers = call_args[1]["headers"]

            # Verify signature header exists and format
            assert "X-Hokusai-Signature" in headers
            signature = headers["X-Hokusai-Signature"]
            assert signature.startswith("sha256=")

            # Verify idempotency key
            assert "X-Hokusai-Idempotency-Key" in headers
            idem_key = headers["X-Hokusai-Idempotency-Key"]
            assert idem_key == sample_payload["idempotency_key"]

    @pytest.mark.asyncio
    async def test_publish_http_error(self, publisher, sample_payload):
        """Test webhook publishing with HTTP error response."""
        with patch.object(publisher._client, "post", new_callable=AsyncMock) as mock_post:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.return_value = mock_response

            result = await publisher._send_webhook(sample_payload)

            assert result is False

    @pytest.mark.asyncio
    async def test_publish_connection_error(self, publisher, sample_payload):
        """Test webhook publishing with connection error."""
        with patch.object(publisher._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection failed")

            result = await publisher._send_webhook(sample_payload)

            assert result is False

    @pytest.mark.asyncio
    async def test_publish_timeout(self, publisher, sample_payload):
        """Test webhook publishing with timeout."""
        with patch.object(publisher._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timeout")

            result = await publisher._send_webhook(sample_payload)

            assert result is False

    @pytest.mark.asyncio
    async def test_publish_with_retries_success(self, publisher, sample_payload):
        """Test webhook publishing with retry success."""
        with patch.object(publisher, "_send_webhook", new_callable=AsyncMock) as mock_send:
            # First two calls fail, third succeeds
            mock_send.side_effect = [False, False, True]

            result = await publisher._publish_with_retries(sample_payload)

            assert result is True
            assert mock_send.call_count == 3

    @pytest.mark.asyncio
    async def test_publish_with_retries_max_attempts(self, publisher, sample_payload):
        """Test webhook publishing exhausts all retry attempts."""
        with patch.object(publisher, "_send_webhook", new_callable=AsyncMock) as mock_send:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                mock_send.return_value = False  # All attempts fail

                result = await publisher._publish_with_retries(sample_payload)

            assert result is False
            assert mock_send.call_count == len(publisher.retry_delays) + 1  # Initial + retries

    @pytest.mark.asyncio
    async def test_publish_with_retries_delay(self, publisher, sample_payload):
        """Test webhook publishing retry delays."""
        with patch.object(publisher, "_send_webhook", new_callable=AsyncMock) as mock_send:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_send.return_value = False  # All attempts fail

                await publisher._publish_with_retries(sample_payload)

                # Verify sleep was called with correct delays
                expected_delays = publisher.retry_delays
                sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
                assert sleep_calls == expected_delays

    def test_circuit_breaker_closed_state(self, publisher):
        """Test circuit breaker in closed state."""
        # Circuit breaker should be closed initially
        assert publisher.circuit_breaker.state == "closed"

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_failures(self, publisher, sample_payload):
        """Test circuit breaker opens after threshold failures."""
        with patch.object(
            publisher, "_publish_with_retries", new_callable=AsyncMock
        ) as mock_publish:
            mock_publish.return_value = False  # All calls fail

            # Make enough failing calls to open circuit breaker
            failure_threshold = publisher.circuit_breaker.failure_threshold
            for _ in range(failure_threshold):
                await publisher._send_with_circuit_breaker(sample_payload)

            # Circuit breaker should now be open
            assert publisher.circuit_breaker.state == "open"

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_when_open(self, publisher, sample_payload):
        """Test circuit breaker blocks calls when open."""
        # Force circuit breaker to open state
        publisher.circuit_breaker._state = "open"
        publisher.circuit_breaker.last_failure_time = datetime.utcnow()

        with patch.object(
            publisher, "_publish_with_retries", new_callable=AsyncMock
        ) as mock_publish:
            result = await publisher._send_with_circuit_breaker(sample_payload)

            # Should return False without calling publish
            assert result is False
            mock_publish.assert_not_called()

    def test_publish_sync_success(self, publisher, sample_message):
        """Test synchronous publish method."""
        with patch.object(
            publisher, "_send_with_circuit_breaker", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = True

            result = publisher.publish(sample_message.to_dict(), "test-queue")

            assert result is True
            mock_send.assert_called_once()

    def test_publish_sync_invalid_message(self, publisher):
        """Test synchronous publish with invalid message."""
        invalid_message = {"invalid": "data"}

        result = publisher.publish(invalid_message, "test-queue")

        assert result is False

    def test_publish_model_ready_success(self, publisher):
        """Test publish_model_ready convenience method."""
        with patch.object(publisher, "publish", return_value=True) as mock_publish:
            result = publisher.publish_model_ready(
                model_id="test-model",
                token_symbol="TEST",
                metric_name="accuracy",
                baseline_value=0.8,
                current_value=0.9,
                model_name="test_model",
                model_version="v1.0",
                mlflow_run_id="run-123",
            )

            assert result is True
            mock_publish.assert_called_once()

    def test_publish_model_ready_validation_error(self, publisher):
        """Test publish_model_ready with validation error."""
        with pytest.raises(PublisherException):
            publisher.publish_model_ready(
                model_id="",  # Invalid empty model_id
                token_symbol="TEST",
                metric_name="accuracy",
                baseline_value=0.8,
                current_value=0.9,
                model_name="test_model",
                model_version="v1.0",
                mlflow_run_id="run-123",
            )

    def test_health_check_healthy(self, publisher):
        """Test health check when webhook is healthy."""
        with patch.object(publisher._client, "get", new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.elapsed = Mock()
            mock_response.elapsed.total_seconds.return_value = 0.1
            mock_get.return_value = mock_response

            health = publisher.health_check()

            assert health["status"] == "healthy"
            assert health["webhook_url"] == publisher.webhook_url
            assert "response_time_ms" in health
            assert health["circuit_breaker_state"] == "closed"

    def test_health_check_unhealthy(self, publisher):
        """Test health check when webhook is unhealthy."""
        with patch.object(publisher._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection failed")

            health = publisher.health_check()

            assert health["status"] == "unhealthy"
            assert "error" in health

    def test_get_queue_depth_not_supported(self, publisher):
        """Test get_queue_depth returns None (not supported for webhooks)."""
        depth = publisher.get_queue_depth("test-queue")
        assert depth is None

    def test_close_publisher(self, publisher):
        """Test closing the publisher."""
        assert not publisher._closed

        publisher.close()

        assert publisher._closed

    def test_context_manager(self, webhook_url):
        """Test publisher as context manager."""
        with WebhookPublisher(webhook_url=webhook_url) as publisher:
            assert not publisher._closed

        assert publisher._closed

    @pytest.mark.asyncio
    async def test_concurrent_publishing(self, publisher, sample_payload):
        """Test concurrent webhook publishing."""
        with patch.object(publisher._client, "post", new_callable=AsyncMock) as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            # Send multiple concurrent webhooks
            tasks = [publisher._send_webhook(sample_payload) for _ in range(5)]
            results = await asyncio.gather(*tasks)

            # All should succeed
            assert all(results)
            assert mock_post.call_count == 5

    def test_idempotency_key_generation(self, publisher, sample_message):
        """Test idempotency key is generated consistently."""
        payload1 = publisher._create_webhook_payload(sample_message)
        payload2 = publisher._create_webhook_payload(sample_message)

        # Same message should generate same idempotency key
        assert payload1["idempotency_key"] == payload2["idempotency_key"]

    def test_different_messages_different_keys(self, publisher):
        """Test different messages generate different idempotency keys."""
        message1 = ModelReadyToDeployMessage(
            model_id="model-1",
            token_symbol="TOKEN1",
            metric_name="accuracy",
            baseline_value=0.8,
            current_value=0.9,
            model_name="model1",
            model_version="v1.0",
            mlflow_run_id="run-1",
        )

        message2 = ModelReadyToDeployMessage(
            model_id="model-2",
            token_symbol="TOKEN2",
            metric_name="accuracy",
            baseline_value=0.8,
            current_value=0.9,
            model_name="model2",
            model_version="v1.0",
            mlflow_run_id="run-2",
        )

        payload1 = publisher._create_webhook_payload(message1)
        payload2 = publisher._create_webhook_payload(message2)

        assert payload1["idempotency_key"] != payload2["idempotency_key"]

    def test_payload_serialization(self, publisher, sample_message):
        """Test webhook payload is properly serialized."""
        payload = publisher._create_webhook_payload(sample_message)

        # Verify all required fields are present
        required_fields = [
            "model_id",
            "idempotency_key",
            "registered_version",
            "timestamp",
            "token_symbol",
            "baseline_metrics",
            "metadata",
        ]
        for field in required_fields:
            assert field in payload

        # Verify types
        assert isinstance(payload["model_id"], str)
        assert isinstance(payload["idempotency_key"], str)
        assert isinstance(payload["registered_version"], str)
        assert isinstance(payload["timestamp"], str)
        assert isinstance(payload["token_symbol"], str)
        assert isinstance(payload["baseline_metrics"], dict)
        assert isinstance(payload["metadata"], dict)

        # Verify UUID format for idempotency key
        UUID(payload["idempotency_key"])  # Should not raise exception

    def test_error_logging_on_failure(self, publisher, sample_payload, caplog):
        """Test error logging on webhook failure."""
        with patch.object(publisher._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection failed")

            # Run the async function in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(publisher._send_webhook(sample_payload))
                assert result is False
            finally:
                loop.close()

            # Check that error was logged
            assert "Connection failed" in caplog.text
