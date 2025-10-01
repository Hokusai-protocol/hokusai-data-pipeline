# Root Cause: API ID 21 Connection 405 Error

## Executive Summary

**Root Cause**: The `/api/v1/models/{model_id}/predict` endpoint is correctly implemented in code but has **dual authentication layers** that create complexity and potential failure points. The most likely issue is that the external auth service validation is failing or the third-party's API key is not being properly validated.

**Severity**: High - Blocks third-party integration

**Impact**: Third-party clients cannot use Model ID 21 for predictions via the API

**Fix Complexity**: Medium - Requires either:
1. Adding endpoint to middleware excluded paths (simple)
2. Removing redundant auth layer (better design)
3. Debugging auth service integration (if that's failing)

---

## Technical Root Cause

### Problem: Conflicting Authentication Architecture

The `/api/v1/models/{model_id}/predict` endpoint has **two authentication layers**:

#### Layer 1: Global Middleware (src/middleware/auth.py)

```python
# main.py line 48
app.add_middleware(APIKeyAuthMiddleware)

# auth.py line 142-154
self.excluded_paths = excluded_paths or [
    "/health",
    "/ready",
    ...
    # NOTE: /api/v1/models/{model_id}/predict is NOT in this list!
]
```

This middleware:
- Intercepts ALL requests except excluded paths
- Validates API keys with external auth service at `HOKUSAI_AUTH_SERVICE_URL`
- Caches validation results in Redis
- Returns 401 if validation fails
- **Applies to the model serving endpoint** (not excluded)

#### Layer 2: Endpoint-Specific Auth (src/api/endpoints/model_serving.py)

```python
# model_serving.py line 377-387
@router.post("/{model_id}/predict")
async def predict(
    model_id: str,
    request: PredictionRequest,
    authorization: Optional[str] = Header(None)
):
    # Verify authorization
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Extract API key
    api_key = authorization.replace("Bearer ", "")

    # Simple validation
    if not api_key.startswith("hk_"):
        raise HTTPException(status_code=401, detail="Invalid API key")
```

This creates a **second** authentication check that:
- Requires Authorization header with Bearer token
- Checks if API key starts with "hk_"
- Does NOT validate with auth service

---

## Why This Causes 405 Error

The **405 Method Not Allowed** error is unusual and suggests the issue is NOT a simple 401 authentication failure.

### Most Likely Scenario

1. **Middleware validates request** with auth service
2. **Auth service validation fails** or returns unexpected response
3. **Middleware allows request through anyway** (due to error handling)
4. **Request reaches endpoint**
5. **Endpoint's auth check examines Authorization header**
6. **Something about the request format causes routing failure**

### Alternative Scenarios

#### Scenario A: Auth Service Unreachable

```python
# auth.py line 205-210
except httpx.TimeoutException:
    logger.error("Auth service request timed out")
    return ValidationResult(is_valid=False, error="Authentication service timeout")
except Exception as e:
    logger.error(f"Auth service error: {str(e)}")
    return ValidationResult(is_valid=False, error="Authentication service unavailable")
```

If auth service is down/unreachable:
- Middleware returns 401, not 405
- But the client says "authentication is working"
- This suggests middleware IS passing the request through

#### Scenario B: Outdated Deployment

The deployed version might not have the model_serving.router registered:

```python
# main.py line 86
app.include_router(model_serving.router, tags=["model-serving"])
```

If this line doesn't exist in deployed version:
- Endpoint wouldn't exist
- Would return 404, not 405

#### Scenario C: Router Registration Failure

The router registration might fail silently at startup due to:
- Import error in model_serving.py
- Dependency missing (sklearn, huggingface_hub, etc.)
- Router prefix conflict
- FastAPI version incompatibility

If registration fails:
- No POST endpoint at `/api/v1/models/21/predict`
- FastAPI might match a different route that only supports GET
- Returns 405 for POST requests

#### Scenario D: ALB Routing Configuration

The Application Load Balancer might:
- Have a path-based rule that blocks POST to this path
- Route this path to a different target (wrong service)
- Apply HTTP method restrictions

---

## Why It Wasn't Caught Earlier

### Missing Monitoring
- No health check for model serving endpoints
- No automated API integration tests
- No alerts for 405 errors

### Dual Auth Complexity
- Two authentication systems make it hard to debug
- Not clear which layer is failing
- Auth middleware logs might not be detailed enough

### Documentation vs Implementation Gap
- MODEL_21_VERIFICATION_REPORT.md documents the endpoint
- But doesn't mention dual authentication layers
- Doesn't document auth service dependency
- Client might be following incomplete documentation

### Development vs Production Parity
- Local development might bypass auth middleware
- Auth service might not be running locally
- Works in development, fails in production

---

## Impact Assessment

### Current Impact
- **High**: Third-party integration completely blocked
- Cannot use Model 21 for predictions
- Potential revenue loss
- Developer experience severely impacted

### Potential for Escalation
- **Medium**: Other model serving endpoints have same dual auth
- If this is systemic, affects all model serving
- Could impact multiple customers

### User Experience
- Error message (405) is not descriptive
- Doesn't indicate whether it's auth, routing, or other issue
- Client has no way to debug further

---

## Related Code Sections

### Key Files
1. **src/api/main.py** (Line 48, 86)
   - Middleware registration
   - Router registration

2. **src/middleware/auth.py** (Line 58-458)
   - APIKeyAuthMiddleware implementation
   - Excluded paths configuration
   - Auth service integration

3. **src/api/endpoints/model_serving.py** (Line 377-423)
   - Predict endpoint implementation
   - Endpoint-specific authentication
   - Model serving logic

4. **src/api/utils/config.py**
   - Configuration settings
   - Auth service URL configuration

### Environment Variables

Required for proper operation:
```bash
# Auth service
HOKUSAI_AUTH_SERVICE_URL=https://auth.hokus.ai
AUTH_SERVICE_TIMEOUT=5.0

# Redis cache
REDIS_URL=redis://localhost:6379/0
# OR
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_AUTH_TOKEN=<optional>

# HuggingFace (for model loading)
HUGGINGFACE_API_KEY=<token>
```

---

## Recommended Fix

### Option 1: Add Endpoint to Excluded Paths (Quick Fix)

**Pros**:
- Simple, fast fix
- Removes middleware validation
- Endpoint handles its own auth

**Cons**:
- Loses centralized auth logging
- Loses auth service integration benefits
- Creates inconsistency in auth patterns

**Implementation**:
```python
# src/middleware/auth.py line 142-154
self.excluded_paths = excluded_paths or [
    "/health",
    "/ready",
    ...
    "/api/v1/models",  # Add this to exclude all model serving endpoints
]
```

### Option 2: Remove Endpoint-Specific Auth (Recommended)

**Pros**:
- Single authentication layer
- Consistent with other endpoints
- Better observability
- Proper auth service integration

**Cons**:
- Requires more changes
- Need to test auth service integration
- Might need to adjust endpoint logic

**Implementation**:
```python
# src/api/endpoints/model_serving.py
@router.post("/{model_id}/predict")
async def predict(
    model_id: str,
    request: PredictionRequest,
    auth: dict[str, Any] = Depends(require_auth),  # Use standard auth dependency
):
    # Remove manual auth check
    # Middleware already validated

    # Log the user making the request
    logger.info(f"Prediction request for model {model_id} from user {auth['user_id']}")

    # Continue with prediction logic
    ...
```

### Option 3: Debug Auth Service Integration (Investigation)

**If the issue is auth service failure**, we need to:
1. Check auth service logs
2. Verify auth service is reachable from API service
3. Test API key validation endpoint
4. Check network policies / security groups
5. Review auth service URL configuration

---

## Prevention Measures

### 1. Standardize Authentication

**Action**: Use single auth pattern across all endpoints
- Either middleware-based OR endpoint-based, not both
- Document the chosen pattern clearly
- Create auth utility functions for consistency

### 2. Improve Error Messages

**Action**: Return descriptive errors
```python
if not authorization:
    raise HTTPException(
        status_code=401,
        detail={
            "error": "UNAUTHORIZED",
            "message": "Authorization header required",
            "hint": "Include 'Authorization: Bearer hk_your_api_key_here' header"
        }
    )
```

### 3. Add Health Checks

**Action**: Create endpoint health check
```python
@router.get("/{model_id}/health")
async def check_model_health(model_id: str):
    return {
        "model_id": model_id,
        "status": "healthy",
        "auth_required": True,
        "endpoint": f"/api/v1/models/{model_id}/predict"
    }
```

### 4. Integration Tests

**Action**: Add automated API tests
- Test with valid API key
- Test with invalid API key
- Test with missing API key
- Test actual prediction flow
- Run in CI/CD pipeline

### 5. Monitoring & Alerts

**Action**: Set up CloudWatch alarms
- Alert on 40x errors
- Alert on auth service failures
- Alert on model serving errors
- Track auth success/failure rates

### 6. Documentation Updates

**Action**: Update API documentation
- Document auth requirements clearly
- Provide working code examples
- Include troubleshooting guide
- Document all endpoints and auth patterns

---

## Next Steps

See `fix-tasks.md` for detailed implementation tasks.

## Conclusion

The root cause is a **dual authentication architecture** that adds complexity and potential failure points. The endpoint is correctly implemented but the authentication flow needs to be simplified and debugged.

**Primary recommendation**: Remove endpoint-specific auth and rely solely on the middleware-based auth for consistency and better observability.

**Secondary recommendation**: If keeping dual auth, add comprehensive logging and error messages to help debug auth failures.

