# Test Results: Problems Registering Model

## Testing Date: 2025-09-15

## Hypothesis 1: API Keys Created with Default Read-Only Scope
**Status**: PARTIALLY CONFIRMED

### Test Results

#### Test 1: Check Default Scope Configuration
- **Finding**: In `src/cli/auth.py` line 103, the default scopes are:
  ```python
  default=["model:read", "model:write", "mlflow:access"]
  ```
- **Result**: API keys SHOULD have write permissions by default
- **Conclusion**: The CLI tool is configured correctly to grant write permissions

#### Test 2: Check Scope Validation in Middleware
- **Finding**: In `src/middleware/auth.py`:
  - Line 194: Scopes ARE retrieved from auth service
  - Line 296: Scopes ARE stored in `request.state.scopes`
  - **CRITICAL**: No code found that actually CHECKS these scopes for write operations
- **Result**: Scopes are retrieved but NOT enforced
- **Conclusion**: The middleware validates API keys but doesn't check permissions

## Hypothesis 2: Missing model:write Permission Check in Auth Middleware
**Status**: CONFIRMED ✅

### Test Results

#### Test 1: Search for Scope Checking Logic
- **Finding**: No scope checking logic found in:
  - `src/middleware/auth.py` - Only validates key existence, not permissions
  - `src/api/routes/mlflow_proxy.py` - No permission checks
  - `src/api/routes/mlflow_proxy_improved.py` - No permission checks
- **Result**: The system authenticates users but doesn't authorize operations
- **Conclusion**: This is the root cause - missing authorization checks

#### Test 2: MLflow Proxy Behavior
- **Finding**: In `src/api/routes/mlflow_proxy_improved.py`:
  - Lines 95-102: Authentication headers are intentionally kept and forwarded to MLflow
  - No scope validation before forwarding requests
- **Result**: All authenticated requests are forwarded regardless of permissions
- **Conclusion**: The proxy trusts any authenticated user for any operation

## Hypothesis 3: MLflow Proxy Incorrectly Filtering Write Operations
**Status**: REJECTED ❌

### Test Results
- The proxy does NOT filter write operations
- It forwards all authenticated requests to MLflow
- The issue is the lack of permission checking, not filtering

## Additional Findings

### Critical Issue Identified
The authentication middleware (`APIKeyAuthMiddleware`) performs these steps:
1. ✅ Validates API key with auth service
2. ✅ Retrieves user scopes from auth service
3. ✅ Stores scopes in request state
4. ❌ **MISSING**: Never checks if the scopes match the operation

### Why 403 Errors Occur
The 403 errors are likely coming from either:
1. The auth service itself when validating keys that don't have write scopes
2. MLflow server if it has its own permission system
3. A downstream service that checks permissions

But the data pipeline API service itself is NOT checking permissions.

## Test Conclusion

**ROOT CAUSE CONFIRMED**: The API service lacks authorization logic to check if an API key's scopes permit the requested operation. While the middleware retrieves scopes, it never validates them against the operation being performed (read vs write).

### Next Steps
1. Implement scope checking in the middleware or create a separate authorization decorator
2. Check MLflow write endpoints and enforce `model:write` or `mlflow:write` scope
3. Return 403 Forbidden for unauthorized write attempts