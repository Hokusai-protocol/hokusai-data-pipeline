# Model Registration Webhook Integration Fix

## Problem Summary
When users register models using `registry.register_tokenized_model()`, the model is successfully registered in MLflow but the Hokusai website is not notified, leaving the token status as DRAFT instead of updating to REGISTERED.

## Root Cause
The SDK's `register_tokenized_model()` method was not sending webhook notifications to the Hokusai website after successful registration.

## Solution Implemented

### 1. Updated ModelRegistry Class
Modified `/hokusai-ml-platform/src/hokusai/core/registry.py`:
- Added `_notify_registration()` method to send webhook notifications
- Modified `register_tokenized_model()` to call `_notify_registration()` after successful registration
- Webhook sends notification to `https://hokus.ai/api/mlflow/registered`

### 2. Webhook Configuration
Added to `.env`:
```env
WEBHOOK_URL=https://hokus.ai/api/mlflow/registered
WEBHOOK_SECRET=test_webhook_secret_for_development
```

### 3. Webhook Payload Format
The webhook sends the following payload when a model is registered:
```json
{
  "event_type": "model_registered",
  "timestamp": "2025-08-21T14:42:23.646003",
  "token_id": "LSCOR",
  "model_name": "Sales lead scoring model",
  "model_version": "4",
  "mlflow_run_id": "abc123",
  "metric_name": "accuracy",
  "baseline_value": 0.933,
  "status": "REGISTERED",
  "tags": {...}
}
```

### 4. Security
- Webhook payload is signed with HMAC-SHA256
- Signature sent in `X-Hokusai-Signature` header
- Format: `sha256=<signature>`

## Current Status

### ✅ Completed
1. Updated `register_tokenized_model()` to send webhooks
2. Added webhook configuration to environment
3. Tested webhook endpoint connectivity
4. Token IDs now accept both uppercase and lowercase (normalized to uppercase)

### ⚠️ Issue Found
The Hokusai website endpoint (`https://hokus.ai/api/mlflow/registered`) returns:
```json
{"success":false,"error":"Webhook secret not configured"}
```

This indicates the website needs to be configured with the same webhook secret for signature verification.

## Required Actions for Website Team

### 1. Configure Webhook Secret
The website endpoint needs to be configured with the webhook secret:
```
WEBHOOK_SECRET=test_webhook_secret_for_development
```

### 2. Update Webhook Handler
The webhook handler at `/api/mlflow/registered` should:
1. Verify the HMAC signature from `X-Hokusai-Signature` header
2. Parse the payload to extract `token_id`
3. Update the token status from DRAFT to REGISTERED in the database
4. Return a success response (200 OK)

### 3. Signature Verification Example
```javascript
const crypto = require('crypto');

function verifyWebhookSignature(payload, signature, secret) {
  const expectedSignature = 'sha256=' + crypto
    .createHmac('sha256', secret)
    .update(payload, 'utf8')
    .digest('hex');
  
  return signature === expectedSignature;
}
```

## How It Works Now

1. **User registers model:**
   ```python
   registry.register_tokenized_model(
       model_uri="runs:/abc123/model",
       model_name="My Model",
       token_id="LSCOR",
       metric_name="accuracy",
       baseline_value=0.92
   )
   ```

2. **SDK automatically:**
   - Registers model in MLflow ✅
   - Normalizes token ID to uppercase ✅
   - Sends webhook to website ✅
   - Website updates status to REGISTERED ❌ (needs configuration)

## Testing

Use the provided test script:
```bash
python test_webhook_notification.py
```

This will send a test webhook to verify the integration.

## Migration for Existing DRAFT Models

For models already registered but stuck in DRAFT status (like LSCOR), the website team can:
1. Manually update their status in the database, OR
2. Re-trigger the webhook notification for those specific models

## Benefits
- Automatic status updates (no manual intervention needed)
- Consistent state between MLflow and website
- Secure webhook communication with HMAC signatures
- Case-insensitive token IDs for better UX