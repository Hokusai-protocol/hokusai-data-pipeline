# Queue Consumer Integration Guide for External Services

This guide explains how external services (like hokusai-smart-contracts) can consume `model_ready_to_deploy` messages from the Hokusai ML Platform's message queue.

## Architecture Overview

```
┌─────────────────────────┐     ┌─────────────────────┐     ┌──────────────────────┐
│ Hokusai ML Platform     │     │      Redis Queue     │     │ Smart Contracts Repo │
│ - Model Registration    │────▶│ - model_ready_queue  │────▶│ - Queue Reader       │
│ - Emits Messages        │     │ - Reliable Pattern   │     │ - Token Deployment   │
└─────────────────────────┘     └─────────────────────┘     └──────────────────────┘
```

## Prerequisites

1. **Network Access**: The smart contracts service must have network access to the Redis instance
2. **Redis Credentials**: Connection string and any authentication required
3. **Python Environment**: Python 3.8+ with Redis client library

## Implementation Steps

### 1. Install Dependencies

In your hokusai-smart-contracts repository:

```bash
pip install redis>=4.5.0 pydantic>=2.0.0
```

Or add to your requirements.txt:
```
redis>=4.5.0
pydantic>=2.0.0
```

### 2. Copy Message Schema

Create a file `queue_reader/schemas.py` with the message schema:

```python
from datetime import datetime
from typing import Dict, Optional, Any
from pydantic import BaseModel


class ModelReadyToDeployMessage(BaseModel):
    """Message schema for model_ready_to_deploy events."""
    
    # Required fields
    model_id: str
    token_symbol: str
    metric_name: str
    baseline_value: float
    current_value: float
    
    # Model metadata
    model_name: str
    model_version: str
    mlflow_run_id: str
    
    # Optional metadata
    improvement_percentage: Optional[float] = None
    contributor_address: Optional[str] = None
    experiment_name: Optional[str] = None
    tags: Optional[Dict[str, str]] = None
    
    # System fields
    timestamp: datetime
    message_version: str = "1.0"


class MessageEnvelope(BaseModel):
    """Envelope for queue messages."""
    
    message_id: str
    message_type: str
    payload: Dict[str, Any]
    timestamp: datetime
    retry_count: int = 0
    max_retries: int = 3
```

### 3. Implement Queue Reader

Create `queue_reader/consumer.py`:

