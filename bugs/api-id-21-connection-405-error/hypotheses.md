# Root Cause Hypotheses: API ID 21 Connection 405 Error

## Hypothesis Summary Table

| # | Hypothesis | Confidence | Complexity | Impact if True |
|---|------------|------------|------------|----------------|
| 1 | Route parameter type mismatch (UUID vs string) | High (85%) | Simple | Critical - Wrong endpoint handling request |
| 2 | Missing predict endpoint in model_serving.py router | High (80%) | Simple | Critical - Endpoint not registered |
| 3 | Router registration order causing route shadowing | Medium (60%) | Medium | High - Conflicting routes |
| 4 | Model 21 not properly deployed with UUID | Medium (50%) | Medium | High - Wrong deployment method |
| 5 | ALB routing misconfiguration | Low (20%) | Complex | Medium - Infrastructure issue |

---

## Detailed Hypotheses

### Hypothesis 1: Route Parameter Type Mismatch (UUID vs String)

**Confidence**: High (85%)
**Category**: API Routing / Type System Mismatch

#### Description

The `predict.py` router defines the predict endpoint with `deployed_model_id: UUID` parameter type, but clients are calling with string "21". FastAPI's type validation rejects the string "21" as invalid UUID format before the handler executes, resulting in 405 or similar error.

However, the `/api/v1/models` prefix in model_serving.py should create a separate route `/api/v1/models/{model_id}/predict` that accepts strings.

**The issue**: The model_serving.py router may not have the `/predict` POST endpoint implemented yet.

#### Supporting Evidence

1. **predict.py line 85-92** expects UUID:
   ```python
   @router.post("/models/{deployed_model_id}/predict", ...)
   async def predict(deployed_model_id: UUID, ...)
   ```

2. **Client is calling** with string "21" not a UUID

3. **MODEL_21_VERIFICATION_REPORT.md** documents the endpoint as `/api/v1/models/21/predict` (string ID)

4. **405 Method Not Allowed** suggests the path matches but method doesn't (or route doesn't exist)

5. **model_serving.py** creates router but may not have `/predict` endpoint defined

#### Why This Causes the Bug

1. Client calls `POST /api/v1/models/21/predict`
2. FastAPI route matching:
   - Tries predict.py route: `/models/{deployed_model_id}/predict`
   - "21" doesn't match UUID type → route rejected
   - Tries model_serving.py routes → no POST predict endpoint found
   - Returns 405 Method Not Allowed

#### Test Method

1. Check model_serving.py for POST predict endpoint:
   ```bash
   grep -n "def predict" src/api/endpoints/model_serving.py
   grep -n "@router.post.*predict" src/api/endpoints/model_serving.py
   ```

2. Check registered routes via FastAPI docs:
   ```bash
   curl https://api.hokus.ai/docs
   # Or locally: http://localhost:8001/docs
   ```

3. Test with actual UUID vs string ID:
   ```bash
   # Try with string
   curl -X POST "https://api.hokus.ai/api/v1/models/21/predict" \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"inputs": {}}'

   # Check if there's a UUID for model 21
   # Query database or check deployment records
   ```

4. **Expected results if TRUE**: model_serving.py has no POST /predict endpoint defined

5. **Expected results if FALSE**: model_serving.py has POST /predict endpoint and it's working

#### Code/Configuration to Check

```bash
# Check model_serving.py endpoints
cat src/api/endpoints/model_serving.py | grep -A 20 "@router"

# Check route registration in main.py
cat src/api/main.py | grep -A 5 "model_serving"

# Check if predict.py routes are also registered
cat src/api/main.py | grep -A 5 "predict"
```

#### Quick Fix Test

Add a simple POST /predict endpoint to model_serving.py:
```python
@router.post("/{model_id}/predict")
async def predict_model(model_id: str, request: PredictionRequest):
    return {"model_id": model_id, "status": "test"}
```

If this fixes the 405, hypothesis is confirmed.

---

### Hypothesis 2: Missing Predict Endpoint in model_serving.py Router

**Confidence**: High (80%)
**Category**: Missing Implementation

#### Description

The `model_serving.py` router is registered at `/api/v1/models` prefix but doesn't have a POST prediction endpoint defined. The file may only have GET endpoints (info, health) but not the POST /predict endpoint.

#### Supporting Evidence

1. model_serving.py line 25 shows router prefix: `/api/v1/models`
2. main.py line 86 registers the router: `app.include_router(model_serving.router, tags=["model-serving"])`
3. 405 error typically means "method not allowed on this path"
4. Documentation describes endpoint but implementation may be incomplete

#### Why This Causes the Bug

1. Router is registered correctly at `/api/v1/models`
2. Possible GET endpoints exist: `/{model_id}/info`, `/{model_id}/health`
3. POST `/{model_id}/predict` endpoint is missing
4. FastAPI returns 405 when path exists but method doesn't match

#### Test Method

