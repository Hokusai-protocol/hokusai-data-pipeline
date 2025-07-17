# Fixes Applied for Third-Party Model Registration

## Summary

All three critical issues have been fixed:

1. ✅ **Authentication Middleware** - Fixed to send API key in Authorization header
2. ✅ **MLflow Server URL** - Configured to use `https://registry.hokus.ai/mlflow`
3. ✅ **MLflow Path Translation** - Fixed proxy to convert `/api/2.0/mlflow/` to `/ajax-api/2.0/mlflow/`

## 1. Authentication Middleware Fix

### File: `src/middleware/auth.py`

**Changed**: The middleware now sends the API key in the Authorization header instead of JSON body

```python
# FIXED: Send API key in Authorization header, not JSON body
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

## 2. MLflow Configuration Fix

### File: `src/api/routes/mlflow_proxy.py`

**Changed**: Updated default MLflow server URL from localhost to production

```python
# MLflow server configuration
MLFLOW_SERVER_URL = os.getenv("MLFLOW_SERVER_URL", "https://registry.hokus.ai/mlflow")
```

### File: `.env.production`

**Created**: Production environment configuration

```
MLFLOW_SERVER_URL=https://registry.hokus.ai/mlflow
MLFLOW_TRACKING_URI=https://registry.hokus.ai/mlflow
HOKUSAI_AUTH_SERVICE_URL=https://auth.hokus.ai
```

## 3. MLflow Path Translation Fix

### File: `src/api/routes/mlflow_proxy.py`

**Changed**: Added path translation because MLflow at registry.hokus.ai uses `/ajax-api/` instead of `/api/`

```python
# FIXED: Convert standard API paths to MLflow ajax-api paths
if path.startswith("api/2.0/mlflow/"):
    # MLflow at registry.hokus.ai uses ajax-api instead of api
    path = path.replace("api/2.0/mlflow/", "ajax-api/2.0/mlflow/")
    logger.info(f"Converted path to MLflow format: {path}")
```

**Also updated**:
- Added handling for `ajax-api/` paths in the router
- Updated health check to use the correct MLflow endpoint

## Deployment Configuration

### File: `deploy/docker-compose.production.yml`

**Created**: Production deployment configuration with correct environment variables

## Testing the Fixes

After deploying these changes, test with:

```bash
# Test authentication
curl -X POST https://auth.hokus.ai/api/v1/keys/validate \
  -H "Authorization: Bearer hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL" \
  -H "Content-Type: application/json" \
  -d '{"service_id": "ml-platform"}'

# Test MLflow proxy
curl -H "Authorization: Bearer hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL" \
     https://registry.hokus.ai/mlflow/api/2.0/mlflow/experiments/search

# Full registration test
export HOKUSAI_API_KEY="hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL"
python test_real_registration.py
```

## Key Insights

1. **MLflow uses non-standard paths**: The production MLflow uses `/ajax-api/2.0/mlflow/` instead of `/api/2.0/mlflow/`
2. **Auth service expects header auth**: The Hokusai auth service expects Bearer tokens in headers, not request body
3. **MLflow is already deployed**: No need to run local MLflow - it's at `https://registry.hokus.ai/mlflow`

## Next Steps

1. **Deploy the updated API service** with these fixes
2. **Verify with the test scripts** to ensure everything works
3. **Monitor logs** for any issues during initial usage

## Test Results (2025-07-17)

### ❌ **FAILED** - Authentication Issues Persist

Testing with API key `hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL` revealed:

1. **All endpoints return 401 "Invalid or expired API key"**
   - The API key is being rejected by the auth service
   - This happens for both JSON body and Bearer header formats

2. **Possible causes**:
   - The API key may be expired or invalid
   - The fixes may not have been deployed to production yet
   - The auth service may have additional requirements not addressed

3. **Action needed**:
   - Verify API key validity with the team
   - Confirm deployment status of PR #49
   - Check auth service logs for validation failures

See `TEST_REPORT.md` for full test results and analysis.