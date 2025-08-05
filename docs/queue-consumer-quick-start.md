# Quick Start: Consuming Model Ready Messages in External Services

## Overview

The Hokusai ML Platform emits `model_ready_to_deploy` messages to a Redis queue when models are ready for token deployment. This guide shows how to consume these messages from the `hokusai-smart-contracts` repository.

## Message Format

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "message_type": "model_ready_to_deploy",
  "timestamp": "2025-01-27T15:30:00Z",
  "payload": {
    "model_id": "model-name/1/msg-ai",
    "token_symbol": "msg-ai",
    "metric_name": "reply_rate",
    "baseline_value": 0.75,
    "current_value": 0.82,
    "improvement_percentage": 9.33,
    "model_name": "msg-model",
    "model_version": "1",
    "mlflow_run_id": "abc123def456",
    "contributor_address": "0x1234567890123456789012345678901234567890"
  }
}
```

## Quick Implementation

### 1. Install Redis Client

```bash
pip install redis>=4.5.0
```

### 2. Basic Consumer Code

```python
import redis
import json
import os

# Connect to Redis
redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

# Queue names
QUEUE = "hokusai:model_ready_queue"
PROCESSING = f"{QUEUE}:processing"

def process_model_deployment(payload):
    """Deploy token for the model."""
    print(f"Deploying token {payload['token_symbol']} for model {payload['model_id']}")
    # Your token deployment logic here
    return True

# Consume messages
while True:
    # Reliable queue pattern: move from main to processing queue
    message = redis_client.brpoplpush(QUEUE, PROCESSING, timeout=5)
    
    if message:
        try:
            data = json.loads(message)
            payload = data['payload']
            
            # Process the message
            if process_model_deployment(payload):
                # Success - remove from processing queue
                redis_client.lrem(PROCESSING, 1, message)
                print(f"Processed: {data['message_id']}")
        except Exception as e:
            print(f"Error: {e}")
            # Handle error (retry, move to DLQ, etc.)
```

## Connection Options

### Option 1: Direct Redis Connection (Development)

```python
# Local development
REDIS_URL = "redis://localhost:6379/0"

# With authentication
REDIS_URL = "redis://:password@redis-host:6379/0"

# With TLS (production)
REDIS_URL = "rediss://redis-host:6380/0"
```

### Option 2: Docker Network (Recommended)

```yaml
# docker-compose.yml
version: '3.8'
services:
  smart-contracts:
    image: hokusai/smart-contracts
    environment:
      - REDIS_URL=redis://redis:6379/0
    networks:
      - hokusai-network

networks:
  hokusai-network:
    external: true
```

### Option 3: External Access

For production external access:

1. **VPN Access**: Connect through Hokusai VPN to access internal Redis
2. **Public Endpoint**: Use authenticated Redis endpoint (contact DevOps for credentials)
3. **AWS PrivateLink**: For AWS-to-AWS connectivity

## Environment Variables

```bash
# Required
REDIS_URL=redis://redis.hokusai.internal:6379/0

# Optional
REDIS_PASSWORD=your-password          # If AUTH enabled
REDIS_SSL_CERT_REQS=required         # For TLS
QUEUE_POLL_INTERVAL=5                # Seconds between polls
PROCESSING_TIMEOUT=300               # Max processing time
```

## Full Example with Error Handling

See `/examples/external_queue_consumer.py` for a complete implementation with:
- Graceful shutdown
- Error handling
- Retry logic
- Queue statistics
- Logging

## Testing Your Integration

### 1. Push a Test Message

```python
import redis
import json
import uuid
from datetime import datetime

r = redis.from_url("redis://localhost:6379/0")

test_message = {
    "message_id": str(uuid.uuid4()),
    "message_type": "model_ready_to_deploy",
    "timestamp": datetime.utcnow().isoformat(),
    "payload": {
        "model_id": "test-model/1/test-token",
        "token_symbol": "TEST",
        "metric_name": "accuracy",
        "baseline_value": 0.80,
        "current_value": 0.85,
        "improvement_percentage": 6.25,
        "model_name": "test-model",
        "model_version": "1",
        "mlflow_run_id": "test-run-123"
    }
}

r.lpush("hokusai:model_ready_queue", json.dumps(test_message))
print("Test message pushed to queue")
```

### 2. Check Queue Status

```bash
# Check queue depths
redis-cli LLEN hokusai:model_ready_queue
redis-cli LLEN hokusai:model_ready_queue:processing

# View messages (without consuming)
redis-cli LRANGE hokusai:model_ready_queue 0 -1
```

## Production Deployment

### Systemd Service

```ini
[Unit]
Description=Hokusai Token Deployer
After=network.target

[Service]
Type=simple
User=hokusai
Environment="REDIS_URL=redis://redis.internal:6379/0"
ExecStart=/usr/bin/python3 /opt/hokusai/queue_consumer.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Docker Container

```dockerfile
FROM python:3.9-slim
RUN pip install redis
COPY queue_consumer.py /app/
CMD ["python", "/app/queue_consumer.py"]
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: token-deployer
spec:
  replicas: 2
  selector:
    matchLabels:
      app: token-deployer
  template:
    metadata:
      labels:
        app: token-deployer
    spec:
      containers:
      - name: consumer
        image: hokusai/token-deployer:latest
        env:
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: redis-credentials
              key: url
```

## Monitoring

### Health Check Endpoint

```python
from flask import Flask, jsonify
app = Flask(__name__)

@app.route('/health')
def health():
    stats = {
        "main_queue": redis_client.llen("hokusai:model_ready_queue"),
        "processing": redis_client.llen("hokusai:model_ready_queue:processing"),
        "status": "healthy"
    }
    return jsonify(stats)
```

### Metrics to Track

- Messages processed per minute
- Average processing time
- Queue depths
- Error rates
- Token deployment success rate

## Troubleshooting

### Connection Issues

```bash
# Test Redis connectivity
redis-cli -h redis.hokusai.internal ping

# Check network
telnet redis.hokusai.internal 6379
```

### Message Format Issues

```python
# Validate message format
try:
    data = json.loads(message)
    assert data.get('message_type') == 'model_ready_to_deploy'
    assert 'payload' in data
    assert all(k in data['payload'] for k in ['model_id', 'token_symbol'])
except Exception as e:
    logger.error(f"Invalid message format: {e}")
```

### Performance Issues

- Use connection pooling
- Process messages in batches
- Implement concurrent processing with workers
- Monitor Redis memory usage

## Support

- **Slack**: #hokusai-ml-platform
- **Docs**: https://docs.hokus.ai/message-queue
- **Redis Admin**: devops@hokusai.ai

## Next Steps

1. Copy the example consumer code
2. Add your token deployment logic
3. Test with local Redis
4. Deploy to your environment
5. Monitor queue processing

The complete implementation guide with advanced features is available in `/docs/queue-consumer-integration-guide.md`.