1. Read full model_serving.py file to inventory all endpoints
2. Check for POST predict endpoint definition
3. Look for any TODO comments or incomplete implementations
4. Compare against MODEL_21_VERIFICATION_REPORT.md documented endpoints

**Expected if TRUE**: No POST predict endpoint in model_serving.py

**Expected if FALSE**: POST predict endpoint exists but has different issue

#### Code/Configuration to Check

```bash
# List all endpoints in model_serving.py
grep -n "^@router\." src/api/endpoints/model_serving.py

# Check for predict function
grep -n "async def.*predict" src/api/endpoints/model_serving.py

# Read the entire router section
head -200 src/api/endpoints/model_serving.py
```

#### Quick Fix Test

Verify by checking file length - if model_serving.py is incomplete (under 200 lines), likely missing endpoints.

---

### Hypothesis 3: Router Registration Order Causing Route Shadowing

**Confidence**: Medium (60%)
**Category**: Configuration - Route Priority

#### Description

In main.py, both `models.router` (line 84) and `model_serving.router` (line 86) are registered, potentially with overlapping paths. FastAPI matches routes in registration order, so the first matching route handles the request. If there's path overlap, the wrong router may handle the request.

#### Supporting Evidence

1. main.py line 84: `app.include_router(models.router, prefix="/models", tags=["models"])`
2. main.py line 86: `app.include_router(model_serving.router, tags=["model-serving"])`
3. Both routers could have paths starting with `/models/`
4. Route matching is order-dependent in FastAPI

#### Why This Causes the Bug

1. models.router registers first with `/models` prefix
2. models.router may have a catch-all or conflicting route
3. Request matches models.router route that doesn't support POST
4. model_serving.router never gets chance to handle request
5. Result: 405 from models.router

#### Test Method

1. Check models.router for any routes matching `/models/{model_id}/*`:
   ```bash
   grep -n "@router" src/api/routes/models.py | head -20
   ```

2. Check exact prefixes:
   - models.router has prefix "/models"
   - model_serving.router has prefix "/api/v1/models" (in router definition)
   - These should NOT conflict if prefixes are different

3. Test by temporarily disabling models.router:
   ```python
   # Comment out in main.py:
   # app.include_router(models.router, prefix="/models", tags=["models"])
   ```

**Expected if TRUE**: models.router has conflicting route that shadows model_serving

**Expected if FALSE**: Routers have distinct prefixes and no conflict

#### Code/Configuration to Check

```bash
# Check models.router routes
head -100 src/api/routes/models.py

# Compare prefixes
grep "prefix=" src/api/main.py
grep "router = APIRouter(prefix=" src/api/routes/models.py
grep "router = APIRouter(prefix=" src/api/endpoints/model_serving.py
```

#### Quick Fix Test

Change router registration order - put model_serving.router before models.router. If this fixes it, route shadowing is confirmed.

---

### Hypothesis 4: Model 21 Not Properly Deployed with UUID

**Confidence**: Medium (50%)
**Category**: Deployment Configuration

#### Description

Model 21 may not exist in the `deployed_models` database table with a proper UUID. The predict.py endpoint expects a UUID from this table, but Model 21 might only be registered in MLflow registry, not in the deployment tracking system.

This would mean:
- Model 21 is registered (in MLflow)
- Model 21 is NOT deployed (in deployment system)
- Two different systems: registry vs deployment
- Documentation describes one system but implementation uses another

#### Supporting Evidence

1. predict.py uses `DeploymentService` and `deployed_models` table
2. model_serving.py doesn't use deployment table - loads directly from HuggingFace
3. Two different serving architectures may exist
4. MODEL_21_VERIFICATION_REPORT.md may document planned architecture, not actual

#### Why This Causes the Bug

1. Model 21 registered in MLflow but not "deployed" with UUID
2. predict.py endpoint requires UUID from deployed_models table
3. model_serving.py endpoint would work but is incomplete
4. No valid route exists for string-based model ID

#### Test Method

1. Query database for Model 21:
   ```sql
   SELECT id, model_id, status, provider
   FROM deployed_models
   WHERE model_id = '21' OR model_id LIKE '%21%';
   ```

2. Check if DeploymentService is being used:
   ```bash
   grep -r "DeploymentService" src/api/
   ```

3. Verify which system Model 21 uses:
   - MLflow registry? Check MLflow UI
   - Deployment table? Check database
   - HuggingFace direct? Check model_serving.py

**Expected if TRUE**: Model 21 not in deployed_models table

**Expected if FALSE**: Model 21 has UUID in deployed_models table

#### Code/Configuration to Check

```bash
# Check database schema
psql $DATABASE_URL -c "\d deployed_models"

# Check DeploymentService usage
grep -n "DeploymentService" src/api/routes/predict.py

# Check model_serving approach
grep -n "get_model_config" src/api/endpoints/model_serving.py
```

#### Quick Fix Test

Register Model 21 in deployed_models table with UUID, then test with UUID-based endpoint.

---

