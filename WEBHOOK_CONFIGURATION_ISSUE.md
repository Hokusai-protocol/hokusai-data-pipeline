# Webhook Configuration Issue

## Current Status
The webhook integration is implemented but there's a **webhook secret mismatch** between the data pipeline and the website.

## What's Working
✅ Model registration in MLflow works  
✅ Webhook is sent to `https://hokus.ai/api/mlflow/registered`  
✅ Website endpoint exists and validates signatures  
✅ Correct header name: `x-mlflow-signature`  

## The Problem
❌ **Signature validation fails** - Status 401: "Invalid signature"

The website is configured with a different `WEBHOOK_SECRET` than what we're using in the data pipeline.

## Configuration

### Data Pipeline Side (.env)
```env
WEBHOOK_URL=https://hokus.ai/api/mlflow/registered
WEBHOOK_SECRET=test_webhook_secret_for_development
```

### Website Side
The website needs to have the **exact same** webhook secret:
```env
WEBHOOK_SECRET=test_webhook_secret_for_development
```

## How Signatures Work

1. **Data Pipeline generates signature:**
```python
signature = hmac.new(
    webhook_secret.encode('utf-8'),
    payload_json.encode('utf-8'),
    hashlib.sha256
).hexdigest()
```

2. **Sends with header:**
```
x-mlflow-signature: sha256=<signature>
```

3. **Website validates:**
```javascript
const expectedSignature = 'sha256=' + crypto
  .createHmac('sha256', WEBHOOK_SECRET)
  .update(payloadString, 'utf8')
  .digest('hex');

if (signature !== expectedSignature) {
  return res.status(401).json({ error: 'Invalid signature' });
}
```

## Resolution Options

### Option 1: Update Website Secret (Recommended)
The website team should update their environment variable to:
```
WEBHOOK_SECRET=test_webhook_secret_for_development
```

### Option 2: Share the Actual Secret
If the website is using a different secret for security reasons:
1. Website team shares their actual `WEBHOOK_SECRET`
2. We update our `.env` file with the correct secret
3. Both sides use the same secret

### Option 3: Disable Signature Validation (Not Recommended)
Temporarily disable signature validation on the website for testing, but this is insecure for production.

## Testing the Fix

Once the secrets match, test with:
```bash
python test_webhook_notification.py
```

Expected successful response:
```json
{
  "success": true,
  "message": "Model registration webhook received",
  "token_id": "LSCOR",
  "status": "REGISTERED"
}
```

## What Happens When It Works

1. User calls `register_tokenized_model()`
2. Model registers in MLflow
3. Webhook sent to website with signature
4. Website validates signature ✅
5. Website updates token status from DRAFT to REGISTERED
6. Token shows as REGISTERED on https://hokus.ai/explore-models/

## Current Webhook Payload Format

```json
{
  "event_type": "model_registered",
  "timestamp": "2025-08-21T14:53:19.671490",
  "token_id": "LSCOR",
  "model_name": "Sales lead scoring model",
  "model_version": "4",
  "mlflow_run_id": "abc123",
  "metric_name": "accuracy",
  "baseline_value": 0.933,
  "status": "REGISTERED",
  "tags": {
    "author": "GTM Backend Team",
    "version": "1.0.0",
    "dataset": "Kaggle B2B Sales"
  }
}
```

## Action Required
**Website team**: Please verify and update your `WEBHOOK_SECRET` environment variable to match ours, or share the correct secret with us.