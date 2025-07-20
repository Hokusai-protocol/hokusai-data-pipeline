# Pull Request: Fix Routing Conflicts for MLflow API Proxy

## Problem
The ALB routing rule `/api*` at priority 100 was catching ALL paths starting with `/api`, including `/api/mlflow/*`. This prevented MLflow clients from using standard configuration and forced users to use a workaround path.

## Critical Discovery
During implementation, we discovered that `auth.hokus.ai` and `registry.hokus.ai` point to the SAME ALB. The `/api*` rule was essential for auth service functionality. Simply changing it would break authentication.

## Solution
1. **Added auth-specific routing rules** (Priority 80) to preserve auth service
2. **Added MLflow proxy rule** (Priority 90) for `/api/mlflow/*`
3. **Updated general API rule** (Priority 100) from `/api*` to specific paths
4. **Added `/api/mlflow` mount point** in FastAPI application

## Changes Made

### Infrastructure (Terraform)
- `infrastructure/terraform/routing-fix.tf` - New ALB routing rules
- `infrastructure/terraform/remove-old-rules.tf` - Instructions for cleanup

### Application Code
- `src/api/main.py` - Added `/api/mlflow` router mount point

### Documentation
- `docs/ROUTING.md` - Comprehensive routing documentation
- `docs/ROUTING_ANALYSIS.md` - Current state analysis
- `docs/ROUTING_SOLUTION.md` - Solution design
- `DEPLOYMENT_GUIDE.md` - Deployment instructions
- `DEPLOYMENT_STEPS.md` - Step-by-step guide
- `CRITICAL_ROUTING_DISCOVERY.md` - Auth service findings

### Testing
- `tests/test_routing.py` - Unit tests for routing
- `test_routing_behavior.py` - Live endpoint testing script

## Testing Performed
- ✅ Verified all API endpoints use `/api/v1/` prefix
- ✅ Discovered auth service dependency on `/api*` rule
- ✅ Added auth-specific rules to prevent breaking auth
- ✅ Created comprehensive test suite
- ⚠️ Requires live environment testing post-deployment

## Deployment Notes
1. **Deploy new rules FIRST** - Do not remove old rules initially
2. **Test auth service** - Critical to verify it still works
3. **Monitor carefully** - Watch for any 404 errors
4. **Remove old rules** - Only after full verification

## Risk Assessment
- **With auth rules added**: LOW risk
- **Without auth rules**: HIGH risk (would break authentication)

## Backward Compatibility
- ✅ Existing `/mlflow/*` paths continue to work
- ✅ Auth service functionality preserved
- ✅ All existing API endpoints continue to work

## Result
After deployment, MLflow clients can use standard configuration:
```python
os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/api/mlflow"
os.environ["MLFLOW_TRACKING_TOKEN"] = "your_api_key"
```
EOF < /dev/null