```python
import json
import logging
import signal
import sys
import time
from typing import Callable, Optional

import redis
from redis.exceptions import ConnectionError, RedisError

from .schemas import MessageEnvelope, ModelReadyToDeployMessage

logger = logging.getLogger(__name__)


class QueueConsumer:
    """Consumes model_ready_to_deploy messages from Redis queue."""
    
    def __init__(
        self,
        redis_url: str,
        queue_name: str = "hokusai:model_ready_queue",
        processing_timeout: int = 300,  # 5 minutes
    ):
        """Initialize queue consumer.
        
        Args:
            redis_url: Redis connection URL (e.g., "redis://host:6379/0")
            queue_name: Name of the queue to consume from
            processing_timeout: Max time to process a message (seconds)
        """
        self.redis_url = redis_url
        self.queue_name = queue_name
        self.processing_queue = f"{queue_name}:processing"
        self.dlq_name = f"{queue_name}:dlq"
        self.processing_timeout = processing_timeout
        self.running = False
        
        # Create Redis connection
        self.redis_client = redis.from_url(redis_url)
        self._test_connection()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _test_connection(self):
        """Test Redis connection."""
        try:
            self.redis_client.ping()
            logger.info(f"Connected to Redis at {self.redis_url}")
        except (ConnectionError, RedisError) as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def consume(
        self,
        message_handler: Callable[[ModelReadyToDeployMessage], bool],
        batch_size: int = 1,
        poll_interval: int = 1,
    ):
        """Start consuming messages from the queue.
        
        Args:
            message_handler: Function to process each message
            batch_size: Number of messages to process in parallel
            poll_interval: Seconds to wait between polls when queue is empty
        """
        self.running = True
        logger.info(f"Starting queue consumer for {self.queue_name}")
        
        while self.running:
            try:
                # Use BRPOPLPUSH for reliable queue processing
                # This atomically moves a message from main queue to processing queue
                raw_message = self.redis_client.brpoplpush(
                    self.queue_name,
                    self.processing_queue,
                    timeout=poll_interval
                )
                
                if not raw_message:
                    continue  # No message available, continue polling
                
                # Process the message
                self._process_message(raw_message, message_handler)
                
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in consume loop: {e}", exc_info=True)
                time.sleep(poll_interval)
        
        logger.info("Queue consumer stopped")
    
    def _process_message(
        self,
        raw_message: bytes,
        message_handler: Callable[[ModelReadyToDeployMessage], bool],
    ):
        """Process a single message."""
        try:
            # Parse message envelope
            message_str = raw_message.decode('utf-8')
            envelope_data = json.loads(message_str)
            envelope = MessageEnvelope(**envelope_data)
            
            # Extract and validate payload
            message = ModelReadyToDeployMessage(**envelope.payload)
            
            logger.info(
                f"Processing message {envelope.message_id}: "
                f"Model {message.model_id} ready for token {message.token_symbol}"
            )
            
            # Call the handler
            success = message_handler(message)
            
            if success:
                # Remove from processing queue on success
                self.redis_client.lrem(self.processing_queue, 1, raw_message)
                logger.info(f"Successfully processed message {envelope.message_id}")
            else:
                # Handle failure
                self._handle_failed_message(envelope, raw_message, "Handler returned False")
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
            self._move_to_dlq(raw_message, f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            self._handle_failed_message(envelope, raw_message, str(e))
    
    def _handle_failed_message(
        self,
        envelope: MessageEnvelope,
        raw_message: bytes,
        error: str
    ):
        """Handle a message that failed processing."""
        if envelope.retry_count < envelope.max_retries:
            # Increment retry count and requeue
            envelope.retry_count += 1
            updated_message = envelope.json()
            
            # Remove from processing queue
            self.redis_client.lrem(self.processing_queue, 1, raw_message)
            
            # Add back to main queue with updated retry count
            self.redis_client.lpush(self.queue_name, updated_message)
            
            logger.warning(
                f"Message {envelope.message_id} failed, "
                f"retrying ({envelope.retry_count}/{envelope.max_retries})"
            )
        else:
            # Max retries exceeded, move to DLQ
            self._move_to_dlq(raw_message, error)
    
    def _move_to_dlq(self, raw_message: bytes, error: str):
        """Move failed message to dead letter queue."""
        try:
            dlq_entry = {
                "original_message": raw_message.decode('utf-8'),
                "error": error,
                "failed_at": datetime.utcnow().isoformat(),
                "queue": self.queue_name
            }
            
            # Remove from processing queue
            self.redis_client.lrem(self.processing_queue, 1, raw_message)
            
            # Add to DLQ
            self.redis_client.lpush(self.dlq_name, json.dumps(dlq_entry))
            
            logger.error(f"Moved message to DLQ due to: {error}")
        except Exception as e:
            logger.error(f"Failed to move message to DLQ: {e}")
    
    def get_queue_stats(self) -> Dict[str, int]:
        """Get current queue statistics."""
        return {
            "main_queue": self.redis_client.llen(self.queue_name),
            "processing": self.redis_client.llen(self.processing_queue),
            "dead_letter": self.redis_client.llen(self.dlq_name),
        }


# Import at module level
from datetime import datetime
```

### 4. Implement Token Deployment Handler

Create `token_deployer.py`:

```python
import logging
from web3 import Web3
from queue_reader.schemas import ModelReadyToDeployMessage

logger = logging.getLogger(__name__)


class TokenDeployer:
    """Handles token deployment for ready models."""
    
    def __init__(self, web3_provider_url: str, deployer_private_key: str):
        """Initialize token deployer.
        
        Args:
            web3_provider_url: Ethereum node URL
            deployer_private_key: Private key for deployment account
        """
        self.w3 = Web3(Web3.HTTPProvider(web3_provider_url))
        self.account = self.w3.eth.account.from_key(deployer_private_key)
        
    def deploy_token(self, message: ModelReadyToDeployMessage) -> bool:
        """Deploy token for a ready model.
        
        Args:
            message: Model ready to deploy message
            
        Returns:
            True if deployment successful
        """
        try:
            logger.info(f"Deploying token for model {message.model_id}")
            
            # Validate message
            if not self._validate_deployment_criteria(message):
                logger.error("Model does not meet deployment criteria")
                return False
            
            # Deploy token contract
            token_address = self._deploy_token_contract(
                symbol=message.token_symbol,
                name=f"Hokusai {message.token_symbol}",
                model_id=message.model_id,
                baseline_metric=message.baseline_value,
                current_metric=message.current_value,
                contributor=message.contributor_address
            )
            
            # Register token in registry
            self._register_token(
                token_address=token_address,
                model_id=message.model_id,
                mlflow_run_id=message.mlflow_run_id
            )
            
            logger.info(f"Successfully deployed token at {token_address}")
            return True
            
        except Exception as e:
            logger.error(f"Token deployment failed: {e}", exc_info=True)
            return False
    
    def _validate_deployment_criteria(self, message: ModelReadyToDeployMessage) -> bool:
        """Validate model meets all deployment criteria."""
        # Check improvement percentage
        if message.improvement_percentage and message.improvement_percentage < 0:
            logger.error("Model performance is below baseline")
            return False
        
        # Check contributor address
        if message.contributor_address and not self.w3.is_address(message.contributor_address):
            logger.error(f"Invalid contributor address: {message.contributor_address}")
            return False
        
        return True
    
    def _deploy_token_contract(self, **kwargs) -> str:
        """Deploy the actual token contract."""
        # Implementation depends on your smart contract
        # This is a placeholder
        logger.info(f"Deploying contract with params: {kwargs}")
        
        # Example deployment logic:
        # contract = self.w3.eth.contract(abi=TOKEN_ABI, bytecode=TOKEN_BYTECODE)
        # tx = contract.constructor(**kwargs).build_transaction({
        #     'from': self.account.address,
        #     'nonce': self.w3.eth.get_transaction_count(self.account.address),
        #     'gas': 3000000,
        #     'gasPrice': self.w3.eth.gas_price
        # })
        # signed = self.account.sign_transaction(tx)
        # tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        # receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        # return receipt.contractAddress
        
        return "0x1234567890123456789012345678901234567890"  # Placeholder
    
    def _register_token(self, token_address: str, model_id: str, mlflow_run_id: str):
        """Register token in Hokusai registry."""
        logger.info(f"Registering token {token_address} for model {model_id}")
        # Implementation depends on your registry contract
```

### 5. Create Main Application

Create `main.py`:

```python
import logging
import os
from queue_reader.consumer import QueueConsumer
from token_deployer import TokenDeployer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Main entry point for queue consumer."""
    # Configuration from environment variables
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    web3_provider = os.environ.get("WEB3_PROVIDER_URL", "http://localhost:8545")
    deployer_key = os.environ.get("DEPLOYER_PRIVATE_KEY")
    
    if not deployer_key:
        logger.error("DEPLOYER_PRIVATE_KEY environment variable required")
        return
    
    # Initialize components
    consumer = QueueConsumer(redis_url=redis_url)
    deployer = TokenDeployer(
        web3_provider_url=web3_provider,
        deployer_private_key=deployer_key
    )
    
    # Log startup info
    logger.info("Starting Hokusai token deployment service")
    stats = consumer.get_queue_stats()
    logger.info(f"Queue stats: {stats}")
    
    # Start consuming messages
    try:
        consumer.consume(
            message_handler=deployer.deploy_token,
            poll_interval=5  # Check every 5 seconds
        )
    except Exception as e:
        logger.error(f"Consumer error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
```

### 6. Docker Configuration

Create `Dockerfile`:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the consumer
CMD ["python", "main.py"]
```

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  token-deployer:
    build: .
    container_name: hokusai_token_deployer
    environment:
      - REDIS_URL=redis://redis.hokusai.internal:6379/0
      - WEB3_PROVIDER_URL=${WEB3_PROVIDER_URL}
      - DEPLOYER_PRIVATE_KEY=${DEPLOYER_PRIVATE_KEY}
      - LOG_LEVEL=INFO
    restart: unless-stopped
    networks:
      - hokusai-network

networks:
  hokusai-network:
    external: true
```

## Environment Configuration

### Development

Create `.env.development`:
```bash
REDIS_URL=redis://localhost:6379/0
WEB3_PROVIDER_URL=http://localhost:8545
DEPLOYER_PRIVATE_KEY=your_test_private_key_here
LOG_LEVEL=DEBUG
```

### Production

Use secure environment variables or secrets management:
```bash
REDIS_URL=redis://redis.hokusai.internal:6379/0
WEB3_PROVIDER_URL=https://mainnet.infura.io/v3/YOUR_PROJECT_ID
DEPLOYER_PRIVATE_KEY=${DEPLOYER_PRIVATE_KEY_FROM_SECRETS}
LOG_LEVEL=INFO
```

