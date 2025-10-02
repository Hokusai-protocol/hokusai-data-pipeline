# Bug Investigation: API 404 Errors for Model ID 21

## Bug Summary

**Issue:** Third-party users receiving 404 errors when calling API endpoints for Model ID 21, with HTML responses instead of JSON API responses.

**When it occurs:** All API calls to model serving endpoints

**Who/what is affected:** External API users trying to use Model ID 21 (Sales Lead Scoring Model)

**Business Impact:** High - blocking third-party integration, preventing revenue generation from API usage

**Severity:** P1 - Complete API failure for model serving endpoints

## Reproduction Steps

1. User makes API call to any of these endpoints:
   - GET `/api/v1/models/21/info` - Model information
   - POST `/api/v1/models/21/predict` - Run prediction
   - GET `/api/v1/models/21/health` - Health check

2. Expected: JSON response with model data
3. Actual: 404 error with HTML response (likely FastAPI default 404 page)

**Required environment/configuration:**
- Valid Hokusai API key
- Request to `https://api.hokus.ai`
- Model ID 21 endpoints

**Success rate of reproduction:** 100%

**Variations in behavior:** All model serving endpoints affected

## Affected Components

### Services/Modules
- `src/api/main.py` - FastAPI application and router registration
- `src/api/endpoints/model_serving.py` - Model serving endpoints
- `src/api/routes/models.py` - Model registry endpoints
- ALB routing rules in `hokusai-infrastructure`

### API Endpoints Touched
- `/api/v1/models/{model_id}/info`
- `/api/v1/models/{model_id}/predict`
- `/api/v1/models/{model_id}/health`

### Potential Route Conflicts
1. **model_serving.py** (line 30): Router prefix = `/api/v1/models`
2. **main.py** (line 84): Models router mounted at `/models`
3. **main.py** (line 86): Model serving router mounted with NO prefix override

## Initial Observations

### Code Analysis

**In main.py (lines 84-86):**
```python
app.include_router(models.router, prefix="/models", tags=["models"])
app.include_router(dspy.router, tags=["dspy"])
app.include_router(model_serving.router, tags=["model-serving"])  # Model 21 serving endpoint
```

**In model_serving.py (line 30):**
```python
router = APIRouter(prefix="/api/v1/models", tags=["model-serving"])
```

**Identified Issue:**
The model_serving router already has prefix `/api/v1/models` but is being included in main.py WITHOUT specifying a prefix, meaning it will use its own prefix. This creates the route `/api/v1/models/{model_id}/predict`.

However, there's a CONFLICT with the models.router which is mounted at `/models` prefix (line 84) and has its own routes like:
- `/models/{model_name}/{version}` (line 141 in models.py)

**The problem:** When a request comes to `/api/v1/models/21/predict`:
1. FastAPI first checks routers in the order they were registered
2. The `models.router` (mounted at `/models`) doesn't match `/api/v1/models/*`
3. The `model_serving.router` SHOULD match but may not be registered correctly
4. Result: 404 error

### Error Messages/Stack Traces
- HTML 404 response (FastAPI default page)
- No JSON error response
- Indicates route is not matched at all

### Recent Changes
- Model serving endpoint was added to serve Model ID 21
- Authentication middleware was fixed recently
- Routes may not have been properly tested end-to-end

## Data Analysis Required

### Logs to Examine
```bash
# Check ECS logs for API service
aws logs tail /ecs/hokusai-api-development --follow --since 1h

# Search for 404 errors
aws logs filter-log-events --log-group-name /ecs/hokusai-api-development \
  --filter-pattern "404"
```

### API Tests to Run
1. Test route registration order
2. Test with curl to verify actual routes
3. Check OpenAPI schema at `/docs` to see registered routes
4. Test authentication flow

### Metrics to Review
- 404 error rate for `/api/v1/models/*` paths
- Request patterns from third-party users

## Investigation Strategy

### Priority Order
1. **Verify route registration** - Check FastAPI /docs to see what routes are actually registered
2. **Test route matching** - Call endpoints directly with curl
3. **Check authentication** - Verify auth middleware not blocking routes incorrectly
4. **Review ALB configuration** - Ensure ALB is routing to correct target group

### Tools and Techniques
- FastAPI interactive docs (`/docs`)
- Direct curl requests
- FastAPI route inspection
- Log analysis

### Key Questions to Answer
1. ✅ Are the model serving routes registered in FastAPI?
2. ✅ Is there a route conflict between models.router and model_serving.router?
3. ❓ Is the authentication middleware excluding the correct paths?
4. ❓ Is the ALB routing correctly to the API service?

### Success Criteria
- Understand exactly why routes return 404
- Identify the root cause (route conflict, missing registration, or other)
- Have clear path to fix

## Risk Assessment

### Current Impact on Users
- **High** - Third-party integration completely blocked
- API key holders cannot use Model ID 21
- No workaround available

### Potential for Escalation
- Medium - Could affect other model serving endpoints if pattern continues
- Loss of customer confidence in API reliability

### Security Implications
- None identified - 404 errors don't expose sensitive information
- HTML responses instead of JSON could leak framework information

### Data Integrity Concerns
- None - no data being written or corrupted
- Pure routing issue

## Timeline

### When Bug First Appeared
- Likely when model_serving.py endpoints were first deployed
- May have never worked in production

### Correlation with Deployments/Changes
- Recent deployment of model serving endpoints
- Authentication middleware fixes may have exposed the issue

### Frequency of Occurrence
- **Constant** - 100% failure rate for these endpoints

### Patterns in Timing
- No time-based patterns
- Affects all requests equally

## Next Steps

1. ✅ Generate hypotheses about root causes
2. ⏭️ Test each hypothesis systematically
3. ⏭️ Document confirmed root cause
4. ⏭️ Create fix tasks
5. ⏭️ Implement fix with tests
6. ⏭️ Validate fix resolves original issue
