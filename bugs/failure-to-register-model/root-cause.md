# Root Cause Analysis: Model Registration Failure

## Confirmed Root Cause

**Issue**: The MLflow proxy service is explicitly stripping authentication headers before forwarding requests to MLflow, causing all authenticated operations to fail.

## Technical Explanation

### The Bug Mechanism

1. **Client sends request** with API key in Authorization header:
   ```
   Authorization: Bearer hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN
   ```

2. **Auth middleware validates** the API key successfully:
   - Validates with auth service
   - Adds user context to `request.state`
   - Allows request to proceed

3. **MLflow proxy strips auth headers** (THE BUG):
   ```python
   # From mlflow_proxy_improved.py lines 91-98
   headers_to_remove = [
       "authorization",  # Don't forward Hokusai API key to MLflow
       "x-api-key",      # Don't forward Hokusai API key to MLflow
       "host",
       "content-length",
   ]
   for header in headers_to_remove:
       headers.pop(header, None)
   ```

4. **MLflow receives request without auth**:
   - No Authorization header present
   - MLflow returns "API key required" error
   - Registration fails

### Why It Wasn't Caught Earlier

1. **Incorrect assumption**: The code comments indicate developers assumed MLflow shouldn't receive Hokusai API keys ("Don't forward Hokusai API key to MLflow")

2. **Architecture misunderstanding**: The design assumed MLflow runs without authentication internally, but the current deployment requires auth

3. **Testing gap**: Previous tests likely used a different MLflow configuration or direct access without the proxy

4. **Recent changes**: The webhook migration work may have changed the MLflow deployment configuration to require authentication

## Impact Assessment

### Affected Operations
- ALL MLflow API operations through the proxy
- Model registration completely blocked
- Experiment creation fails
- Run logging fails
- Model versioning fails
- Artifact storage operations fail

### Affected Users
- All third-party API users
- GTM Backend Team
- Any team using the hokusai-ml-platform package
- Internal services relying on model registration

### Business Impact
- Critical platform functionality non-operational
- Blocks model deployment pipeline
- Prevents platform adoption
- Development teams blocked

## Related Code Sections

### Files Affected
1. `/src/api/routes/mlflow_proxy.py` - Lines 64-71
2. `/src/api/routes/mlflow_proxy_improved.py` - Lines 91-98
3. Both files have identical bug

### Configuration
- Main app uses `mlflow_proxy_improved` as the active router
- Mounted at `/mlflow` prefix
- Also needs to handle `/api/mlflow` prefix (currently missing)

## Why Previous Fixes Failed

Looking at the git history and completed tickets:
- PR #60 mentioned "Hokusai auth headers are removed before proxying to MLflow" - this was intentional but incorrect
- Multiple attempts to fix routing and authentication
- The core issue of stripping headers was never identified

## Solution Requirements

1. **Forward authentication headers to MLflow**
2. **Maintain security** - validate API keys before forwarding
3. **Handle both Hokusai and MLflow auth** formats if needed
4. **Test with actual MLflow authentication** enabled

## Additional Findings

### Missing Route Configuration
The proxy is mounted at `/mlflow` but clients are calling `/api/mlflow`:
- Client calls: `https://registry.hokus.ai/api/mlflow/...`
- Proxy mounted at: `/mlflow`
- This causes 404 errors for `/api/mlflow` paths

### Environment Configuration
- MLflow is configured at internal IP: `http://10.0.3.219:5000`
- External URL uses: `https://registry.hokus.ai`
- Path translation logic exists but headers are still stripped