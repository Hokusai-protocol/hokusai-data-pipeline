# MLFlow Artifact Storage 404 Fix Plan

**Date**: 2025-07-26  
**Issue**: MLFlow artifact endpoints returning HTML 404 errors instead of proper JSON responses  
**Impact**: Third-party users unable to upload/download model artifacts

## Issue Analysis

### Root Cause
The MLFlow proxy is not properly handling artifact endpoint routing. The issue occurs because:

1. **Path Translation Issue**: The proxy converts `api/2.0/mlflow/` to `ajax-api/2.0/mlflow/` for external MLFlow, but this conversion is NOT applied to artifact paths (`api/2.0/mlflow-artifacts/`)
2. **HTML vs JSON Response**: When artifact endpoints return 404, they return HTML error pages instead of JSON error responses
3. **Missing Route Handling**: The proxy doesn't have specific handling for artifact paths when using the ajax-api conversion

### Test Results
- ❌ `/api/mlflow/api/2.0/mlflow-artifacts/artifacts` → 404 HTML
- ✅ `/api/mlflow/ajax-api/2.0/mlflow-artifacts/artifacts` → 200 JSON
- ❌ Direct artifact paths return HTML 404s
- ✅ Regular MLFlow API endpoints work correctly

## Fix Implementation

### 1. Update MLFlow Proxy Route Handler

**File**: `src/api/routes/mlflow_proxy_improved.py`

```python
# Current problematic code (lines 44-53):
if path.startswith("api/2.0/mlflow/"):
    # For internal MLflow server, use standard API path
    if "registry.hokus.ai" in mlflow_base_url:
        # External MLflow uses ajax-api
        path = path.replace("api/2.0/mlflow/", "ajax-api/2.0/mlflow/")
        logger.info(f"Converted path for external MLflow: {original_path} -> {path}")
    else:
        # Internal MLflow uses standard api path
        logger.info(f"Using standard API path for internal MLflow: {path}")

# MISSING: Similar handling for artifact paths!
```

**Fix**: Add artifact path handling after the MLFlow path handling:

```python
# Handle artifact endpoints with proper path translation
if path.startswith("api/2.0/mlflow-artifacts/"):
    logger.info(f"Proxying artifact request: {path}")
    
    # Apply the same ajax-api conversion for external MLflow
    if "registry.hokus.ai" in mlflow_base_url:
        path = path.replace("api/2.0/mlflow-artifacts/", "ajax-api/2.0/mlflow-artifacts/")
        logger.info(f"Converted artifact path for external MLflow: {original_path} -> {path}")
    
    # Check if artifact serving is enabled
    if not os.getenv("MLFLOW_SERVE_ARTIFACTS", "true").lower() == "true":
        logger.warning("Artifact storage is disabled by configuration")
        raise HTTPException(
            status_code=503,
            detail={"error": "ARTIFACTS_DISABLED", "message": "Artifact storage is not configured. Please contact your administrator."}
        )
```

### 2. Ensure JSON Error Responses

Update the error handling to always return JSON for API endpoints:

```python
# In the proxy error handling section (around line 129-134):
if response.status_code >= 400:
    # Check if response is HTML error page
    if "text/html" in response.headers.get("Content-Type", ""):
        # Convert HTML 404 to JSON response
        if response.status_code == 404:
            json_error = {
                "error_code": "RESOURCE_NOT_FOUND",
                "message": f"The requested resource was not found: {original_path}"
            }
            return Response(
                content=json.dumps(json_error),
                status_code=404,
                headers={"Content-Type": "application/json"}
            )
```

### 3. Update Health Check to Test Artifacts

Add artifact endpoint testing to the health check:

```python
# In mlflow_detailed_health_check() add:
{
    "name": "artifacts_api", 
    "path": "/ajax-api/2.0/mlflow-artifacts/artifacts", 
    "method": "GET"
}
```

## Alternative Solution: Documentation Update

If the code cannot be updated immediately, update the documentation to guide users to use the correct endpoints:

### For `documentation/ml-platform/mlflow-integration.md`:

```markdown
## Artifact Storage

When working with MLFlow artifacts through the Hokusai API, use the following endpoints:

### Correct Artifact Endpoints
```python
# For artifact operations, use ajax-api path directly:
artifact_url = "https://registry.hokus.ai/api/mlflow/ajax-api/2.0/mlflow-artifacts/artifacts"

# NOT this (returns 404):
# artifact_url = "https://registry.hokus.ai/api/mlflow/api/2.0/mlflow-artifacts/artifacts"
```

### Working with MLFlow Client
The MLFlow client may attempt to use standard paths. Configure it to use the ajax-api endpoints:

```python
import mlflow
import os

# Set tracking URI
mlflow.set_tracking_uri("https://registry.hokus.ai/api/mlflow")

# For artifact operations, you may need to manually construct URLs
# or use the MLFlow REST API directly
```
```

## Testing Plan

1. **Unit Tests**: Add tests for artifact path translation in `test_mlflow_proxy_improved.py`
2. **Integration Tests**: Test artifact upload/download with both internal and external MLFlow
3. **E2E Tests**: Full model registration with artifact storage

## Deployment Steps

1. Update `mlflow_proxy_improved.py` with the fixes
2. Run unit tests to verify routing logic
3. Deploy to staging environment
4. Test artifact operations in staging
5. Deploy to production
6. Verify with third-party test case

## Immediate Workaround for Users

Until the fix is deployed, users can work around the issue by:

1. Using the ajax-api path directly for artifacts:
   ```
   https://registry.hokus.ai/api/mlflow/ajax-api/2.0/mlflow-artifacts/artifacts
   ```

2. Or configuring MLFlow client to handle redirects:
   ```python
   import mlflow
   from mlflow.tracking._tracking_service.utils import _get_store
   
   # Custom artifact handling may be required
   ```

## Summary

The issue is a simple path translation bug where artifact endpoints are not being converted from `api/2.0` to `ajax-api/2.0` for external MLFlow servers. The fix is straightforward and should resolve all artifact 404 errors while maintaining backward compatibility.