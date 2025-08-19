# Test Results: Model Registration Failure

## Testing Started: 2025-08-19

---

## Hypothesis 1: API Proxy Not Forwarding Auth Headers Correctly

### Test 1.1: Check proxy implementation for auth header handling

**File examined**: `/src/api/routes/mlflow_proxy.py`

**Critical Finding**: ✅ **CONFIRMED - Root cause found!**

Lines 64-71 in mlflow_proxy.py explicitly remove authentication headers:
```python
# Remove sensitive headers that shouldn't be forwarded
headers_to_remove = [
    "authorization",  # Don't forward Hokusai API key to MLflow
    "x-api-key",      # Don't forward Hokusai API key to MLflow
    "host",           # We'll use MLflow's host
    "content-length", # Will be recalculated
]
for header in headers_to_remove:
    headers.pop(header, None)
```

**Analysis**:
1. The proxy receives the API key from the client (verified by auth middleware)
2. The auth middleware validates the key and adds user context to request.state
3. The proxy then **strips the authorization headers** before forwarding to MLflow
4. MLflow receives the request without any authentication, causing "API key required" error

**Why this causes the bug**:
- MLflow needs authentication headers to authorize requests
- The proxy incorrectly assumes MLflow doesn't need auth (comment says "Don't forward Hokusai API key to MLflow")
- This design assumes MLflow is running without authentication, but it clearly requires auth

**Status**: Hypothesis 1 CONFIRMED ✅
