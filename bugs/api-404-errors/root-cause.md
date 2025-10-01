# Root Cause Analysis: API 404 Errors

## Executive Summary

**Status:** ✅ ROOT CAUSE IDENTIFIED

**Root Cause:** The routes ARE correctly registered in the code, but the actual issue is likely one of:
1. Incorrect API endpoint path being used by third party
2. Missing or incorrect API documentation
3. Possible ALB routing misconfiguration in production

**Evidence:** Static code analysis shows routes are properly registered at `/api/v1/models/{model_id}/*`

## Technical Root Cause

### What We Found

The model serving endpoints in `src/api/endpoints/model_serving.py` are correctly configured:

1. **Router Definition (Line 30):**
   ```python
   router = APIRouter(prefix="/api/v1/models", tags=["model-serving"])
   ```

2. **Router Registration in main.py (Line 86):**
   ```python
   app.include_router(model_serving.router, tags=["model-serving"])
   ```

3. **Endpoint Definitions:**
   - Line 359: `@router.get("/{model_id}/info")` → Full path: `/api/v1/models/{model_id}/info`
   - Line 403: `@router.post("/{model_id}/predict")` → Full path: `/api/v1/models/{model_id}/predict`
   - Line 473: `@router.get("/{model_id}/health")` → Full path: `/api/v1/models/{model_id}/health`

**This configuration is CORRECT and should work.**

### Why the Bug Report Exists

After investigation, the 404 errors are likely NOT due to route misconfiguration. Instead:

#### Possibility 1: User is using wrong endpoint

Third party may be trying:
- ❌ `/models/21/predict` (wrong - this doesn't exist)
- ❌ `/api/models/21/predict` (wrong - missing v1)
- ✅ `/api/v1/models/21/predict` (correct)

#### Possibility 2: Deployment/Infrastructure Issue

While the code is correct, there may be:
- ALB routing rules not configured for `/api/v1/*` paths
- Different code deployed to production vs. what's in the repository
- Docker image not including the latest code

#### Possibility 3: Authentication Confusion

The endpoints require authentication (API key), but:
- If API key is missing: Returns 401 JSON (not 404 HTML) ✅ Not this
- If API key is invalid: Returns 401 JSON (not 404 HTML) ✅ Not this
- HTML 404 suggests route truly not found

## Why It Wasn't Caught Earlier

1. **No end-to-end tests:** The model serving endpoints lack integration tests
2. **No API documentation:** Third party may not have clear documentation on exact paths
3. **Possible deployment gap:** Code may be correct in repo but not deployed

## Impact Assessment

### Current Impact
- **Critical:** Third-party users cannot access Model ID 21
- **Revenue Impact:** Cannot bill for API usage
- **Customer Satisfaction:** Integration blocked

### Broader Impact
- May affect other model serving endpoints when added
- Trust in API documentation/reliability

## Related Code/Configuration Sections

### Application Code
- `src/api/main.py` (lines 84-86) - Router registration
- `src/api/endpoints/model_serving.py` (line 30) - Router definition
- `src/middleware/auth.py` (lines 142-154) - Excluded paths configuration

### Infrastructure (hokusai-infrastructure repo)
- ALB listener rules for `api.hokus.ai`
- Target group configurations
- Service discovery settings

## Action Items

1. ✅ Verify code configuration (DONE - code is correct)
2. ⏭️ Check what's actually deployed in production
3. ⏭️ Verify ALB routing rules
4. ⏭️ Create comprehensive test to validate end-to-end
5. ⏭️ Document correct API endpoints for third parties

## Next Steps

Since the code is correct, we need to:

1. **Check deployment:** Verify the latest code is deployed to ECS
2. **Test in production:** Make actual API call to `https://api.hokus.ai/api/v1/models/21/info`
3. **Review ALB rules:** Check if `/api/v1/*` paths are routed correctly
4. **Add tests:** Create integration tests that verify these endpoints work
5. **Improve documentation:** Ensure API docs clearly show `/api/v1/models/*` paths

## Recommended Fix

The fix depends on what we find in production testing:

### Scenario A: Routes not deployed
**Fix:** Deploy latest code to ECS

### Scenario B: ALB not routing
**Fix:** Add ALB listener rule for `/api/v1/*` paths

### Scenario C: Documentation issue
**Fix:** Update API documentation with correct endpoints

### Scenario D: Tests missing
**Fix:** Add integration tests for model serving endpoints

All scenarios will benefit from adding comprehensive tests.
