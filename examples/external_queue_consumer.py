"""
Example: External Queue Consumer for model_ready_to_deploy Messages

This example shows how an external service (like hokusai-smart-contracts)
can consume messages from the Hokusai ML Platform's Redis queue.

Usage:
    REDIS_URL=redis://localhost:6379/0 python external_queue_consumer.py
"""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from typing import Dict, Any

import redis

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ModelReadyToDeployConsumer:
    """Simple consumer for model_ready_to_deploy messages."""
    
    def __init__(self, redis_url: str):
        """Initialize consumer with Redis connection."""
        self.redis_url = redis_url
        self.queue_name = "hokusai:model_ready_queue"
        self.processing_queue = f"{self.queue_name}:processing"
        self.running = True
        
        # Connect to Redis
        logger.info(f"Connecting to Redis at {redis_url}")
        self.redis_client = redis.from_url(redis_url)
        
        # Test connection
        self.redis_client.ping()
        logger.info("Successfully connected to Redis")
        
        # Setup graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)
    
    def _shutdown(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def consume_messages(self):
        """Main consumption loop."""
        logger.info(f"Starting to consume messages from {self.queue_name}")
        logger.info("Press Ctrl+C to stop")
        
        while self.running:
            try:
                # Check queue stats
                main_queue_len = self.redis_client.llen(self.queue_name)
                processing_len = self.redis_client.llen(self.processing_queue)
                logger.debug(f"Queue depths - Main: {main_queue_len}, Processing: {processing_len}")
                
                # Use BRPOPLPUSH for reliable message processing
                # This atomically moves a message from the main queue to processing queue
                raw_message = self.redis_client.brpoplpush(
                    self.queue_name,
                    self.processing_queue,
                    timeout=5  # Wait up to 5 seconds for a message
                )
                
                if not raw_message:
                    continue  # No message available
                
                # Process the message
                self._process_message(raw_message)
                
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                logger.error(f"Error in consume loop: {e}", exc_info=True)
                time.sleep(5)
        
        logger.info("Consumer stopped")
    
    def _process_message(self, raw_message: bytes):
        """Process a single message."""
        try:
            # Decode message
            message_str = raw_message.decode('utf-8')
            envelope = json.loads(message_str)
            
            # Extract message details
            message_id = envelope.get('message_id', 'unknown')
            message_type = envelope.get('message_type')
            payload = envelope.get('payload', {})
            
            logger.info(f"Processing message {message_id} of type {message_type}")
            
            # Validate it's the right message type
            if message_type != "model_ready_to_deploy":
                logger.warning(f"Unexpected message type: {message_type}")
                # Still remove from processing queue
                self.redis_client.lrem(self.processing_queue, 1, raw_message)
                return
            
            # Extract model deployment information
            model_id = payload.get('model_id')
            token_symbol = payload.get('token_symbol')
            metric_name = payload.get('metric_name')
            baseline_value = payload.get('baseline_value')
            current_value = payload.get('current_value')
            improvement = payload.get('improvement_percentage', 0)
            contributor = payload.get('contributor_address')
            
            logger.info(f"""
            Model Ready for Deployment:
            - Model ID: {model_id}
            - Token Symbol: {token_symbol}
            - Metric: {metric_name}
            - Performance: {current_value:.4f} (baseline: {baseline_value:.4f})
            - Improvement: {improvement:.2f}%
            - Contributor: {contributor or 'Not specified'}
            """)
            
            # ==========================================
            # HERE: Add your token deployment logic
            # ==========================================
            # Example:
            # token_address = deploy_token_contract(
            #     symbol=token_symbol,
            #     model_id=model_id,
            #     performance=current_value,
            #     contributor=contributor
            # )
            # logger.info(f"Deployed token at address: {token_address}")
            
            # Simulate processing time
            time.sleep(2)
            
            # If processing succeeded, remove from processing queue
            self.redis_client.lrem(self.processing_queue, 1, raw_message)
            logger.info(f"Successfully processed message {message_id}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode message: {e}")
            # Move to dead letter queue or handle error
            self._handle_failed_message(raw_message, str(e))
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            self._handle_failed_message(raw_message, str(e))
    
    def _handle_failed_message(self, raw_message: bytes, error: str):
        """Handle messages that failed processing."""
        try:
            # For this example, we'll just log and remove from processing queue
            logger.error(f"Failed to process message: {error}")
            
            # In production, you might want to:
            # 1. Retry with exponential backoff
            # 2. Move to a dead letter queue
            # 3. Send alerts
            
            # Remove from processing queue
            self.redis_client.lrem(self.processing_queue, 1, raw_message)
            
        except Exception as e:
            logger.error(f"Error handling failed message: {e}")
    
    def get_queue_stats(self) -> Dict[str, int]:
        """Get current queue statistics."""
        return {
            "main_queue": self.redis_client.llen(self.queue_name),
            "processing": self.redis_client.llen(self.processing_queue),
            "dlq": self.redis_client.llen(f"{self.queue_name}:dlq")
        }


def main():
    """Main entry point."""
    # Get Redis URL from environment or use default
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Create and run consumer
    consumer = ModelReadyToDeployConsumer(redis_url)
    
    # Show initial queue stats
    stats = consumer.get_queue_stats()
    logger.info(f"Initial queue stats: {stats}")
    
    # Start consuming
    try:
        consumer.consume_messages()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


# ==========================================
# DEPLOYMENT INSTRUCTIONS
# ==========================================
#
# 1. Install Dependencies:
#    pip install redis>=4.5.0
#
# 2. Set Environment Variables:
#    export REDIS_URL=redis://your-redis-host:6379/0
#
# 3. Run the Consumer:
#    python external_queue_consumer.py
#
# 4. For Production Deployment:
#    - Use a process manager (systemd, supervisor, etc.)
#    - Run multiple instances for high availability
#    - Monitor queue depths and processing rates
#    - Set up alerts for failures
#
# 5. Docker Deployment:
#    FROM python:3.9-slim
#    RUN pip install redis
#    COPY external_queue_consumer.py /app/
#    WORKDIR /app
#    CMD ["python", "external_queue_consumer.py"]
#
# ==========================================