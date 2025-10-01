# Bug Investigation Plan: API ID 21 Connection 405 Error

## 1. Bug Summary

**Issue:** Third-party client receiving HTTP 405 (Method Not Allowed) when attempting to connect to Model ID 21 API endpoint

**Severity:** High - Blocks third-party integration and API usage

**Impact:**
- Third-party unable to use Model ID 21 for predictions
- Potential loss of API revenue
- Negative developer experience
- May indicate documentation or API routing misconfiguration

**When it occurs:** When third-party makes POST request to model prediction endpoint

**Who is affected:** External API consumers trying to use Model ID 21 (LSCOR - Sales Lead Scoring v2)

## 2. Reproduction Steps

Based on the Linear issue description:

1. Client attempts to connect to `https://hokus.ai/api/v1/models/21/predict`
2. Client sends POST request with proper authentication (API key)
3. Request reaches the API (no 401 error, authentication working)
4. API returns HTTP 405 (Method Not Allowed)

**Success rate:** 100% (consistently failing)

**Variations:**
- Authentication is working (no 401 error)
- Connection succeeds (no network issues)
- HTTP method appears to be the issue

## 3. Affected Components

### API Services
- **predict.py** (`src/api/routes/predict.py`): Handles prediction endpoints for deployed models
  - Route: `/api/v1/models/{deployed_model_id}/predict` (expects UUID)
  - Requires UUID for deployed_model_id parameter

- **model_serving.py** (`src/api/endpoints/model_serving.py`): Alternative model serving endpoint
  - Route: `/api/v1/models/{model_id}/predict` (expects string)
  - Handles Model ID 21 specifically
  - Uses HuggingFace storage

- **main.py** (`src/api/main.py`): FastAPI application routing
  - Line 86: Registers model_serving.router with prefix handling

### Route Conflicts
- **Potential issue:** Two different routers handling similar paths with different parameter types
  - predict.py expects UUID
  - model_serving.py expects string (model_id "21")

### Database Tables
- `deployed_models` table (referenced in predict.py)
- Model configuration (likely in MLflow registry)

### Third-Party Dependencies
- HuggingFace Hub (for model storage)
- Auth service (for API key validation)

### Frontend/Documentation
- Website: https://hokus.ai/explore-models/21
- API documentation (potentially outdated or incorrect)

## 4. Initial Observations

### From Linear Issue
- Client is successfully connecting (not a network issue)
- Authentication working (API key being accepted - no 401)
- Getting 405 instead of 404 suggests endpoint exists but wrong method or path
- Client attempted: `https://hokus.ai/api/v1/models/21/predict`

### From Codebase Analysis

**predict.py (Line 85-96):**
```python
@router.post(
    "/models/{deployed_model_id}/predict",
    ...
)
async def predict(
    deployed_model_id: UUID,  # <-- Expects UUID, not string "21"
    ...
)
```

**model_serving.py (Line 25):**
```python
router = APIRouter(prefix="/api/v1/models", tags=["model-serving"])
```

**main.py (Line 86):**
```python
app.include_router(model_serving.router, tags=["model-serving"])
```

### Key Findings
1. **predict.py expects UUID** but client is sending string "21"
2. **Two different routing systems** may be conflicting
3. **Route registration order** matters in FastAPI
4. **Documentation** (MODEL_21_VERIFICATION_REPORT.md) shows correct endpoint structure but may not match actual implementation

## 5. Data Analysis Required

### Logs to examine
- `/ecs/hokusai-api-development` CloudWatch logs
- Filter for:
  - "405" errors
  - "models/21/predict" requests
  - "Method Not Allowed"
  - Timestamp around when third-party attempted connection

### API Testing
- Test with curl/Postman against:
  - `POST /api/v1/models/21/predict` (string ID)
  - `POST /api/v1/models/{uuid}/predict` (with actual UUID)
  - Check which routes are actually registered

### Database Queries
- Check if Model 21 exists in deployed_models table
- Get the actual UUID for Model 21's deployment
- Query: `SELECT id, model_id, status FROM deployed_models WHERE model_id = '21'`

### Route Inspection
- Use FastAPI `/docs` endpoint to see registered routes
- Check route priority and matching order

## 6. Investigation Strategy

### Priority 1: Confirm Route Registration Issue (30 min)
1. Check FastAPI application startup logs for route registration
2. Access `/docs` endpoint to see all registered routes
3. Verify which endpoint is actually handling `/api/v1/models/21/predict`
4. Test both endpoints with curl

### Priority 2: Understand Routing Conflict (30 min)
1. Review main.py router inclusion order (line 84-86)
2. Check if predict.py routes are being registered
3. Determine if model_serving.py routes are overriding predict.py
4. Understand UUID vs string parameter type handling

### Priority 3: Check Model 21 Deployment Status (15 min)
1. Query database for Model 21 deployment record
2. Verify if Model 21 has a UUID in deployed_models table
3. Check if model_serving.py is the correct endpoint for Model 21

### Priority 4: Review Documentation vs Implementation (15 min)
1. Compare MODEL_21_VERIFICATION_REPORT.md with actual code
2. Check if documentation is outdated
3. Verify expected vs actual API behavior

### Tools and Techniques
- CloudWatch Logs Insights
- FastAPI /docs (OpenAPI) endpoint
- curl for API testing
- Database queries via psql or Python
- Code tracing for route registration

### Key Questions to Answer
1. Which router is actually handling `/api/v1/models/21/predict`?
2. Is there a UUID for Model 21 in deployed_models table?
3. Are both routers (predict.py and model_serving.py) registered?
4. What is the route matching priority in FastAPI?
5. Is the documentation wrong or is the implementation incomplete?

### Success Criteria
- Identified which endpoint should handle Model 21 requests
- Understood why 405 error is occurring
- Determined correct UUID or route structure
- Found the specific code causing the routing failure

## 7. Risk Assessment

### Current Impact
- **High:** Third-party integration blocked
- API revenue potential loss
- Reputation damage with external developers

### Potential for Escalation
- Medium: Other models may have similar issues
- Could affect all deployed model endpoints if systematic problem
- May require breaking changes to API

### Security Implications
- Low: No security vulnerability identified
- Authentication working correctly
- Issue is routing/configuration only

### Data Integrity Concerns
- Low: No data corruption risk
- Issue is request routing, not data handling

## 8. Timeline

### When Bug First Appeared
- Unknown - need to check logs
- Likely since Model 21 deployment
- May have existed since multiple routers were added

### Correlation with Deployments
- Check recent deployments to API service
- Review git history for:
  - When model_serving.py was added (check git log)
  - When predict.py was modified (check git log)
  - Recent changes to main.py router registration

### Frequency of Occurrence
- 100% of requests to this endpoint
- Systematic issue, not intermittent

### Patterns in Timing
- No time-based pattern expected
- Affects all requests regardless of timing

## Next Steps

1. Run CloudWatch log analysis to confirm 405 errors
2. Test API endpoints directly with curl
3. Check database for Model 21 deployment UUID
4. Review route registration order in main.py
5. Generate hypotheses based on findings