## Network Access Requirements

### For Docker Deployment

If both services are in Docker:
1. Ensure both containers are on the same Docker network
2. Use service names for internal communication
3. Redis should be accessible at `redis://redis:6379`

### For External Access

If the smart contracts service is external:
1. Redis must be exposed on a public IP or through VPN
2. Configure Redis with authentication:
   ```
   REDIS_URL=redis://:password@redis.hokusai.ai:6379/0
   ```
3. Set up firewall rules to allow access from smart contracts service

### Security Considerations

1. **Authentication**: Use Redis AUTH password
   ```python
   redis_url = "redis://:your_redis_password@host:6379/0"
   ```

2. **TLS/SSL**: For production, use Redis with TLS
   ```python
   redis_url = "rediss://host:6380/0"  # Note the 'rediss' protocol
   ```

3. **Network Security**:
   - Use VPN or private networking between services
   - Whitelist IP addresses in Redis configuration
   - Use firewall rules to restrict access

## Monitoring and Operations

### Health Check Endpoint

Add a health check for monitoring:

```python
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/health')
def health():
    """Health check endpoint."""
    try:
        stats = consumer.get_queue_stats()
        redis_healthy = consumer.redis_client.ping()
        
        return jsonify({
            "status": "healthy" if redis_healthy else "unhealthy",
            "queue_stats": stats,
            "service": "token-deployer"
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500
```

### Monitoring Metrics

Track these metrics:
- Messages processed per minute
- Processing time per message
- Success/failure rates
- Queue depths
- Token deployment gas costs

### Error Recovery

For messages in the dead letter queue:

```python
def reprocess_dlq_messages():
    """Reprocess messages from DLQ."""
    dlq_name = f"{consumer.queue_name}:dlq"
    
    while True:
        # Get message from DLQ
        message = consumer.redis_client.rpop(dlq_name)
        if not message:
            break
            
        # Parse and requeue
        dlq_entry = json.loads(message)
        original = dlq_entry["original_message"]
        
        # Add back to main queue
        consumer.redis_client.lpush(consumer.queue_name, original)
        logger.info("Requeued message from DLQ")
```

## Testing

### Unit Tests

```python
import pytest
from unittest.mock import MagicMock, patch
from queue_reader.consumer import QueueConsumer

def test_message_processing():
    """Test message processing."""
    # Mock Redis
    with patch('redis.from_url') as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        
        # Create consumer
        consumer = QueueConsumer("redis://localhost:6379")
        
        # Mock message handler
        handler = MagicMock(return_value=True)
        
        # Test processing
        test_message = {
            "message_id": "test-123",
            "message_type": "model_ready_to_deploy",
            "payload": {
                "model_id": "test-model",
                "token_symbol": "TEST",
                # ... other fields
            }
        }
        
        consumer._process_message(
            json.dumps(test_message).encode(),
            handler
        )
        
        # Verify handler was called
        handler.assert_called_once()
```

### Integration Tests

Test with a real Redis instance:

```python
def test_end_to_end_flow():
    """Test full message flow."""
    # Start Redis test container
    # Push test message
    # Start consumer
    # Verify message processed
    # Check token deployed
```

## Troubleshooting

### Common Issues

1. **Connection Refused**
   - Check Redis is running
   - Verify network connectivity
   - Check firewall rules

2. **Authentication Failed**
   - Verify Redis password
   - Check AUTH configuration

3. **Messages Not Processing**
   - Check queue names match
   - Verify message format
   - Check logs for errors

4. **High Memory Usage**
   - Implement message batching
   - Add memory limits to container
   - Monitor queue depths

### Debug Commands

```bash
# Check queue depths
redis-cli LLEN hokusai:model_ready_queue

# View messages without consuming
redis-cli LRANGE hokusai:model_ready_queue 0 10

# Check processing queue
redis-cli LLEN hokusai:model_ready_queue:processing

# View DLQ messages
redis-cli LRANGE hokusai:model_ready_queue:dlq 0 -1
```

## Summary

This implementation provides:
1. Reliable message consumption with retry logic
2. Dead letter queue for failed messages
3. Graceful shutdown handling
4. Health monitoring
5. Comprehensive error handling
6. Easy deployment with Docker

The consumer will continuously monitor the Redis queue and trigger token deployments when models are ready, ensuring reliable processing of all messages from the Hokusai ML Platform.