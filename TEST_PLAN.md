# Routing Fix Test Plan

## What We Need to Test

### 1. Local Testing (Before Deployment)

**API Changes:**
- [x] Added `/api/mlflow` mount point to FastAPI app
- [ ] Verify the app starts without errors
- [ ] Test that both `/mlflow/*` and `/api/mlflow/*` routes are registered

**Test locally:**
```bash
# Start the API locally
python -m uvicorn src.api.main:app --reload

# Test endpoints
curl http://localhost:8000/mlflow/health/mlflow
curl http://localhost:8000/api/mlflow/health/mlflow
```

### 2. Terraform Changes (Dry Run)

**Infrastructure Changes:**
- [ ] New ALB rule for `/api/mlflow/*` at priority 90
- [ ] Updated ALB rule for `/api/v1/*` at priority 100
- [ ] Verify no conflicts with existing rules

**Test with Terraform plan:**
```bash
cd infrastructure/terraform
terraform plan
# Review the plan - should show:
# - 2 new listener rules to be created
# - No resources to be destroyed
```

### 3. Integration Testing (After Deployment)

**Routing Behavior:**
- [ ] `/api/mlflow/*` routes to API service (not 404)
- [ ] `/api/v1/dspy/*` still works
- [ ] `/mlflow/*` still works (backward compatibility)
- [ ] `/models/*` endpoints still work

**MLflow Proxy:**
- [ ] Path translation works (`api/2.0/mlflow` → `ajax-api/2.0/mlflow`)
- [ ] Authentication headers are properly forwarded
- [ ] MLflow client can connect via proxy

### 4. End-to-End Testing

**Model Registration:**
- [ ] Run `test_real_registration.py` with API key
- [ ] Verify model can be registered
- [ ] Check model appears in MLflow UI

## Current State vs. Fixed State

### Current State (BROKEN)
- `/api/mlflow/*` → 404 (caught by `/api*` rule, goes to wrong service)
- MLflow clients must use workaround: `MLFLOW_TRACKING_URI=https://registry.hokus.ai/mlflow`

### Fixed State (EXPECTED)
- `/api/mlflow/*` → 200 (routed correctly to API service with proxy)
- MLflow clients can use standard: `MLFLOW_TRACKING_URI=https://registry.hokus.ai/api/mlflow`

## Risk Assessment

### Low Risk
- Adding new mount point to FastAPI (backward compatible)
- Adding new ALB rules (doesn't affect existing rules)

### Medium Risk
- Changing ALB rule from `/api*` to `/api/v1/*` could affect unknown endpoints
- Need to verify all API endpoints are under `/api/v1/`

### Mitigation
- Deploy new rules first without removing old ones
- Test thoroughly before removing old rules
- Keep rollback plan ready

## Test Scripts to Run

1. **Before deployment:**
   ```bash
   # Test current state (should fail)
   python test_routing_behavior.py
   ```

2. **After deployment:**
   ```bash
   # Test fixed state (should pass)
   python test_routing_behavior.py
   
   # Test model registration
   export HOKUSAI_API_KEY="your_key"
   python test_real_registration.py
   ```

## What Could Go Wrong

1. **Unknown API endpoints** - If there are `/api/*` endpoints not under `/api/v1/`, they would break
2. **MLflow path mismatch** - If MLflow expects different paths than we're translating
3. **Authentication issues** - If the proxy doesn't properly forward auth headers
4. **Performance impact** - Additional hop through proxy could add latency

## Recommendation

Given that we haven't tested these changes in a live environment, I recommend:

1. **First**: Set up a local test environment to verify the API changes work
2. **Second**: Deploy to a staging/dev environment if available
3. **Third**: Deploy new rules to production WITHOUT removing old rules
4. **Fourth**: Test thoroughly
5. **Finally**: Remove old rules only after confirming everything works