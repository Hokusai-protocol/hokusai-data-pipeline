# Webhook Integration Guide

## Overview

The Hokusai data pipeline now supports webhooks for model registration notifications, replacing the previous Redis pub/sub system. This enables serverless platforms like Vercel to receive real-time notifications when models are registered and ready for deployment.

## Configuration

### Environment Variables

Configure the webhook system using these environment variables:

```bash
# Required
WEBHOOK_URL=https://your-endpoint.com/api/models/ready
WEBHOOK_SECRET=your_shared_secret_here

# Optional (with defaults)
WEBHOOK_TIMEOUT=30                                    # Request timeout in seconds
WEBHOOK_MAX_RETRIES=5                                 # Maximum retry attempts
WEBHOOK_RETRY_DELAY=2                                 # Initial retry delay (exponential backoff)
WEBHOOK_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5          # Failures before circuit opens
WEBHOOK_CIRCUIT_BREAKER_RECOVERY_TIME=60             # Recovery time in seconds

# Migration support
ENABLE_REDIS_FALLBACK=false                          # Enable dual publishing during migration
```

## Webhook Payload

When a model is registered and meets baseline requirements, the following JSON payload is sent:

```json
{
  "model_id": "model_abc123",
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
  "registered_version": "1",
  "timestamp": "2024-01-15T10:30:00Z",
  "token_symbol": "TOKEN_ABC",
  "baseline_metrics": {
    "accuracy": 0.85,
    "f1_score": 0.82
  },
  "metadata": {
    "model_name": "sentiment-analyzer",
    "mlflow_run_id": "run_xyz789",
    "contributor_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
    "experiment_name": "production-models",
    "tags": {
      "environment": "production",
      "model_type": "classification"
    }
  }
}
```

## Security

### HMAC Signature Verification

All webhook requests include an HMAC-SHA256 signature in the `X-Hokusai-Signature` header. Verify this signature to ensure the request is authentic:

```python
import hmac
import hashlib

def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify the HMAC signature of a webhook payload."""
    expected_signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)

# In your webhook handler
@app.post("/api/models/ready")
async def handle_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("X-Hokusai-Signature")
    
    if not verify_webhook_signature(payload, signature, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Process the webhook...
```

### Node.js Example

```javascript
const crypto = require('crypto');

function verifyWebhookSignature(payload, signature, secret) {
    const expectedSignature = crypto
        .createHmac('sha256', secret)
        .update(payload)
        .digest('hex');
    
    return crypto.timingSafeEqual(
        Buffer.from(signature),
        Buffer.from(expectedSignature)
    );
}

// In your webhook handler
app.post('/api/models/ready', (req, res) => {
    const signature = req.headers['x-hokusai-signature'];
    const payload = JSON.stringify(req.body);
    
    if (!verifyWebhookSignature(payload, signature, process.env.WEBHOOK_SECRET)) {
        return res.status(401).json({ error: 'Invalid signature' });
    }
    
    // Process the webhook...
});
```

## Idempotency

Each webhook payload includes an `idempotency_key` to prevent duplicate processing. Store this key and check for duplicates:

```python
processed_keys = set()  # In production, use a database or cache

@app.post("/api/models/ready")
async def handle_webhook(request: Request):
    data = await request.json()
    idempotency_key = data.get("idempotency_key")
    
    if idempotency_key in processed_keys:
        # Already processed, return success without reprocessing
        return {"status": "already_processed"}
    
    # Process the webhook
    process_model_registration(data)
    processed_keys.add(idempotency_key)
    
    return {"status": "success"}
```

## Reliability Features

### Retry Mechanism

The webhook publisher implements exponential backoff for failed requests:
- Initial retry after 2 seconds
- Subsequent retries: 4s, 8s, 16s, 32s
- Maximum 5 retry attempts by default

Your endpoint should return a 2xx status code to indicate success. Any other status code or timeout triggers a retry.

### Circuit Breaker

After 5 consecutive failures (configurable), the circuit breaker opens and stops sending requests for 60 seconds. This prevents overwhelming a failing endpoint.

### Timeout Handling

Requests timeout after 30 seconds by default. Ensure your endpoint responds within this time or adjust the `WEBHOOK_TIMEOUT` setting.

## Migration from Redis

### Phase 1: Dual Publishing (Current)

Enable both webhook and Redis publishing during migration:

```bash
WEBHOOK_URL=https://your-endpoint.com/api/models/ready
WEBHOOK_SECRET=your_secret
ENABLE_REDIS_FALLBACK=true
```

Both systems will receive notifications, allowing gradual migration.

### Phase 2: Webhook Only

Once webhook consumers are stable, disable Redis fallback:

```bash
ENABLE_REDIS_FALLBACK=false
```

### Phase 3: Redis Removal

After all consumers migrate, Redis configuration can be removed entirely.

## Testing Your Webhook

### Health Check

Test webhook connectivity:

```bash
curl -X POST https://your-endpoint.com/health \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

### Test Payload

Send a test model registration:

```python
import requests
import hmac
import hashlib
import json
from datetime import datetime
import uuid

def send_test_webhook(url: str, secret: str):
    payload = {
        "model_id": "test_model_001",
        "idempotency_key": str(uuid.uuid4()),
        "registered_version": "1",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "token_symbol": "TEST_TOKEN",
        "baseline_metrics": {
            "accuracy": 0.95
        },
        "metadata": {
            "model_name": "test-model",
            "test": True
        }
    }
    
    payload_bytes = json.dumps(payload).encode()
    signature = hmac.new(
        secret.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    
    response = requests.post(
        url,
        data=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Hokusai-Signature": signature
        }
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

# Test your endpoint
send_test_webhook(
    "https://your-endpoint.com/api/models/ready",
    "your_webhook_secret"
)
```

## Troubleshooting

### Common Issues

1. **401 Unauthorized**: Check HMAC signature verification and ensure secrets match
2. **Timeouts**: Increase `WEBHOOK_TIMEOUT` or optimize endpoint response time
3. **Circuit breaker open**: Check logs for repeated failures, fix endpoint issues
4. **Duplicate processing**: Implement idempotency key checking

### Monitoring

Monitor webhook delivery through CloudWatch metrics:
- `webhook_publish_success`: Successful deliveries
- `webhook_publish_failure`: Failed deliveries
- `webhook_retry_count`: Number of retries
- `webhook_circuit_breaker_state`: Circuit breaker status

### Logging

Enable debug logging for detailed webhook information:

```python
import logging
logging.getLogger("src.events.publishers.webhook_publisher").setLevel(logging.DEBUG)
```

## Support

For issues or questions:
- Check CloudWatch logs for detailed error messages
- Review this guide for configuration and implementation details
- Contact the Hokusai team for additional support