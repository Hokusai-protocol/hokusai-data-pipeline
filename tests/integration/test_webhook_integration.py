"""Integration tests for WebhookPublisher."""

import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime
from unittest.mock import patch

import pytest
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn
import threading

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from events.publishers.webhook_publisher import WebhookPublisher
from events.schemas import ModelReadyToDeployMessage


class TestWebhookServer:
    """Test webhook server for integration testing."""
    
    def __init__(self, port=8999, secret_key=None):
        self.port = port
        self.secret_key = secret_key
        self.app = FastAPI()
        self.server = None
        self.server_thread = None
        self.received_webhooks = []
        self.response_config = {
            "status_code": 200,
            "response_data": {"status": "received"},
            "delay": 0,
            "fail_count": 0,
            "current_fails": 0
        }
        
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup FastAPI routes."""
        
        @self.app.post("/webhook")
        async def receive_webhook(request: Request):
            # Parse request first (always needed)
            body = await request.body()
            headers = dict(request.headers)
            
            # Always store received webhook data for test verification
            webhook_data = {
                "body": json.loads(body.decode()),
                "headers": headers,
                "timestamp": datetime.utcnow().isoformat()
            }
            self.received_webhooks.append(webhook_data)
            
            # Add delay if configured
            if self.response_config["delay"] > 0:
                await asyncio.sleep(self.response_config["delay"])
            
            # Fail if configured
            if self.response_config["current_fails"] < self.response_config["fail_count"]:
                self.response_config["current_fails"] += 1
                raise HTTPException(status_code=500, detail="Simulated failure")
            
            # Verify signature if secret key is configured
            if self.secret_key and "x-hokusai-signature" in headers:
                signature = headers["x-hokusai-signature"]
                expected_sig = hmac.new(
                    self.secret_key.encode('utf-8'),
                    body,
                    hashlib.sha256
                ).hexdigest()
                
                if signature != f"sha256={expected_sig}":
                    raise HTTPException(status_code=401, detail="Invalid signature")
            
            return JSONResponse(
                content=self.response_config["response_data"],
                status_code=self.response_config["status_code"]
            )
        
        @self.app.get("/health")
        async def health_check():
            return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
    
    def start(self):
        """Start the test webhook server."""
        def run_server():
            config = uvicorn.Config(
                self.app,
                host="127.0.0.1",
                port=self.port,
                log_level="error"  # Suppress logs during testing
            )
            self.server = uvicorn.Server(config)
            asyncio.run(self.server.serve())
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        
        # Wait for server to start
        time.sleep(0.5)
    
    def stop(self):
        """Stop the test webhook server."""
        if self.server:
            self.server.should_exit = True
        if self.server_thread:
            self.server_thread.join(timeout=1.0)
    
    def configure_response(self, status_code=200, response_data=None, delay=0, fail_count=0):
        """Configure server response behavior."""
        self.response_config.update({
            "status_code": status_code,
            "response_data": response_data or {"status": "received"},
            "delay": delay,
            "fail_count": fail_count,
            "current_fails": 0
        })
    
    def clear_webhooks(self):
        """Clear received webhooks."""
        self.received_webhooks.clear()


class TestWebhookIntegration:
    """Integration tests for WebhookPublisher."""
    
    @pytest.fixture(scope="class")
    def webhook_server(self):
        """Start test webhook server."""
        server = TestWebhookServer(port=8999, secret_key="test-secret")
        server.start()
        yield server
        server.stop()
    
    @pytest.fixture
    def webhook_url(self):
        """Webhook URL for test server."""
        return "http://127.0.0.1:8999/webhook"
    
    @pytest.fixture
    def publisher(self, webhook_url):
        """Create WebhookPublisher for integration testing."""
        config = {
            "timeout": 10.0,
            "retry_delays": [0.1, 0.2, 0.3],  # Faster retries for testing
            "circuit_breaker": {
                "failure_threshold": 3,
                "recovery_timeout": 2,
                "expected_exception": httpx.RequestError
            }
        }
        return WebhookPublisher(
            webhook_url=webhook_url,
            secret_key="test-secret",
            config=config
        )
    
    @pytest.fixture
    def sample_message(self):
        """Sample ModelReadyToDeployMessage."""
        return ModelReadyToDeployMessage(
            model_id="integration-test-model-123",
            token_symbol="INT-TOKEN",
            metric_name="accuracy",
            baseline_value=0.85,
            current_value=0.92,
            model_name="integration_test_model",
            model_version="v1.0.0",
            mlflow_run_id="integration-run-123",
            improvement_percentage=8.2,
            contributor_address="0x1234567890123456789012345678901234567890",
            experiment_name="integration_test_experiment",
            tags={"env": "integration", "team": "ml-test"}
        )

    def test_successful_webhook_delivery(self, webhook_server, publisher, sample_message):
        """Test successful webhook delivery end-to-end."""
        webhook_server.clear_webhooks()
        webhook_server.configure_response(status_code=200)
        
        # Publish message
        result = publisher.publish(sample_message.to_dict(), "test-queue")
        
        assert result is True
        
        # Verify webhook was received
        assert len(webhook_server.received_webhooks) == 1
        
        received = webhook_server.received_webhooks[0]
        body = received["body"]
        headers = received["headers"]
        
        # Verify payload structure
        assert body["model_id"] == sample_message.model_id
        assert body["token_symbol"] == sample_message.token_symbol
        assert "idempotency_key" in body
        assert "timestamp" in body
        assert "baseline_metrics" in body
        assert "metadata" in body
        
        # Verify headers
        assert "x-hokusai-signature" in headers
        assert "x-hokusai-idempotency-key" in headers
        assert headers["content-type"] == "application/json"

    def test_webhook_signature_verification(self, webhook_server, publisher, sample_message):
        """Test HMAC signature verification."""
        webhook_server.clear_webhooks()
        webhook_server.configure_response(status_code=200)
        
        result = publisher.publish(sample_message.to_dict(), "test-queue")
        
        assert result is True
        assert len(webhook_server.received_webhooks) == 1
        
        # Server validates signature internally - if we get here, signature was valid

    def test_webhook_with_retry_success(self, webhook_server, publisher, sample_message):
        """Test webhook delivery with retry success."""
        webhook_server.clear_webhooks()
        # First 2 calls fail, then succeed
        webhook_server.configure_response(status_code=200, fail_count=2)
        
        result = publisher.publish(sample_message.to_dict(), "test-queue")
        
        assert result is True
        # Should have received 3 webhooks total (2 fails + 1 success)
        assert len(webhook_server.received_webhooks) == 3

    def test_webhook_retry_exhaustion(self, webhook_server, publisher, sample_message):
        """Test webhook delivery fails after exhausting retries."""
        webhook_server.clear_webhooks()
        # Fail more times than we have retries
        webhook_server.configure_response(status_code=500, fail_count=10)
        
        result = publisher.publish(sample_message.to_dict(), "test-queue")
        
        assert result is False
        # Should have received initial + retry attempts
        expected_attempts = 1 + len(publisher.retry_delays)
        assert len(webhook_server.received_webhooks) == expected_attempts

    def test_webhook_timeout_handling(self, webhook_server, publisher, sample_message):
        """Test webhook timeout handling."""
        webhook_server.clear_webhooks()
        # Configure server to delay longer than client timeout
        webhook_server.configure_response(delay=11.0)  # Longer than 10s timeout
        
        result = publisher.publish(sample_message.to_dict(), "test-queue")
        
        assert result is False
        # May have received webhook but client timed out

    def test_circuit_breaker_integration(self, webhook_server, publisher, sample_message):
        """Test circuit breaker integration."""
        webhook_server.clear_webhooks()
        webhook_server.configure_response(status_code=500)
        
        # Make enough failing requests to open circuit breaker
        for i in range(publisher.circuit_breaker.failure_threshold):
            result = publisher.publish(sample_message.to_dict(), f"test-queue-{i}")
            assert result is False
        
        # Circuit breaker should now be open
        assert publisher.circuit_breaker.state == "open"
        
        # Next request should be blocked by circuit breaker
        initial_webhook_count = len(webhook_server.received_webhooks)
        result = publisher.publish(sample_message.to_dict(), "blocked-queue")
        assert result is False
        
        # Should not have sent additional webhook
        assert len(webhook_server.received_webhooks) == initial_webhook_count

    @pytest.mark.asyncio
    async def test_concurrent_webhook_publishing(self, webhook_server, publisher, sample_message):
        """Test concurrent webhook publishing."""
        webhook_server.clear_webhooks()
        webhook_server.configure_response(status_code=200)
        
        # Create multiple messages with different model IDs
        messages = []
        for i in range(5):
            msg_dict = sample_message.to_dict()
            msg_dict["model_id"] = f"concurrent-model-{i}"
            messages.append(msg_dict)
        
        # Publish concurrently (using thread pool since publish is sync)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(publisher.publish, msg, f"queue-{i}")
                for i, msg in enumerate(messages)
            ]
            results = [future.result() for future in futures]
        
        # All should succeed
        assert all(results)
        assert len(webhook_server.received_webhooks) == 5
        
        # Verify all different model IDs were received
        received_ids = {webhook["body"]["model_id"] for webhook in webhook_server.received_webhooks}
        expected_ids = {f"concurrent-model-{i}" for i in range(5)}
        assert received_ids == expected_ids

    def test_idempotency_key_uniqueness(self, webhook_server, publisher, sample_message):
        """Test that idempotency keys are unique for different messages."""
        webhook_server.clear_webhooks()
        webhook_server.configure_response(status_code=200)
        
        # Publish same message twice  
        result1 = publisher.publish(sample_message.to_dict(), "test-queue-1")
        result2 = publisher.publish(sample_message.to_dict(), "test-queue-2")
        
        assert result1 is True
        assert result2 is True
        
        # Check we got at least 2 webhooks (may be more due to retries/health checks)
        import time
        time.sleep(0.1)
        assert len(webhook_server.received_webhooks) >= 2
        
        # Both should have same idempotency key (same message)
        # Get the first two webhooks with the right model_id
        same_msg_webhooks = [w for w in webhook_server.received_webhooks 
                            if w["body"]["model_id"] == sample_message.model_id][:2]
        
        key1 = same_msg_webhooks[0]["headers"]["x-hokusai-idempotency-key"]
        key2 = same_msg_webhooks[1]["headers"]["x-hokusai-idempotency-key"]
        assert key1 == key2
        
        # Now publish different message
        webhook_server.clear_webhooks()
        different_message = sample_message.to_dict()
        different_message["model_id"] = "different-model"
        
        result3 = publisher.publish(different_message, "test-queue-3")
        assert result3 is True
        
        # Should have different idempotency key
        time.sleep(0.1)
        assert len(webhook_server.received_webhooks) >= 1
        key3 = webhook_server.received_webhooks[0]["headers"]["x-hokusai-idempotency-key"]
        assert key3 != key1

    def test_health_check_integration(self, webhook_server, publisher):
        """Test health check against real server."""
        webhook_server.configure_response(status_code=200)
        
        health = publisher.health_check()
        
        assert health["status"] == "healthy"
        assert health["webhook_url"] == publisher.webhook_url
        assert "response_time_ms" in health
        assert health["circuit_breaker_state"] in ["closed", "half_open", "open"]

    def test_health_check_server_down(self, publisher):
        """Test health check when server is unreachable."""
        # Create publisher with unreachable URL
        down_publisher = WebhookPublisher(
            webhook_url="http://127.0.0.1:9999/webhook",  # Non-existent server
            secret_key="test-secret"
        )
        
        health = down_publisher.health_check()
        
        assert health["status"] == "unhealthy"
        assert "error" in health

    def test_publish_model_ready_integration(self, webhook_server, publisher):
        """Test publish_model_ready convenience method integration."""
        webhook_server.clear_webhooks()
        webhook_server.configure_response(status_code=200)
        
        result = publisher.publish_model_ready(
            model_id="convenience-test-model",
            token_symbol="CONV-TOKEN",
            metric_name="f1_score",
            baseline_value=0.75,
            current_value=0.83,
            model_name="convenience_test_model",
            model_version="v2.0.0",
            mlflow_run_id="convenience-run-456",
            improvement_percentage=10.7,
            contributor_address="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            experiment_name="convenience_experiment",
            tags={"method": "convenience", "test": "true"}
        )
        
        assert result is True
        assert len(webhook_server.received_webhooks) == 1
        
        received = webhook_server.received_webhooks[0]["body"]
        assert received["model_id"] == "convenience-test-model"
        assert received["token_symbol"] == "CONV-TOKEN"
        assert received["baseline_metrics"]["f1_score"] == 0.75
        assert received["metadata"]["improvement_percentage"] == 10.7

    def test_malformed_response_handling(self, webhook_server, publisher, sample_message):
        """Test handling of malformed server responses."""
        webhook_server.clear_webhooks()
        
        # Configure server to return malformed response
        webhook_server.configure_response(
            status_code=200,
            response_data="not-json-data"  # This will cause JSON decode error
        )
        
        # Should still succeed as long as status code is 200
        result = publisher.publish(sample_message.to_dict(), "test-queue")
        
        assert result is True
        assert len(webhook_server.received_webhooks) == 1

    def test_large_payload_handling(self, webhook_server, publisher):
        """Test handling of large webhook payloads."""
        webhook_server.clear_webhooks()
        webhook_server.configure_response(status_code=200)
        
        # Create message with large metadata
        large_tags = {f"tag_{i}": f"value_{i}" * 100 for i in range(100)}
        
        large_message = ModelReadyToDeployMessage(
            model_id="large-payload-test",
            token_symbol="LARGE-TOKEN",
            metric_name="accuracy",
            baseline_value=0.8,
            current_value=0.9,
            model_name="large_payload_model",
            model_version="v1.0.0",
            mlflow_run_id="large-run-123",
            tags=large_tags
        )
        
        result = publisher.publish(large_message.to_dict(), "large-queue")
        
        assert result is True
        assert len(webhook_server.received_webhooks) == 1
        
        # Verify large tags were transmitted
        received_tags = webhook_server.received_webhooks[0]["body"]["metadata"]["tags"]
        assert len(received_tags) == 100
        assert "tag_50" in received_tags