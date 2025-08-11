"""Example Redis queue consumer for model_ready_to_deploy messages.

This example shows how downstream services (hokusai-site, hokusai-token) can
consume messages from the Redis queue when models are ready for deployment.
"""

import json
import logging
import os
import signal
import sys
import time
from typing import Dict, Any

import redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModelDeploymentConsumer:
    """Consumer for model deployment messages from Redis queue."""
    
    def __init__(self, redis_url: str = None):
        """Initialize consumer with Redis connection.
        
        Args:
            redis_url: Redis connection URL with authentication
        """
        if not redis_url:
            # Build Redis URL from environment variables
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = os.getenv("REDIS_PORT", "6379")
            redis_auth_token = os.getenv("REDIS_AUTH_TOKEN")
            
            if redis_auth_token:
                redis_url = f"redis://:{redis_auth_token}@{redis_host}:{redis_port}/0"
            else:
                redis_url = f"redis://{redis_host}:{redis_port}/0"
        
        self.redis_url = redis_url
        self.client = redis.Redis.from_url(redis_url, decode_responses=True)
        self.running = True
        self.queue_name = "hokusai:model_ready_queue"
        self.processing_queue = f"{self.queue_name}:processing"
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info("Shutdown signal received, stopping consumer...")
        self.running = False
    
    def process_message(self, message: Dict[str, Any]) -> bool:
        """Process a model deployment message.
        
        This is where downstream services would implement their logic:
        - hokusai-site: Update marketplace with new model
        - hokusai-token: Trigger token minting process
        
        Args:
            message: Message payload with model information
            
        Returns:
            True if processing was successful
        """
        try:
            model_id = message.get("model_id")
            token_symbol = message.get("token_symbol")
            metric_name = message.get("metric_name")
            baseline_value = message.get("baseline_value")
            current_value = message.get("current_value")
            
            improvement = ((current_value - baseline_value) / baseline_value) * 100
            
            logger.info(
                f"Processing model deployment:\n"
                f"  Model ID: {model_id}\n"
                f"  Token: {token_symbol}\n"
                f"  Metric: {metric_name}\n"
                f"  Improvement: {improvement:.2f}%"
            )
            
            # Example processing logic for different services:
            
            # For hokusai-site:
            # - Update model catalog
            # - Display on marketplace
            # - Send notifications to subscribers
            
            # For hokusai-token:
            # - Validate model metrics
            # - Calculate token allocation
            # - Trigger smart contract interaction
            # - Mint tokens for model
            
            # Simulate processing time
            time.sleep(0.5)
            
            logger.info(f"Successfully processed model {model_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return False
    
    def consume(self, batch_size: int = 1, timeout: int = 5):
        """Consume messages from the Redis queue.
        
        Uses reliable queue pattern with processing queue to prevent message loss.
        
        Args:
            batch_size: Number of messages to process in parallel
            timeout: Timeout for blocking pop operation
        """
        logger.info(f"Starting consumer for queue: {self.queue_name}")
        logger.info(f"Redis connection: {self.redis_url.split('@')[1] if '@' in self.redis_url else self.redis_url}")
        
        while self.running:
            try:
                # Use BRPOPLPUSH for reliable queue processing
                # This atomically moves message from main queue to processing queue
                raw_message = self.client.brpoplpush(
                    self.queue_name,
                    self.processing_queue,
                    timeout=timeout
                )
                
                if not raw_message:
                    continue
                
                # Parse message envelope
                try:
                    envelope = json.loads(raw_message)
                    message_id = envelope.get("message_id")
                    message_type = envelope.get("message_type")
                    payload = envelope.get("payload", {})
                    retry_count = envelope.get("retry_count", 0)
                    
                    logger.info(f"Received message {message_id} (type: {message_type})")
                    
                    # Process the message
                    if self.process_message(payload):
                        # Remove from processing queue on success
                        self.client.lrem(self.processing_queue, 1, raw_message)
                        logger.info(f"Message {message_id} processed successfully")
                    else:
                        # On failure, could move to DLQ or retry
                        if retry_count < 3:
                            # Increment retry count and re-queue
                            envelope["retry_count"] = retry_count + 1
                            self.client.lpush(self.queue_name, json.dumps(envelope))
                            self.client.lrem(self.processing_queue, 1, raw_message)
                            logger.warning(f"Message {message_id} requeued (retry {retry_count + 1})")
                        else:
                            # Move to dead letter queue
                            dlq_name = f"{self.queue_name}:dlq"
                            self.client.lpush(dlq_name, raw_message)
                            self.client.lrem(self.processing_queue, 1, raw_message)
                            logger.error(f"Message {message_id} moved to DLQ after {retry_count} retries")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in message: {e}")
                    # Move invalid messages to DLQ
                    self.client.lpush(f"{self.queue_name}:dlq", raw_message)
                    self.client.lrem(self.processing_queue, 1, raw_message)
                
            except redis.ConnectionError as e:
                logger.error(f"Redis connection error: {e}")
                time.sleep(5)  # Wait before retrying
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                time.sleep(1)
        
        logger.info("Consumer stopped")
    
    def get_queue_stats(self) -> Dict[str, int]:
        """Get current queue statistics.
        
        Returns:
            Dictionary with queue depths
        """
        return {
            "main_queue": self.client.llen(self.queue_name),
            "processing_queue": self.client.llen(self.processing_queue),
            "dead_letter_queue": self.client.llen(f"{self.queue_name}:dlq")
        }


def main():
    """Main entry point for the consumer."""
    # Configure from environment or use defaults
    redis_host = os.getenv("REDIS_HOST", "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com")
    redis_port = os.getenv("REDIS_PORT", "6379")
    redis_auth_token = os.getenv("REDIS_AUTH_TOKEN")
    
    if not redis_auth_token:
        logger.warning("REDIS_AUTH_TOKEN not set, using unauthenticated connection")
    
    # Create and run consumer
    consumer = ModelDeploymentConsumer()
    
    # Print initial queue stats
    stats = consumer.get_queue_stats()
    logger.info(f"Queue stats: {stats}")
    
    # Start consuming messages
    try:
        consumer.consume()
    except KeyboardInterrupt:
        logger.info("Consumer interrupted by user")
    finally:
        # Print final stats
        stats = consumer.get_queue_stats()
        logger.info(f"Final queue stats: {stats}")


if __name__ == "__main__":
    main()