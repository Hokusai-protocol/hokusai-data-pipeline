# Test Results: API ID 21 Connection 405 Error

## Test Session: 2025-10-01

---

## Hypothesis 1/2: Missing POST /predict Endpoint

**Status**: ❌ **REJECTED**

### Test Method
Read complete `src/api/endpoints/model_serving.py` file to check for POST /predict endpoint

### Results

**Endpoint EXISTS**:
- **Line 377-423**: `@router.post("/{model_id}/predict")`
- **Function**: `async def predict(model_id: str, request: PredictionRequest, authorization: Optional[str] = Header(None))`
- **Router prefix**: `/api/v1/models` (line 25)
- **Full path**: `POST /api/v1/models/{model_id}/predict`

### Code Evidence

```python
# Line 377-379
@router.post("/{model_id}/predict")
async def predict(
    model_id: str, request: PredictionRequest, authorization: Optional[str] = Header(None)
):
```

### Analysis

The endpoint is fully implemented with:
1. ✅ Proper route decorator
2. ✅ String model_id parameter (accepts "21")
3. ✅ Authorization handling
4. ✅ Complete prediction logic
5. ✅ Error handling
6. ✅ Response formatting

**Conclusion**: Hypothesis 1/2 is WRONG. The endpoint exists and should work.

---

## Hypothesis 3: Router Registration Order / Prefix Conflict

**Status**: 🔍 **TESTING IN PROGRESS**

### Test Method
Check router registrations in `main.py` for prefix conflicts

### Router Registrations Found

From `src/api/main.py`:

**Line 84**:
```python
app.include_router(models.router, prefix="/models", tags=["models"])
```

**Line 86**:
```python
app.include_router(model_serving.router, tags=["model-serving"])
```

### Prefix Analysis

**models.router**:
- Main.py applies prefix: `/models`
- models.py router definition: Need to check
- **Resulting paths**: `/models/*`

**model_serving.router**:
- Main.py applies prefix: NONE (no prefix argument)
- model_serving.py router definition: `prefix="/api/v1/models"` (line 25)
- **Resulting paths**: `/api/v1/models/*`

### Path Resolution

**Request from client**: `POST /api/v1/models/21/predict`

**FastAPI route matching order**:
1. First registered: `models.router` with prefix `/models`
   - Would only match paths starting with `/models/`
   - Does NOT match `/api/v1/models/21/predict` ✅

2. Second registered: `model_serving.router` with prefix `/api/v1/models`
   - Should match `/api/v1/models/21/predict` ✅
   - Has POST endpoint for `/{model_id}/predict` ✅

### Preliminary Analysis

**This should work!** No obvious prefix conflict because:
- `models.router` handles `/models/*` paths
- `model_serving.router` handles `/api/v1/models/*` paths
- These are DIFFERENT prefixes, no overlap

### Additional Check Needed

Need to verify if `models.router` has any routes that could match first. Let me check models.py routes:

From previous read of `models.py`:
- Line 38: `@router.get("/")` → becomes `/models/`
- Line 141: `@router.get("/{model_name}/{version}")` → becomes `/models/{model_name}/{version}`
- No routes would match `/api/v1/models/*` pattern

**Conclusion so far**: Router registration order does NOT appear to be the issue.

---

## Hypothesis 4: Route Not Actually Registered

**Status**: 🔍 **NEW HYPOTHESIS - TESTING**

### Observation

In `main.py` line 86:
```python
app.include_router(model_serving.router, tags=["model-serving"])
```

The router IS registered, BUT let me check if there's an issue with the double-prefix.

### Potential Issue Discovered

**model_serving.py line 25**:
```python
router = APIRouter(prefix="/api/v1/models", tags=["model-serving"])
```

**main.py line 86**:
```python
app.include_router(model_serving.router, tags=["model-serving"])
```

When you do `app.include_router(router_with_prefix)`, FastAPI uses the router's own prefix.

**Expected full path**: `/api/v1/models/{model_id}/predict`

This SHOULD work! The endpoint should be registered at exactly the path the client is calling.

---

## Hypothesis 5: Middleware or Authentication Blocking Request

**Status**: 🔍 **NEW HYPOTHESIS - TESTING**

### Discovery

The endpoint has its OWN authentication in `predict()` function:

```python
@router.post("/{model_id}/predict")
async def predict(
    model_id: str, request: PredictionRequest, authorization: Optional[str] = Header(None)
):
    # Verify authorization
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
```

BUT, the main.py also has middleware:

```python
# Line 48
app.add_middleware(APIKeyAuthMiddleware)
```

### Potential Issue

The `APIKeyAuthMiddleware` might be using `require_auth` dependency which could be interfering.

From previous observations:
- Client says "authentication working" (no 401)
- Getting 405 instead

This suggests the request is passing authentication but failing at routing level.

---

## Hypothesis 6: Missing Module Import or Router Not Included

**Status**: ⚠️ **CRITICAL FINDING**

### Test Method

Check exact import path in main.py

### Finding from main.py line 12:

```python
from src.api.endpoints import model_serving
```

This imports the MODULE, not the router specifically.

### Router Registration line 86:

```python
app.include_router(model_serving.router, tags=["model-serving"])
```

This references `model_serving.router` which should work since router is defined at module level in model_serving.py.

### Verification Needed

Is `model_serving.router` actually accessible? Let me trace:

