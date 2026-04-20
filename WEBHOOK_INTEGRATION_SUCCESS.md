# Webhook Integration Status

## Summary
Site notification is wired into the **packaged CLI** (`hokusai model register`). After a
successful MLflow registration the CLI POSTs a `model_registered` event to the Hokusai
site webhook at `https://hokus.ai/api/webhooks/model-registration` (or the URL in
`HOKUSAI_SITE_WEBHOOK_URL`). The webhook publisher used by `EnhancedModelRegistry` also
sends a correctly-shaped payload.

> **Note (HOK-1362):** An earlier version of this document incorrectly claimed that
> `register_tokenized_model()` automatically sent website notifications. It did not. That
> oversight is now fixed — see HOK-1362 for details.

## What Is Implemented

### 1. Code Changes (HOK-1362)
- ✅ `hokusai model register` CLI calls `_notify_site_of_registration()` after MLflow registration
- ✅ `WebhookPublisher._create_webhook_payload()` now includes `event_type: model_registered` so the site schema validation passes
- ✅ CLI accepts `--site-webhook-url` and `--webhook-secret` flags; both fall back to env vars

### 2. Configuration
- ✅ Added webhook configuration to `.env`:
  ```env
  WEBHOOK_URL=https://hokus.ai/api/webhooks/model-registration
  WEBHOOK_SECRET=test_webhook_secret_for_development
  ```

### 3. Payload Format
- ✅ Corrected webhook payload structure to match website expectations
- ✅ Uses `x-mlflow-signature` header for authentication
- ✅ Status must be lowercase ("registered" not "REGISTERED")
- ✅ Model data must be nested in a "model" object with "id" field

## How It Works Now

When someone calls:
```python
registry.register_tokenized_model(
    model_uri="runs:/abc123/model",
    model_name="My Model",
    token_id="LSCOR",  # Can be uppercase or lowercase
    metric_name="accuracy",
    baseline_value=0.92
)
```

The system automatically:
1. Registers the model in MLflow ✅
2. Normalizes token ID to uppercase (LSCOR) ✅
3. Sends webhook to https://hokus.ai/api/webhooks/model-registration ✅
4. Website validates signature and updates status to REGISTERED ✅

## Webhook Payload Format
```json
{
  "model": {
    "id": "LSCOR",
    "name": "Sales lead scoring model",
    "version": "5",
    "mlflow_run_id": "abc123",
    "metric_name": "accuracy",
    "baseline_value": 0.933,
    "token_id": "LSCOR",
    "status": "registered",
    "tags": {...}
  },
  "source": "mlflow",
  "event_type": "model_registered",
  "timestamp": "2025-08-21T15:04:51.563343"
}
```

## Security
- Webhook payload is signed with HMAC-SHA256
- Signature sent in `x-mlflow-signature` header
- Both sides use the same `WEBHOOK_SECRET` for validation

## Testing
Three test scripts are available:
1. `test_webhook_notification.py` - Basic webhook test
2. `test_final_webhook.py` - Complete integration test
3. `test_simple_webhook.py` - Minimal payload test

Run: `python test_final_webhook.py` to verify the integration.

## Success Response
```json
{
  "success": true,
  "message": "Webhook model_registered processed successfully for model Sales lead scoring model",
  "processed_at": "2025-08-21T15:04:51.835Z"
}
```

## Benefits
- ✅ Automatic status updates (no manual intervention)
- ✅ Consistent state between MLflow and website
- ✅ Secure webhook communication
- ✅ Case-insensitive token IDs for better UX
- ✅ Clear error messages for troubleshooting

## For Existing DRAFT Models
Models that were registered before this fix (like the original LSCOR with version 4) will remain in DRAFT status. To update them:
1. Re-register the model with a new version, OR
2. Manually update the status in the website database, OR
3. Use the test script to send a webhook for that specific model

## Next Steps
The integration is complete and working. New model registrations will automatically update to REGISTERED status on the website.
