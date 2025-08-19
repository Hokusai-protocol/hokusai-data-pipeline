# Root Cause Analysis: Model Registration Failure

## Confirmed Root Cause

**The API service container has a Python syntax error that prevents it from starting, causing all API proxy endpoints to fail with 504 Gateway Timeout errors.**

## Technical Explanation

### The Bug
The deployed Docker image (tag: `08f0380d3e657ac3512c403fa3f7d4e09bff6d2e`) contains a syntax error in `/app/src/services/model_registry.py` at line 26:

```python
def __init__(self, tracking_uri: str = "http://10.0.1.88:5000"  # TEMPORARY: Direct IP until service discovery fixed) -> None:
```

This line has an unclosed parenthesis in the function parameter definition. The comment was incorrectly placed inside the parameter list without proper closure, causing a Python syntax error during module import.

### Why It Wasn't Caught Earlier

1. **No CI/CD validation**: The syntax error made it into the deployed image, suggesting the build process doesn't run basic Python syntax checking
2. **Incomplete testing**: The image was built and pushed without attempting to start the application
3. **Missing health checks in deployment**: ECS continuously tries to restart the failing container without alerting

### Current State

- **MLflow service**: ✅ Running and accessible at https://registry.hokus.ai/mlflow/
- **API service**: ❌ Cannot start due to syntax error
- **Result**: All `/api/*` endpoints return 504 Gateway Timeout as the ALB has no healthy targets

## Impact Assessment

### Direct Impact
- Complete failure of all API proxy endpoints (`/api/mlflow/*`, `/api/2.0/mlflow/*`)
- Model registration via API is impossible
- Health checks fail with timeouts
- Authentication proxy for MLflow is non-functional

### Cascade Effects
- Data science teams cannot register models programmatically
- CI/CD pipelines for model deployment are blocked
- The LSCOR model with 93.3% accuracy cannot be deployed
- Platform appears completely down despite MLflow being healthy

## Evidence

### Container Logs
```
File "/app/src/services/model_registry.py", line 26
    def __init__(self, tracking_uri: str = "http://10.0.1.88:5000"  # TEMPORARY: Direct IP until service discovery fixed) -> None:
                ^
SyntaxError: '(' was never closed
```

### ECS Service Status
- hokusai-mlflow-development: 1/1 running
- hokusai-api-development: 0/1 running (continuous restart loop)

### ALB Target Health
- MLflow targets: 1 healthy, 1 unhealthy
- API targets: 0 healthy (no running containers to register)

### Endpoint Testing
- https://registry.hokus.ai/mlflow/ → 200 OK (direct MLflow access works)
- https://registry.hokus.ai/api/mlflow/* → 504 (no API service to proxy)

## Related Code Sections

**File**: `src/services/model_registry.py`
**Line**: 26
**Issue**: Malformed parameter definition with unclosed parenthesis

The syntax error was introduced when attempting to add a temporary comment about using a direct IP address for MLflow service discovery. The comment was incorrectly placed within the function signature.

## Solution

The fix is straightforward - correct the syntax error by either:
1. Moving the comment outside the function signature
2. Properly closing the parenthesis before the comment
3. Using a different IP resolution strategy without inline comments

The current repository already has the correct code (line 26 shows proper syntax), but the fix needs to be deployed by:
1. Building a new Docker image
2. Pushing to ECR
3. Updating the ECS service to use the new image