### Hypothesis 5: ALB Routing Misconfiguration

**Confidence**: Low (20%)
**Category**: Infrastructure - Load Balancer

#### Description

The Application Load Balancer (ALB) in front of the API service may have routing rules that incorrectly handle `/api/v1/models/21/predict` path. The ALB could be:
- Routing to wrong target group
- Stripping path prefix incorrectly
- Not allowing POST method on this path
- Applying incorrect listener rules

#### Supporting Evidence

1. Client successfully connects (no 404)
2. Authentication works (no 401) - suggests request reaches auth middleware
3. 405 suggests method restriction, could be at ALB level
4. CLAUDE.md mentions multiple ALBs: main, registry, data pipeline

#### Why This Causes the Bug

1. ALB receives POST request
2. ALB applies path-based routing rules
3. ALB either:
   - Forwards to wrong service
   - Blocks POST method
   - Transforms request incorrectly
4. API service receives malformed request or different method

#### Test Method

1. Check ALB configuration in infrastructure repo:
   ```bash
   cd ../hokusai-infrastructure
   grep -r "models.*predict" environments/*/alb*.tf
   ```

2. Test directly against ECS service (bypass ALB):
   ```bash
   # Get internal ECS service URL
   curl -X POST "http://api.hokusai-development.local:8001/api/v1/models/21/predict" \
     -H "Authorization: Bearer $API_KEY" \
     -d '{"inputs": {}}'
   ```

3. Compare ALB response vs direct ECS response

4. Check ALB access logs for request transformation

**Expected if TRUE**: Direct ECS request works, ALB request fails

**Expected if FALSE**: Both fail with same 405 error

#### Code/Configuration to Check

```bash
# Check ALB configuration
cd ../hokusai-infrastructure
find . -name "*.tf" -exec grep -l "data-pipeline\|models" {} \;

# Check listener rules
grep -A 10 "listener_rule" environments/development/*.tf
```

#### Quick Fix Test

Test against internal ECS endpoint. If it works, ALB is the issue. If it also fails, ALB is not the problem.

---

## Testing Priority Order

1. **Start with Hypothesis 1 & 2 (Combined)**: Read model_serving.py to see if POST /predict endpoint exists
   - **Reasoning**: This is the most likely issue - incomplete implementation
   - **Time**: 5 minutes to read file
   - **High confidence**: 80-85%
   - **Quick to verify**: Just read the code

2. **If H1/H2 false, test Hypothesis 3**: Check router registration and path conflicts
   - **Reasoning**: Route shadowing is common FastAPI issue
   - **Time**: 10 minutes to analyze routes
   - **Medium confidence**: 60%
   - **Quick to test**: Reorder routers or check /docs endpoint

3. **If H3 false, test Hypothesis 4**: Check database for Model 21 deployment
   - **Reasoning**: Deployment vs Registry separation
   - **Time**: 15 minutes to query database
   - **Medium confidence**: 50%
   - **Requires**: Database access

4. **If all above false, test Hypothesis 5**: Check ALB configuration
   - **Reasoning**: Infrastructure issues are less likely given auth works
   - **Time**: 30 minutes to check infrastructure
   - **Low confidence**: 20%
   - **Complex**: Requires infrastructure repo access

---

## Alternative Hypotheses to Consider if All Above Fail

1. **HTTP Method Case Sensitivity**: Client sending "Post" instead of "POST"
2. **Content-Type Validation**: API rejecting request due to missing/wrong Content-Type header
3. **API Gateway/Proxy**: Another proxy between client and ALB
4. **CORS Preflight**: OPTIONS request failing, blocking POST
5. **Authentication Middleware Side Effect**: Middleware modifying request method
6. **FastAPI Version Bug**: Version-specific routing bug
7. **Starlette Routing Issue**: Underlying framework issue

## Data Needed for Further Investigation

If initial hypotheses don't pan out, gather:

1. **CloudWatch Logs**:
   ```bash
   aws logs tail /ecs/hokusai-api-development --since 1h --filter-pattern "405"
   ```

2. **Request Traces**:
   - Full request headers from client
   - Full response headers from server
   - Request ID for tracing

3. **Route Dump**:
   - Export all registered routes from FastAPI app
   - Use `/openapi.json` endpoint

4. **Database State**:
   ```sql
   SELECT * FROM deployed_models LIMIT 10;
   SELECT * FROM models WHERE id = 21;
   ```

5. **FastAPI Debug Mode**:
   - Enable debug logging
   - Check startup route registration logs

6. **Direct Service Test**:
   - Access ECS task directly (bypass ALB)
   - Use port forwarding or AWS Session Manager

---

## Recommended First Action

**Read model_serving.py file completely** to verify if POST /predict endpoint is implemented. This will confirm or reject Hypothesis 1/2 within 5 minutes with near certainty.

```bash
cat src/api/endpoints/model_serving.py
```

Based on that finding, we can immediately move to appropriate fix or continue testing other hypotheses.
