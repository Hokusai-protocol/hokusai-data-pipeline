"""Webhook-based message publisher implementation."""

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from uuid import UUID

import httpx

try:
    from ..schemas import ModelReadyToDeployMessage
    from .base import AbstractPublisher, PublisherException
except ImportError:
    # Fallback for when running tests
    from src.events.schemas import ModelReadyToDeployMessage
    from src.events.publishers.base import AbstractPublisher, PublisherException

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Simple circuit breaker implementation for webhook reliability."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        """Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of consecutive failures before opening circuit
            recovery_timeout: Time in seconds to wait before trying half-open state
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self._state = "closed"  # closed, open, half_open
    
    @property
    def state(self) -> str:
        """Get current circuit breaker state."""
        if self._state == "open" and self._should_attempt_reset():
            self._state = "half_open"
        return self._state
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        return (datetime.utcnow() - self.last_failure_time).total_seconds() > self.recovery_timeout
    
    def record_success(self):
        """Record successful operation."""
        self.failure_count = 0
        self._state = "closed"
        self.last_failure_time = None
    
    def record_failure(self):
        """Record failed operation."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.failure_count >= self.failure_threshold:
            self._state = "open"
    
    def can_execute(self) -> bool:
        """Check if operation can be executed."""
        return self.state != "open"


class WebhookPublisher(AbstractPublisher):
    """Publisher that sends HTTP webhooks for model registration notifications."""
    
    def __init__(
        self,
        webhook_url: str,
        secret_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize WebhookPublisher.
        
        Args:
            webhook_url: URL to send webhooks to
            secret_key: Secret key for HMAC signature generation
            config: Additional configuration options
            
        Raises:
            ValueError: If webhook_url is invalid
        """
        # Validate webhook URL
        parsed_url = urlparse(webhook_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError(f"Invalid webhook URL: {webhook_url}")
        
        self.webhook_url = webhook_url
        self.secret_key = secret_key
        self._closed = False
        
        # Parse configuration
        config = config or {}
        self.timeout = config.get("timeout", 30.0)
        self.retry_delays = config.get("retry_delays", [2, 4, 8, 16, 32])
        
        # Initialize circuit breaker
        cb_config = config.get("circuit_breaker", {})
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=cb_config.get("failure_threshold", 5),
            recovery_timeout=cb_config.get("recovery_timeout", 60)
        )
        
        # Initialize HTTP client with connection pooling
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)
        self._client = httpx.AsyncClient(
            limits=limits,
            timeout=httpx.Timeout(self.timeout),
            headers={
                "User-Agent": "Hokusai-WebhookPublisher/1.0",
                "Content-Type": "application/json"
            }
        )
        
        logger.info(f"WebhookPublisher initialized for {webhook_url}")
    
    def publish(self, message: Dict[str, Any], queue_name: Optional[str] = None) -> bool:
        """Publish message via webhook.
        
        Args:
            message: Message to publish (ModelReadyToDeployMessage dict)
            queue_name: Queue name (ignored for webhooks, kept for interface compatibility)
            
        Returns:
            True if successful, False otherwise
        """
        if self._closed:
            logger.warning("Cannot publish: WebhookPublisher is closed")
            return False
        
        try:
            # Validate and convert message
            model_message = ModelReadyToDeployMessage.from_dict(message)
            if not model_message.validate():
                logger.error("Invalid message format for webhook publishing")
                return False
            
            # Create webhook payload
            webhook_payload = self._create_webhook_payload(model_message)
            
            # Send webhook with circuit breaker protection
            return asyncio.run(self._send_with_circuit_breaker(webhook_payload))
            
        except Exception as e:
            logger.error(f"Failed to publish webhook: {str(e)}")
            return False
    
    def publish_model_ready(
        self,
        model_id: str,
        token_symbol: str,
        metric_name: str,
        baseline_value: float,
        current_value: float,
        model_name: str,
        model_version: str,
        mlflow_run_id: str,
        **kwargs
    ) -> bool:
        """Convenience method to publish model_ready_to_deploy message.
        
        Args:
            model_id: Unique model identifier
            token_symbol: Token symbol
            metric_name: Performance metric name
            baseline_value: Baseline performance value
            current_value: Current model's performance value
            model_name: Registered model name
            model_version: Model version
            mlflow_run_id: MLflow run ID
            **kwargs: Additional optional fields
            
        Returns:
            True if successful
            
        Raises:
            PublisherException: If message validation fails
        """
        try:
            # Create typed message
            message = ModelReadyToDeployMessage(
                model_id=model_id,
                token_symbol=token_symbol,
                metric_name=metric_name,
                baseline_value=baseline_value,
                current_value=current_value,
                model_name=model_name,
                model_version=model_version,
                mlflow_run_id=mlflow_run_id,
                **kwargs
            )
            
            # Validate message
            if not message.validate():
                raise PublisherException("Invalid message format")
            
            return self.publish(message.to_dict())
            
        except Exception as e:
            if isinstance(e, PublisherException):
                raise
            raise PublisherException(f"Failed to publish model ready message: {str(e)}")
    
    def _create_webhook_payload(self, message: ModelReadyToDeployMessage) -> Dict[str, Any]:
        """Create webhook payload from ModelReadyToDeployMessage.
        
        Args:
            message: The message to convert
            
        Returns:
            Dictionary containing webhook payload
        """
        # Generate deterministic idempotency key based on message content
        content_for_key = f"{message.model_id}:{message.token_symbol}:{message.mlflow_run_id}:{message.model_version}"
        idempotency_key = str(uuid.uuid5(uuid.NAMESPACE_DNS, content_for_key))
        
        # Build payload
        payload = {
            "model_id": message.model_id,
            "idempotency_key": idempotency_key,
            "registered_version": message.model_version,
            "timestamp": message.timestamp.isoformat(),
            "token_symbol": message.token_symbol,
            "baseline_metrics": {
                message.metric_name: message.baseline_value
            },
            "metadata": {
                "model_name": message.model_name,
                "mlflow_run_id": message.mlflow_run_id,
                "improvement_percentage": message.improvement_percentage,
                "contributor_address": message.contributor_address,
                "experiment_name": message.experiment_name,
                "tags": message.tags
            }
        }
        
        return payload
    
    def _validate_payload(self, payload: Dict[str, Any]) -> bool:
        """Validate webhook payload structure.
        
        Args:
            payload: Payload to validate
            
        Returns:
            True if valid
            
        Raises:
            ValueError: If payload is invalid
        """
        required_fields = [
            "model_id", "idempotency_key", "registered_version",
            "timestamp", "token_symbol", "baseline_metrics", "metadata"
        ]
        
        for field in required_fields:
            if field not in payload:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate timestamp format
        try:
            datetime.fromisoformat(payload["timestamp"])
        except ValueError:
            raise ValueError("Invalid timestamp format")
        
        # Validate UUID format for idempotency key
        try:
            UUID(payload["idempotency_key"])
        except ValueError:
            raise ValueError("Invalid idempotency key format")
        
        return True
    
    def _generate_signature(self, payload_bytes: bytes) -> Optional[str]:
        """Generate HMAC-SHA256 signature for webhook payload.
        
        Args:
            payload_bytes: Payload as bytes
            
        Returns:
            Signature string in format "sha256=<hex_digest>" or None if no secret key
        """
        if not self.secret_key:
            return None
        
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        
        return f"sha256={signature}"
    
    async def _send_with_circuit_breaker(self, payload: Dict[str, Any]) -> bool:
        """Send webhook with circuit breaker protection.
        
        Args:
            payload: Webhook payload
            
        Returns:
            True if successful
        """
        if not self.circuit_breaker.can_execute():
            logger.warning("Webhook blocked by circuit breaker (state: %s)", self.circuit_breaker.state)
            return False
        
        try:
            success = await self._publish_with_retries(payload)
            
            if success:
                self.circuit_breaker.record_success()
            else:
                self.circuit_breaker.record_failure()
            
            return success
            
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error(f"Webhook failed with circuit breaker: {str(e)}")
            return False
    
    async def _publish_with_retries(self, payload: Dict[str, Any]) -> bool:
        """Publish webhook with retry logic and exponential backoff.
        
        Args:
            payload: Webhook payload
            
        Returns:
            True if successful
        """
        # Initial attempt
        success = await self._send_webhook(payload)
        if success:
            return True
        
        # Retry with exponential backoff
        for delay in self.retry_delays:
            logger.info(f"Retrying webhook in {delay} seconds...")
            await asyncio.sleep(delay)
            
            success = await self._send_webhook(payload)
            if success:
                return True
        
        logger.error(f"Webhook failed after {len(self.retry_delays) + 1} attempts")
        return False
    
    async def _send_webhook(self, payload: Dict[str, Any]) -> bool:
        """Send single webhook HTTP request.
        
        Args:
            payload: Webhook payload
            
        Returns:
            True if successful (2xx response)
        """
        try:
            # Validate payload
            self._validate_payload(payload)
            
            # Serialize payload
            payload_json = json.dumps(payload, separators=(',', ':'))
            payload_bytes = payload_json.encode('utf-8')
            
            # Generate signature
            signature = self._generate_signature(payload_bytes)
            
            # Build headers
            headers = {
                "X-Hokusai-Idempotency-Key": payload["idempotency_key"]
            }
            
            if signature:
                headers["X-Hokusai-Signature"] = signature
            
            # Send webhook
            response = await self._client.post(
                self.webhook_url,
                data=payload_bytes,
                headers=headers,
                timeout=self.timeout
            )
            
            # Check response status
            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"Webhook delivered successfully (status: {response.status_code})")
                return True
            else:
                logger.error(f"Webhook failed with status {response.status_code}: {response.text}")
                return False
                
        except httpx.TimeoutException as e:
            logger.error(f"Webhook timeout: {str(e)}")
            return False
        except httpx.RequestError as e:
            logger.error(f"Webhook request error: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected webhook error: {str(e)}")
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """Check webhook endpoint health.
        
        Returns:
            Dict with health status information
        """
        if self._closed:
            return {
                "status": "unhealthy",
                "error": "Publisher is closed",
                "webhook_url": self.webhook_url,
                "circuit_breaker_state": self.circuit_breaker.state
            }
        
        try:
            # Make health check request (sync version for interface compatibility)
            async def _health_check():
                start_time = time.time()
                try:
                    # Try to make a GET request to the webhook URL or health endpoint
                    # Most webhook endpoints don't support GET, so we'll try both
                    health_url = self.webhook_url.replace('/webhook', '/health')
                    
                    try:
                        response = await self._client.get(health_url, timeout=5.0)
                    except:
                        # If health endpoint doesn't exist, try webhook URL
                        response = await self._client.get(self.webhook_url, timeout=5.0)
                    
                    response_time = (time.time() - start_time) * 1000  # Convert to ms
                    
                    return {
                        "status": "healthy",
                        "webhook_url": self.webhook_url,
                        "response_time_ms": round(response_time, 2),
                        "circuit_breaker_state": self.circuit_breaker.state,
                        "last_status_code": response.status_code
                    }
                    
                except Exception as e:
                    return {
                        "status": "unhealthy",
                        "webhook_url": self.webhook_url,
                        "error": str(e),
                        "circuit_breaker_state": self.circuit_breaker.state
                    }
            
            # Run async health check
            return asyncio.run(_health_check())
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "webhook_url": self.webhook_url,
                "error": f"Health check failed: {str(e)}",
                "circuit_breaker_state": self.circuit_breaker.state
            }
    
    def get_queue_depth(self, queue_name: str) -> Optional[int]:
        """Get number of messages in queue.
        
        Note: Not supported for webhook publishing as there's no queue.
        
        Args:
            queue_name: Queue name (ignored)
            
        Returns:
            None (not supported for webhooks)
        """
        return None
    
    def close(self) -> None:
        """Close HTTP client and clean up resources."""
        if self._closed:
            return
        
        try:
            asyncio.run(self._client.aclose())
            self._closed = True
            logger.info("WebhookPublisher closed successfully")
        except Exception as e:
            logger.error(f"Error closing WebhookPublisher: {str(e)}")
            self._closed = True