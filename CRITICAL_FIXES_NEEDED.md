# Critical Fixes Needed for Third-Party Model Registration

## Summary

Third-party model registration is currently broken due to two critical issues that need immediate fixes:

1. **Authentication Middleware Bug**: The middleware sends API keys incorrectly to the auth service
2. **MLflow Backend Not Configured**: The MLflow proxy returns 404 because the backend is not accessible

## Issue 1: Authentication Middleware Bug ❌

### Problem
The authentication middleware sends the API key in the JSON body, but the auth service expects it in the Authorization header.

### Current Code (BROKEN)
```python
# src/middleware/auth.py line 129-136
response = await client.post(
    f"{self.auth_service_url}/api/v1/keys/validate",
    json={
        "api_key": api_key,  # ❌ WRONG: Sent in body
        "client_ip": client_ip,
        "service_id": "ml-platform"
    }
)
```

### Fixed Code (REQUIRED)
```python
# Send API key in Authorization header
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# Only send service_id and client_ip in body
body = {
    "service_id": "ml-platform"
}
if client_ip:
    body["client_ip"] = client_ip

response = await client.post(
    f"{self.auth_service_url}/api/v1/keys/validate",
    headers=headers,
    json=body
)
```

### Impact
- ALL API requests fail with "Invalid or expired API key"
- No third party can authenticate
- The provided valid API key is rejected

## Issue 2: MLflow Backend Not Configured ❌

### Problem
The MLflow proxy returns 404 for all endpoints because:
1. `MLFLOW_SERVER_URL` environment variable is not set
2. Defaults to `http://localhost:5000` which doesn't exist in production
3. No MLflow backend service is running or accessible

### Required Configuration
```bash
# Set in production environment
MLFLOW_SERVER_URL=http://mlflow-server:5000  # Or actual MLflow URL
```

### Verification
```bash
# This should return a valid response, not 404
curl https://registry.hokus.ai/mlflow/api/2.0/mlflow/experiments/search
```

## Deployment Steps

### 1. Fix Authentication Middleware
```bash
# Apply the patch
cd /path/to/hokusai-data-pipeline
git apply auth_middleware_fix.patch

# Or manually edit src/middleware/auth.py
# Update the validate_with_auth_service method as shown above
```

### 2. Configure MLflow Backend
```bash
# Option A: Set environment variable for API service
export MLFLOW_SERVER_URL="http://actual-mlflow-server:5000"

# Option B: Update docker-compose or k8s configs
# Add MLFLOW_SERVER_URL to environment variables
```

### 3. Ensure MLflow is Running
```bash
# Check if MLflow service is running
docker ps | grep mlflow

# If not, start it
docker compose up -d mlflow
```

### 4. Redeploy API Service
```bash
# Rebuild and deploy with fixes
docker build -t hokusai-api .
docker compose up -d api

# Or use your deployment method (ECS, k8s, etc.)
```

## Testing After Fixes

### 1. Test Authentication
```bash
# Should return user info, not "Invalid API key"
curl -X POST https://auth.hokus.ai/api/v1/keys/validate \
  -H "Authorization: Bearer hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL" \
  -H "Content-Type: application/json" \
  -d '{"service_id": "ml-platform"}'
```

### 2. Test MLflow Proxy
```bash
# Should return experiments, not 404
curl -H "Authorization: Bearer hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL" \
     https://registry.hokus.ai/mlflow/api/2.0/mlflow/experiments/search
```

### 3. Test Full Registration
```bash
export HOKUSAI_API_KEY="hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL"
python test_real_registration.py
```

## Root Cause

The issues stem from:
1. **Mismatched API Contract**: The middleware was written for a different auth service API
2. **Missing Infrastructure**: MLflow backend not deployed/configured
3. **No Integration Testing**: These issues would have been caught with proper end-to-end tests

## Prevention

1. **API Contract Tests**: Add tests that verify external service APIs
2. **Environment Validation**: Check required services on startup
3. **Integration Tests**: Test the full flow with real services
4. **Documentation**: Document all required environment variables

## Urgency

These fixes are **CRITICAL** and block all third-party integrations. Both issues must be fixed for the system to work.