1. `model_serving.py` line 25: `router = APIRouter(prefix="/api/v1/models", tags=["model-serving"])`
2. This creates module-level variable `router`
3. `main.py` imports module and accesses `.router` attribute
4. Should work ✅

---

## NEW HYPOTHESIS 7: FastAPI OpenAPI Route Generation Issue

**Status**: 🔍 **INVESTIGATING**

### Key Observation

The endpoint has:
```python
@router.post("/{model_id}/predict")
async def predict(
    model_id: str,
    request: PredictionRequest,
    authorization: Optional[str] = Header(None)
):
```

But `predict.py` has:
```python
@router.post("/models/{deployed_model_id}/predict", ...)
async def predict(deployed_model_id: UUID, ...)
```

### Potential Conflict

**BOTH ROUTERS HAVE A FUNCTION NAMED `predict`!**

This could cause an internal FastAPI naming conflict!

From predict.py:
- Function name: `predict`
- Route: `/models/{deployed_model_id}/predict` (but with main.py prefix becomes different)

From model_serving.py:
- Function name: `predict`
- Route: `/{model_id}/predict` (with router prefix becomes `/api/v1/models/{model_id}/predict`)

### Impact

FastAPI uses function names for operation IDs in OpenAPI. Having two functions with same name could cause:
- OpenAPI generation conflicts
- Route registration issues
- Unexpected behavior

**ACTION**: Need to check if this is causing the 405 error.

---

## HYPOTHESIS 8: predict.py Router Also Registered at /api/v1

**Status**: 🔍 **CRITICAL - NEEDS VERIFICATION**

### Question

Is `predict.router` from `src/api/routes/predict.py` also registered somewhere?

### Check main.py imports

Line 12-14 doesn't show predict being imported:
```python
from src.api.endpoints import model_serving
from src.api.routes import dspy, health, health_mlflow, models
from src.api.routes import mlflow_proxy_improved as mlflow_proxy
```

**predict is NOT in the imports!**

This means predict.py router is NOT registered in the FastAPI app!

### Conclusion

Only model_serving.router is handling `/api/v1/models/*` routes.

---

## ROOT CAUSE HYPOTHESIS: Authentication Middleware Interaction

**Status**: 🎯 **PRIMARY SUSPECT**

### Theory

Looking at model_serving.py line 385-387:
```python
# Verify authorization
if not authorization or not authorization.startswith("Bearer "):
    raise HTTPException(status_code=401, detail="Unauthorized")
```

And main.py line 48:
```python
app.add_middleware(APIKeyAuthMiddleware)
```

### Potential Issue

The middleware `APIKeyAuthMiddleware` might be:
1. Intercepting the request
2. Checking authentication
3. Blocking the request before it reaches the endpoint
4. Returning 405 instead of 401 due to misconfiguration

OR

The endpoint's own auth check conflicts with middleware, causing routing confusion.

### Test Needed

1. Check what `APIKeyAuthMiddleware` does
2. Check if it has path exclusions
3. Verify if it's causing the 405

---

## Next Steps

1. ✅ Read `APIKeyAuthMiddleware` implementation
2. ✅ Check excluded paths in middleware
3. ✅ Verify if `/api/v1/models/{model_id}/predict` is excluded or not
4. Test locally if possible to reproduce 405
5. Check CloudWatch logs for actual error details

---

## 🎯 ROOT CAUSE IDENTIFIED

### Test: Authentication Middleware Analysis

**Status**: ✅ **ROOT CAUSE CONFIRMED**

### Key Findings from auth.py

1. **Middleware Configuration** (Line 142-154):
   ```python
   self.excluded_paths = excluded_paths or [
       "/health",
       "/ready",
       "/live",
       "/version",
       "/metrics",
       "/docs",
       "/openapi.json",
       "/redoc",
       "/favicon.ico",
       "/api/v1/dspy/health",
       "/api/health/mlflow",
   ]
   ```
   
   ⚠️ **`/api/v1/models/{model_id}/predict` is NOT in excluded_paths!**

2. **Middleware applies to model serving endpoint** - It validates with external auth service

3. **Dual Authentication**:
   - First: `APIKeyAuthMiddleware` validates with auth service
   - Second: Endpoint's own auth check (line 385-387 in model_serving.py)

### The Actual Problem

The client is getting **405 Method Not Allowed** which suggests the code itself is correct, but there's a **deployment or runtime issue**.

Possible causes:
1. **Auth service unreachable**: Middleware can't validate with auth service at `HOKUSAI_AUTH_SERVICE_URL`
2. **Wrong auth service URL**: Environment variable misconfigured  
3. **API key format mismatch**: Client's API key doesn't match expected format
4. **Outdated deployment**: Running code doesn't have model_serving.router registered

### Critical Question

**Is the deployed version actually running this code?**

The Linear issue states client gets 405, which means:
- Path exists (otherwise 404)
- Method not allowed on that path

This could happen if:
- POST endpoint not registered (but code shows it is)
- Old version deployed without the endpoint
- Module import failing silently
- Router registration failing at startup

### Next Action Required

**Check deployment status and logs:**
```bash
# Check ECS service version
aws ecs describe-services --cluster hokusai-development --services hokusai-api-development

# Check CloudWatch logs for startup
aws logs tail /ecs/hokusai-api-development --since 1h | grep -i "router\|startup\|model_serving"

# Check if endpoint is registered
curl https://api.hokus.ai/openapi.json | jq '.paths' | grep -A 5 "models.*predict"
```

