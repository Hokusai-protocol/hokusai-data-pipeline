# Bug Investigation Test Results

## Test Session: Hypothesis 1 - Router Registration Conflict

### Test 1: Examine Route Registration in Code

**Method:** Static code analysis of router registration

**Results:**

#### main.py Analysis (lines 84-86):
```python
app.include_router(models.router, prefix="/models", tags=["models"])
app.include_router(dspy.router, tags=["dspy"])
app.include_router(model_serving.router, tags=["model-serving"])
```

**Finding:** The `model_serving.router` is included WITHOUT a prefix parameter.

####model_serving.py Analysis (line 30):
```python
router = APIRouter(prefix="/api/v1/models", tags=["model-serving"])
```

**Finding:** The router ALREADY HAS a prefix `/api/v1/models`.

#### Expected Behavior:
When `model_serving.router` is included in main.py:
- Since no prefix is specified in `include_router()`, FastAPI should use the router's own prefix
- Routes should register at: `/api/v1/models/{model_id}/info`, `/api/v1/models/{model_id}/predict`, etc.

#### Potential Conflict Analysis:

Let's trace what happens with a request to `/api/v1/models/21/predict`:

1. **models.router** (prefix: `/models`):
   - Has route `@router.get("/{model_name}/{version}")` → full path: `/models/{model_name}/{version}`
   - Does NOT match `/api/v1/models/21/predict` ✅ No conflict here

2. **model_serving.router** (prefix: `/api/v1/models`):
   - Has route `@router.post("/{model_id}/predict")` → full path: `/api/v1/models/{model_id}/predict`
   - SHOULD match `/api/v1/models/21/predict` ✅ This should work!

**Conclusion from static analysis:** Routes SHOULD be working. No obvious conflict detected.

### Test 2: Check for Import/Registration Issues

**Method:** Verify all routers are properly imported

#### Imports in main.py:
```python
from src.api.endpoints import model_serving  # Line 12
from src.api.routes import dspy, health, health_mlflow, models  # Line 13
```

**Finding:** ✅ `model_serving` is imported correctly

#### Router registration:
```python
app.include_router(model_serving.router, tags=["model-serving"])  # Line 86
```

**Finding:** ✅ Router is included in the app

**Conclusion:** Import and registration appear correct.

### Test 3: Check for Path Pattern Issues

**Method:** Analyze route decorators in model_serving.py

#### Routes defined:
1. Line 359: `@router.get("/{model_id}/info")` → `/api/v1/models/{model_id}/info`
2. Line 403: `@router.post("/{model_id}/predict")` → `/api/v1/models/{model_id}/predict`
3. Line 473: `@router.get("/{model_id}/health")` → `/api/v1/models/{model_id}/health`

**Finding:** All routes use path parameters correctly, no obvious pattern issues.

### Test 4: Dynamic Testing Required

**Status:** ⏭️ PENDING - Requires starting the API server

**Plan:**
1. Start API locally: `python -m uvicorn src.api.main:app --reload`
2. Check `/docs` endpoint to see registered routes
3. Test with curl to verify route matching
4. Check for any startup errors in logs

**Expected if Hypothesis 1 is TRUE:**
- Routes will NOT appear in `/docs`
- Curl requests will return 404
- May see errors in startup logs

**Expected if Hypothesis 1 is FALSE:**
- Routes WILL appear in `/docs`
- 404 may be due to authentication or other issues
- Need to test with valid API key

---

## Status

**Hypothesis 1 Status:** ⚠️ INCONCLUSIVE - Static analysis suggests routes should work
**Next Action:** Need to run dynamic tests (start server, check /docs, test with curl)
**Alternative Theory:** Issue may be authentication-related (Hypothesis 2) or deployment-specific

---

## Additional Findings

### Observation: All model_serving routes require authentication

From model_serving.py:
- Line 362: `auth: Dict[str, Any] = Depends(require_auth)`
- Line 407: `auth: Dict[str, Any] = Depends(require_auth)`
- Line 476: `auth: Dict[str, Any] = Depends(require_auth)`

**Implication:** If authentication is failing, could produce 404-like errors if middleware rejects before route matching.

**But:** Auth middleware should return 401, not 404. Unless...

### Observation: Middleware dispatch order matters

From main.py lines 48-51:
```python
app.add_middleware(APIKeyAuthMiddleware)
app.add_middleware(RateLimitMiddleware)
```

From auth.py line 326:
```python
if any(request.url.path.startswith(path) for path in self.excluded_paths):
    response = await call_next(request)
    return response
```

**Finding:** Auth middleware checks if path starts with excluded paths. `/api/v1/models/*` is NOT excluded, so auth is required.

**Potential Issue:** If auth middleware is rejecting requests somehow before they reach the router, could cause unexpected behavior.

**Next Test:** Disable auth middleware and test again.
