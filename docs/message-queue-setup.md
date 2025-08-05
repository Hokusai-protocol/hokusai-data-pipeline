# Message Queue Setup Guide

## Overview

The Hokusai ML Platform emits `model_ready_to_deploy` messages when models pass baseline validation and are ready for token deployment. This guide covers setup and configuration of the message queue system.

## Architecture

```
Model Registration → Validation → Success → Message Queue → Token Deployment System
                                    ↓
                                 Failure → Log & Monitor
```

## Message Format

When a model is successfully registered and meets baseline requirements, the following message is emitted:

```json
{
  "message_id": "uuid-v4",
  "message_type": "model_ready_to_deploy",
  "timestamp": "2025-01-27T12:00:00Z",
  "payload": {
    "model_id": "model-name/version/token-id",
    "token_symbol": "msg-ai",
    "metric_name": "reply_rate",
    "baseline_value": 0.75,
    "current_value": 0.82,
    "improvement_percentage": 9.33,
    "model_name": "msg-model",
    "model_version": "1",
    "mlflow_run_id": "abc123def456",
    "contributor_address": "0x1234...",
    "experiment_name": "baseline-improvements",
    "tags": {
      "custom_key": "custom_value"
    }
  }
}
```

## Configuration

### Environment Variables

```bash
# Message Queue Type (currently only "redis" supported)
MESSAGE_QUEUE_TYPE=redis

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Queue Names
MESSAGE_QUEUE_NAME=hokusai:model_ready_queue

# Retry Configuration
MESSAGE_RETRY_MAX=3
MESSAGE_RETRY_BASE_DELAY=1.0
```

### Docker Compose

Redis is already included in the docker-compose.yml:

```yaml
redis:
  image: redis:7-alpine
  container_name: hokusai_redis
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 10s
    timeout: 5s
    retries: 5
```

## Usage

### Automatic Message Emission

Messages are automatically emitted when using the enhanced registry:

```python
from src.services.enhanced_model_registry import EnhancedModelRegistry

registry = EnhancedModelRegistry()

# Register a tokenized model that meets baseline
result = registry.register_tokenized_model_with_events(
    model_uri="runs:/abc123/model",
    model_name="my-model",
    token_id="msg-ai",
    metric_name="reply_rate",
    baseline_value=0.75,
    current_value=0.82,  # Meets baseline
    contributor_address="0x1234..."
)

# Check if event was emitted
if result.get("event_emitted"):
    print("Model ready to deploy message sent!")
```

### Manual Message Publishing

For custom use cases:

```python
from src.events.publishers.factory import get_publisher

publisher = get_publisher()

success = publisher.publish_model_ready(
    model_id="model-123",
    token_symbol="msg-ai",
    metric_name="accuracy",
    baseline_value=0.8,
    current_value=0.85,
    model_name="test_model",
    model_version="1",
    mlflow_run_id="run123"
)
```

## Message Queue Patterns

### Reliable Queue Processing

The Redis implementation uses the reliable queue pattern:

1. Messages are pushed to the main queue
2. Consumers use RPOPLPUSH to atomically move messages to a processing queue
3. After successful processing, messages are removed from the processing queue
4. Failed messages can be requeued or sent to dead letter queue

### Consumer Example

```python
from src.events.publishers.redis_publisher import RedisPublisher

publisher = RedisPublisher()

def process_message(payload):
    """Process model_ready_to_deploy message."""
    print(f"Model {payload['model_id']} ready for token {payload['token_symbol']}")
    # Trigger token deployment here
    return True

# Consume messages
publisher.consume_messages(
    process_callback=process_message,
    timeout=30  # Block for 30 seconds waiting for messages
)
```

## Monitoring

### Health Check Endpoint

The `/health` endpoint includes message queue status:

```bash
curl http://localhost:8001/health?detailed=true
```

Response includes:
```json
{
  "status": "healthy",
  "services": {
    "message_queue": "healthy",
    "message_queue_details": {
      "status": "healthy",
      "latency_ms": 1.2,
      "queue_depths": {
        "main": 5,
        "processing": 1,
        "dlq": 0
      }
    }
  }
}
```

### Queue Monitoring

Monitor queue depths:

```bash
# Check main queue depth
redis-cli LLEN hokusai:model_ready_queue

# Check processing queue
redis-cli LLEN hokusai:model_ready_queue:processing

# Check dead letter queue
redis-cli LLEN hokusai:model_ready_queue:dlq
```

### Metrics

The system tracks:
- Message publish success/failure rates
- Queue depths
- Processing latency
- Retry counts

## Troubleshooting

### Messages Not Being Published

1. Check Redis connectivity:
   ```bash
   redis-cli ping
   ```

2. Verify model meets baseline:
   ```python
   # Model must have current_value >= baseline_value
   ```

3. Check logs for validation errors:
   ```bash
   docker logs hokusai_api | grep "model_ready_to_deploy"
   ```

### High Queue Depth

If messages are accumulating:

1. Check consumer health
2. Monitor processing errors in DLQ
3. Scale consumers if needed

### Failed Messages

Failed messages are sent to the dead letter queue after max retries:

```bash
# View failed messages
redis-cli LRANGE hokusai:model_ready_queue:dlq 0 -1
```

## Future Enhancements

### AWS SQS Migration

When ready to migrate to SQS:

1. Set `MESSAGE_QUEUE_TYPE=sqs`
2. Configure AWS credentials
3. The factory will automatically use SQS publisher

### Additional Event Types

The system supports multiple event types:
- `model_registered`
- `model_validation_failed`
- `model_deployed`
- `metric_improved`

## Security Considerations

1. **Redis Security**: Use Redis AUTH in production
2. **Message Encryption**: Consider encrypting sensitive data
3. **Access Control**: Limit queue access to authorized services
4. **Audit Trail**: Log all message publications

## Example Integration

Token deployment service example:

```python
import redis
import json

r = redis.Redis()

while True:
    # Reliable queue pattern
    message = r.brpoplpush(
        "hokusai:model_ready_queue",
        "hokusai:model_ready_queue:processing",
        timeout=30
    )
    
    if message:
        data = json.loads(message)
        payload = data['payload']
        
        # Deploy token
        token_address = deploy_token(
            symbol=payload['token_symbol'],
            model_id=payload['model_id'],
            baseline=payload['baseline_value']
        )
        
        # Remove from processing queue
        r.lrem("hokusai:model_ready_queue:processing", 1, message)
```