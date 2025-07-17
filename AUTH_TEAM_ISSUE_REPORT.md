# Authentication Service Issue Report

**Date**: 2025-07-17  
**Reporter**: Hokusai Data Pipeline Team  
**Severity**: 🔴 **CRITICAL** - Blocking all third-party integrations

## Executive Summary

The Hokusai authentication service is rejecting all API keys with "Invalid or expired API key" errors, preventing third-party model registration. Our investigation revealed a critical mismatch between how the API proxy sends authentication data and what the auth service expects.

## The Problem

### Current Behavior
- **API Proxy**: Sends API key in `Authorization: Bearer <key>` header (after recent fix)
- **Auth Service**: Expects API key in JSON request body as `{"api_key": "<key>"}`
- **Result**: All requests fail with 401 "Invalid or expired API key"

### Evidence

1. **Auth Service OpenAPI Specification**:
```json
"APIKeyValidation": {
    "properties": {
        "api_key": {
            "type": "string",
            "title": "Api Key"
        },
        "service_id": {
            "type": "string"
        }
    }
}
```

2. **Test Results**:
```
# API key in Authorization header → FAILS
POST https://auth.hokus.ai/api/v1/keys/validate
Headers: {"Authorization": "Bearer hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL"}
Body: {"service_id": "ml-platform"}
Response: 401 {"detail": "Invalid or expired API key"}

# API key in JSON body → DIFFERENT ERROR
POST https://auth.hokus.ai/api/v1/keys/validate
Body: {"api_key": "hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL", "service_id": "ml-platform"}
Response: 401 {"detail": "API key required"}
```

## Root Cause Analysis

### 1. API Contract Mismatch
The auth service validation endpoint (`/api/v1/keys/validate`) expects the API key in the request body, not in headers. This is confirmed by:
- OpenAPI specification showing `api_key` as a body parameter
- Different error messages when key is in body vs header
- The "API key required" error when sending in body suggests the auth middleware itself expects Bearer tokens

### 2. Possible Double Authentication
The auth service appears to have its own authentication layer that:
- Requires Bearer token authentication to access endpoints
- Then validates a different API key passed in the request body
- This creates a chicken-and-egg problem

### 3. Service Configuration Issue
When testing with `service_id: "ml-platform"`, all requests fail. Possible issues:
- The service ID "ml-platform" may not be registered
- The API key may not have permissions for this service
- The key validation logic may have additional requirements

## Detailed Test Results

### MLflow Discovery
- **MLflow is running**: `https://registry.hokus.ai/mlflow/` returns MLflow UI
- **Correct API path**: `/mlflow/ajax-api/2.0/mlflow/*` (not standard `/api/2.0/mlflow/*`)
- **No auth on MLflow**: Direct MLflow access returns 400 "Invalid max_results" (not auth error)

### Auth Patterns Tested
All of these failed with the same API key:
1. Bearer token in Authorization header
2. Raw API key in Authorization header  
3. API key in X-API-Key header
4. API key in X-Hokusai-API-Key header
5. API key in URL parameter
6. API key in JSON body

### Error Patterns
- `"API key required"` - No authentication provided or wrong format
- `"Invalid or expired API key"` - Key was recognized but validation failed

## Recommendations

### Option 1: Update Auth Service (Recommended)
Modify the auth service to accept API keys in the Authorization header:
```python
# Current expectation
body = {"api_key": "key", "service_id": "ml-platform"}

# Should also accept
headers = {"Authorization": "Bearer key"}
body = {"service_id": "ml-platform"}
```

### Option 2: Revert API Proxy Changes
Change the API proxy back to sending keys in the request body:
```python
# Revert to original behavior
body = {
    "api_key": api_key,
    "service_id": "ml-platform",
    "client_ip": client_ip
}
```

### Option 3: Dual Support
Support both patterns during transition:
1. Try Authorization header first
2. Fall back to body parameter if header fails

## Immediate Actions Needed

1. **Verify API Key Status**
   - Confirm `hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL` is valid
   - Check if key has permissions for "ml-platform" service

2. **Check Service Registration**
   - Verify "ml-platform" is a registered service_id
   - List all valid service_ids for debugging

3. **Review Auth Service Code**
   - Understand why "API key required" error occurs with body parameter
   - Check if there's middleware expecting Bearer tokens

## Test Scripts Provided

We've created comprehensive test scripts to help debug:
- `investigate_mlflow.py` - Tests all endpoint combinations
- `test_auth_endpoints.py` - Maps auth service API surface
- `test_auth_service.py` - Tests validation patterns
- `test_real_registration.py` - End-to-end registration test

## Critical Impact

This issue is blocking:
- ❌ All third-party model registrations
- ❌ MLflow integration through API proxy
- ❌ Production deployment of model registry
- ❌ Customer onboarding and adoption

## Contact

For questions or clarification:
- Test logs: `mlflow_investigation.log`, `auth_endpoints_test.log`
- Test API key: `hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL`
- Affected service: https://registry.hokus.ai/api/mlflow

Please prioritize this issue as it's blocking all third-party integrations with the Hokusai platform.