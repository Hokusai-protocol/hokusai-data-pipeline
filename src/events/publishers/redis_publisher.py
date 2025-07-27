"""Redis-based message publisher implementation."""

import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

import redis
from redis.exceptions import ConnectionError, RedisError

from ..schemas import MessageEnvelope, ModelReadyToDeployMessage
from .base import AbstractPublisher, PublisherException

logger = logging.getLogger(__name__)


class RedisPublisher(AbstractPublisher):
    """Publisher that uses Redis lists for reliable message queuing."""
    
    DEFAULT_QUEUE = "hokusai:model_ready_queue"
    PROCESSING_QUEUE_SUFFIX = ":processing"
    DLQ_SUFFIX = ":dlq"
    
    def __init__(
        self, 
        redis_url: str = "redis://localhost:6379/0",
        connection_pool_kwargs: Optional[Dict[str, Any]] = None,
        retry_config: Optional[Dict[str, Any]] = None
    ):
        """Initialize Redis publisher.
        
        Args:
            redis_url: Redis connection URL
            connection_pool_kwargs: Additional connection pool parameters
            retry_config: Retry configuration (max_retries, base_delay, max_delay)
        """
        self.redis_url = redis_url
        self.retry_config = retry_config or {
            "max_retries": 3,
            "base_delay": 1.0,  # seconds
            "max_delay": 30.0   # seconds
        }
        
        # Create connection pool for better performance
        pool_kwargs = connection_pool_kwargs or {}
        pool_kwargs.setdefault("max_connections", 50)
        pool_kwargs.setdefault("socket_keepalive", True)
        pool_kwargs.setdefault("socket_keepalive_options", {})
        
        try:
            self.pool = redis.ConnectionPool.from_url(redis_url, **pool_kwargs)
            self.client = redis.Redis(connection_pool=self.pool)
            # Test connection
            self.client.ping()
            logger.info(f"Connected to Redis at {redis_url}")
        except (ConnectionError, RedisError) as e:
            raise PublisherException(f"Failed to connect to Redis: {str(e)}")
    
    def publish(self, message: Dict[str, Any], queue_name: Optional[str] = None) -> bool:
        """Publish message to Redis queue with retry logic.
        
        Args:
            message: Message to publish (will be wrapped in envelope)
            queue_name: Queue name (defaults to DEFAULT_QUEUE)
            
        Returns:
            True if successful
        """
        queue_name = queue_name or self.DEFAULT_QUEUE
        
        # Create message envelope
        envelope = MessageEnvelope(
            message_id=str(uuid.uuid4()),
            message_type="model_ready_to_deploy",
            payload=message,
            timestamp=message.get("timestamp", datetime.utcnow()),
            retry_count=0,
            max_retries=self.retry_config["max_retries"]
        )
        
        # Retry logic with exponential backoff
        retries = 0
        base_delay = self.retry_config["base_delay"]
        max_delay = self.retry_config["max_delay"]
        
        while retries <= self.retry_config["max_retries"]:
            try:
                # Push to queue (left push for FIFO with right pop)
                self.client.lpush(queue_name, envelope.to_json())
                
                # Also publish to pub/sub for real-time subscribers
                self._publish_pubsub(message, queue_name)
                
                logger.info(f"Published message {envelope.message_id} to queue {queue_name}")
                return True
                
            except RedisError as e:
                retries += 1
                if retries > self.retry_config["max_retries"]:
                    logger.error(f"Failed to publish after {retries} attempts: {str(e)}")
                    # Send to DLQ
                    self._send_to_dlq(envelope, queue_name, str(e))
                    raise PublisherException(f"Failed to publish message: {str(e)}")
                
                # Calculate exponential backoff
                delay = min(base_delay * (2 ** (retries - 1)), max_delay)
                logger.warning(f"Publish failed, retrying in {delay}s (attempt {retries})")
                time.sleep(delay)
        
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
        """
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
    
    def health_check(self) -> Dict[str, Any]:
        """Check Redis connection health."""
        try:
            # Ping Redis
            latency_start = time.time()
            self.client.ping()
            latency = (time.time() - latency_start) * 1000  # ms
            
            # Get queue depths
            main_queue_depth = self.get_queue_depth(self.DEFAULT_QUEUE)
            processing_depth = self.get_queue_depth(
                self.DEFAULT_QUEUE + self.PROCESSING_QUEUE_SUFFIX
            )
            dlq_depth = self.get_queue_depth(self.DEFAULT_QUEUE + self.DLQ_SUFFIX)
            
            # Get Redis info
            info = self.client.info()
            
            return {
                "status": "healthy",
                "latency_ms": round(latency, 2),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "queue_depths": {
                    "main": main_queue_depth,
                    "processing": processing_depth,
                    "dlq": dlq_depth
                }
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "queue_depths": {
                    "main": None,
                    "processing": None,
                    "dlq": None
                }
            }
    
    def get_queue_depth(self, queue_name: str) -> Optional[int]:
        """Get number of messages in queue."""
        try:
            return self.client.llen(queue_name)
        except RedisError:
            return None
    
    def close(self) -> None:
        """Close Redis connections."""
        try:
            self.pool.disconnect()
            logger.info("Closed Redis connection pool")
        except Exception as e:
            logger.error(f"Error closing Redis connections: {str(e)}")
    
    def _publish_pubsub(self, message: Dict[str, Any], channel: str) -> None:
        """Publish to Redis pub/sub for real-time subscribers."""
        try:
            pubsub_channel = f"{channel}:pubsub"
            self.client.publish(pubsub_channel, json.dumps(message))
            logger.debug(f"Published to pub/sub channel {pubsub_channel}")
        except RedisError as e:
            # Don't fail the main publish if pub/sub fails
            logger.warning(f"Failed to publish to pub/sub: {str(e)}")
    
    def _send_to_dlq(self, envelope: MessageEnvelope, queue_name: str, error: str) -> None:
        """Send failed message to dead letter queue."""
        try:
            dlq_name = f"{queue_name}{self.DLQ_SUFFIX}"
            dlq_envelope = {
                "original_message": envelope.to_json(),
                "error": error,
                "failed_at": datetime.utcnow().isoformat(),
                "original_queue": queue_name
            }
            self.client.lpush(dlq_name, json.dumps(dlq_envelope))
            logger.info(f"Sent message {envelope.message_id} to DLQ")
        except Exception as e:
            logger.error(f"Failed to send to DLQ: {str(e)}")
    
    def consume_messages(
        self, 
        queue_name: Optional[str] = None,
        timeout: int = 0,
        process_callback=None
    ) -> None:
        """Consume messages from queue (for testing/debugging).
        
        Args:
            queue_name: Queue to consume from
            timeout: Blocking timeout in seconds (0 for non-blocking)
            process_callback: Function to process each message
        """
        queue_name = queue_name or self.DEFAULT_QUEUE
        processing_queue = f"{queue_name}{self.PROCESSING_QUEUE_SUFFIX}"
        
        while True:
            try:
                # Reliable queue pattern: move from main to processing queue
                message_data = self.client.brpoplpush(
                    queue_name, processing_queue, timeout=timeout
                )
                
                if not message_data:
                    break  # No message available
                
                # Parse envelope
                envelope = MessageEnvelope.from_json(message_data.decode())
                
                # Process message
                if process_callback:
                    success = process_callback(envelope.payload)
                    if success:
                        # Remove from processing queue
                        self.client.lrem(processing_queue, 1, message_data)
                        logger.info(f"Processed message {envelope.message_id}")
                    else:
                        # Move back to main queue for retry
                        if envelope.should_retry():
                            envelope.increment_retry()
                            self.client.lrem(processing_queue, 1, message_data)
                            self.client.lpush(queue_name, envelope.to_json())
                        else:
                            # Send to DLQ
                            self.client.lrem(processing_queue, 1, message_data)
                            self._send_to_dlq(envelope, queue_name, "Processing failed")
                
            except Exception as e:
                logger.error(f"Error consuming message: {str(e)}")
                if timeout == 0:
                    break


# Import datetime at module level
from datetime import datetime