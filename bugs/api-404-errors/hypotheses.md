# Root Cause Hypotheses for API 404 Errors

## Hypothesis Summary Table

| # | Hypothesis | Confidence | Complexity | Impact if True |
|---|------------|------------|------------|----------------|
| 1 | Router registration conflict - model_serving router has conflicting prefix | High (85%) | Simple | Critical |
| 2 | Authentication middleware incorrectly excluding API paths | Medium (40%) | Medium | High |
| 3 | ALB routing rules not configured for /api/v1/models/* paths | Low (20%) | Medium | Critical |
| 4 | OpenAPI route generation issue with nested prefixes | Low (15%) | Medium | High |

## Detailed Hypotheses

### Hypothesis 1: Router Registration Conflict - Duplicate /models Prefix

**Confidence**: High (85%)
**Category**: Configuration / Route Registration

#### Description

The `model_serving.router` in `src/api/endpoints/model_serving.py` defines its own prefix `/api/v1/models` (line 30), but when it's included in `main.py` (line 86), there's potential for conflict with the `models.router` which is mounted at `/models` prefix (line 84).

The issue is likely one of two scenarios:
1. The routes are registering at the wrong path entirely
2. FastAPI is matching the `models.router` first and returning 404 before checking `model_serving.router`

#### Supporting Evidence

**From Code Review:**
- `model_serving.py:30`: `router = APIRouter(prefix="/api/v1/models", tags=["model-serving"])`
- `main.py:84`: `app.include_router(models.router, prefix="/models", tags=["models"])`
- `main.py:86`: `app.include_router(model_serving.router, tags=["model-serving"])`

**From models.py:**
- Line 141: `@router.get("/{model_name}/{version}")` which becomes `/models/{model_name}/{version}`
- This could match `/api/v1/models/21/predict` if "api" is treated as model_name

**Pattern**: HTML 404 response indicates FastAPI is receiving the request but not finding a matching route

#### Why This Causes the Bug

When a request comes for `/api/v1/models/21/predict`:

1. FastAPI checks routers in registration order
2. `models.router` (prefix `/models`) doesn't match because path is `/api/v1/models/21/predict`
3. `model_serving.router` should match with its prefix `/api/v1/models`
4. BUT if FastAPI's path matching is confused by the nested structure, it may fail

Alternatively:
- The `models.router` at `/models` may be matching `/models/v1/21/predict` incorrectly
- Or the model_serving routes aren't being registered at all

#### Test Method

1. **Check registered routes in FastAPI:**
   ```bash
   # Start the API locally
   python -m uvicorn src.api.main:app --reload

   # Open browser to http://localhost:8000/docs
   # Look for /api/v1/models/21/predict in the endpoint list
   ```

2. **Test with curl:**
   ```bash
   # Test model serving endpoint
   curl -X GET "http://localhost:8000/api/v1/models/21/info" \
     -H "Authorization: Bearer test-key"

   # Expected if TRUE: Route not found in /docs, 404 error
   # Expected if FALSE: Route exists in /docs, works with auth
   ```

3. **Inspect route registration:**
   ```python
   # Add to main.py after all include_router calls:
   for route in app.routes:
       print(f"{route.path} - {route.methods if hasattr(route, 'methods') else 'N/A'}")
   ```

4. **Quick test - modify router inclusion:**
   ```python
   # In main.py, try removing the prefix from model_serving router:
   # Change line 86 to:
   app.include_router(model_serving.router, prefix="", tags=["model-serving"])
   ```

#### Code/Configuration to Check

```python
# src/api/main.py lines 84-86
app.include_router(models.router, prefix="/models", tags=["models"])
app.include_router(dspy.router, tags=["dspy"])
app.include_router(model_serving.router, tags=["model-serving"])  # Check this

# src/api/endpoints/model_serving.py line 30
router = APIRouter(prefix="/api/v1/models", tags=["model-serving"])

# src/api/routes/models.py lines 38-76
# Check for route patterns that might conflict
```

#### Quick Fix Test

**Option 1:** Remove the prefix from model_serving.py and set it in main.py:
```python
# In model_serving.py:30, change to:
router = APIRouter(tags=["model-serving"])

# In main.py:86, change to:
app.include_router(model_serving.router, prefix="/api/v1/models", tags=["model-serving"])
```

**Option 2:** Change the registration order to test priority:
```python
# In main.py, move model_serving.router BEFORE models.router
app.include_router(model_serving.router, tags=["model-serving"])  # Test if order matters
app.include_router(models.router, prefix="/models", tags=["models"])
```

---

### Hypothesis 2: Authentication Middleware Excluding Paths Incorrectly

**Confidence**: Medium (40%)
**Category**: Authentication / Middleware

#### Description

The `APIKeyAuthMiddleware` in `src/middleware/auth.py` has an `excluded_paths` list (lines 142-154) that specifies paths that don't require authentication. If the middleware is incorrectly matching `/api/v1/models/*` paths as excluded, OR if it's rejecting them before they reach the route handlers, this could cause unexpected behavior.

However, 404 errors typically occur BEFORE middleware runs (during route matching), so this is less likely.

#### Supporting Evidence

**From auth.py:**
- Lines 142-154: Excluded paths include health endpoints, docs, etc.
- `/api/v1/models/*` is NOT in the excluded list
- Line 326: `if any(request.url.path.startswith(path) for path in self.excluded_paths):`

**Pattern:**
- HTML 404 response suggests route matching failure, not auth rejection
- Auth rejections would return 401 JSON, not 404 HTML

#### Why This Causes the Bug

If middleware is somehow interfering with route registration or matching:
1. Middleware could be consuming the request before FastAPI route matching
2. Middleware could be returning early with HTML response (unlikely)
3. Middleware could be modifying request path (very unlikely)

#### Test Method

1. **Temporarily disable auth middleware:**
   ```python
   # In main.py:48, comment out:
   # app.add_middleware(APIKeyAuthMiddleware)

   # Then test endpoints without auth
   curl -X GET "http://localhost:8000/api/v1/models/21/info"
   ```

2. **Add debug logging to middleware:**
   ```python
   # In auth.py:326, add logging:
   logger.info(f"Auth check for path: {request.url.path}, excluded: {any(request.url.path.startswith(path) for path in self.excluded_paths)}")
   ```

3. **Expected results:**
   - If TRUE: Endpoints work without middleware
   - If FALSE: Endpoints still 404 without middleware

#### Code/Configuration to Check

```python
# src/middleware/auth.py lines 142-154
self.excluded_paths = excluded_paths or [
    "/health",
    "/ready",
    "/live",
    "/version",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/favicon.ico",
    "/api/v1/dspy/health",
    "/api/health/mlflow",
]
```

#### Quick Fix Test

Add `/api/v1/models/` to excluded paths temporarily:
```python
self.excluded_paths = [
    # ... existing paths ...
    "/api/v1/models/",  # TEST ONLY
]
```

---

### Hypothesis 3: ALB Routing Rules Missing for /api/v1/models/* Paths

**Confidence**: Low (20%)
**Category**: Infrastructure / Load Balancer Configuration

#### Description

The AWS Application Load Balancer may not have routing rules configured to forward requests to `/api/v1/models/*` paths to the API service ECS task. If the ALB returns its own 404 page (which could be HTML), this would explain the symptom.

However, this is less likely because:
1. Other `/api/*` paths reportedly work
2. The bug report mentions the third party is "trying to use the API" suggesting they can reach it
3. ALB would typically return a different error or no response at all

#### Supporting Evidence

**Infrastructure Context:**
- From CLAUDE.md: API service runs on `api.hokus.ai`
- ALB name: `hokusai-dp-development`
- Other API paths work (health checks, etc.)

**Pattern:**
- HTML response could come from ALB default 404
- But more likely from FastAPI since docs are accessible

#### Why This Causes the Bug

If ALB routing rules are misconfigured:
1. Request reaches ALB at `api.hokus.ai`
2. ALB checks path `/api/v1/models/21/predict` against listener rules
3. No rule matches this specific path pattern
4. ALB returns default 404 (HTML)
5. Request never reaches ECS

#### Test Method

1. **Check ALB listener rules:**
   ```bash
   aws elbv2 describe-listener-rules \
     --listener-arn $(aws elbv2 describe-load-balancers \
       --names hokusai-dp-development \
       --query 'LoadBalancers[0].LoadBalancerArn' --output text | sed 's/loadbalancer/listener/')
   ```

2. **Test from within VPC:**
   ```bash
   # SSH to a bastion or ECS task
   curl -v http://api.hokusai-development.local:8001/api/v1/models/21/info

   # If this works but external doesn't, it's ALB
   ```

3. **Check ALB access logs:**
   ```bash
   # Look for 404s in ALB logs
   aws s3 ls s3://hokusai-alb-logs/ --recursive | grep hokusai-dp-development
   ```

#### Code/Configuration to Check

Check in `hokusai-infrastructure` repository:
- `environments/development/alb.tf` or similar
- Target group configurations
- Listener rule path patterns

```hcl
# Look for rules like:
resource "aws_lb_listener_rule" "api_paths" {
  condition {
    path_pattern {
      values = ["/api/*"]  # Should include /api/v1/models/*
    }
  }
}
```

#### Quick Fix Test

Add a catch-all rule for /api/* if it doesn't exist.

---

### Hypothesis 4: OpenAPI Route Generation Issue with Nested Prefixes

**Confidence**: Low (15%)
**Category**: FastAPI Framework Behavior

#### Description

FastAPI may have an edge case with nested router prefixes where:
- `model_serving.router` defines prefix `/api/v1/models`
- `main.py` includes it with no additional prefix
- This could cause OpenAPI schema generation to fail or routes to not register properly

This is the least likely because FastAPI handles this pattern well in most cases.

#### Supporting Evidence

- FastAPI documentation supports this pattern
- Many projects use nested prefixes successfully
- No known bugs in FastAPI for this behavior

#### Why This Causes the Bug

If FastAPI has a bug or edge case:
1. Router gets included in app
2. Prefix is registered in OpenAPI schema
3. But actual route matching fails due to framework issue
4. Results in 404 for valid paths

#### Test Method

1. **Check FastAPI version:**
   ```bash
   pip show fastapi
   # Check if there are known issues with this version
   ```

2. **Simplify router structure:**
   ```python
   # Create a minimal test endpoint at root level in main.py
   @app.get("/test/api/v1/models/21/info")
   async def test_route():
       return {"test": "working"}
   ```

3. **Check OpenAPI schema:**
   ```bash
   curl http://localhost:8000/openapi.json | jq '.paths'
   # Look for /api/v1/models/* paths
   ```

#### Quick Fix Test

Flatten the router structure completely:
```python
# In main.py, define endpoints directly instead of using router
```

---

## Testing Priority Order

1. **Start with Hypothesis 1** because:
   - Highest confidence (85%)
   - Simplest to test (check /docs and modify router registration)
   - Most likely based on code review
   - Can be tested immediately without infrastructure access

2. **If Hypothesis 1 is false, test Hypothesis 2** because:
   - Medium confidence (40%)
   - Easy to test (disable middleware)
   - Would explain HTML response pattern

3. **If Hypotheses 1-2 are false, test Hypothesis 3** because:
   - Requires infrastructure access
   - Less likely based on symptoms
   - But would be critical if true

4. **Test Hypothesis 4 last** because:
   - Lowest confidence (15%)
   - Framework issues are rare
   - More complex to diagnose

## Alternative Hypotheses to Consider if All Above Fail

- **CORS preflight blocking:** OPTIONS requests failing before GET/POST
- **Request path rewriting:** Proxy or middleware modifying paths
- **Case sensitivity:** Path matching failing due to case differences
- **Trailing slash issues:** Routes defined with/without trailing slashes
- **HTTP method mismatch:** Routes registered for POST but GET requested
- **Deployment sync issue:** Old code deployed without model_serving routes
- **Docker build issue:** Route file not included in container image
- **Import error:** model_serving module failing to import silently

## Data Needed for Further Investigation

If initial hypotheses don't pan out, gather:

**Application Logs:**
```bash
aws logs tail /ecs/hokusai-api-development --follow --since 2h --filter-pattern "404"
aws logs tail /ecs/hokusai-api-development --follow --since 2h --filter-pattern "model"
```

**ECS Task Details:**
```bash
# Check if correct Docker image is deployed
aws ecs describe-tasks --cluster hokusai-development \
  --tasks $(aws ecs list-tasks --cluster hokusai-development \
    --service-name hokusai-api-development --query 'taskArns[0]' --output text)
```

**Request/Response Samples:**
- Full HTTP request headers from third-party user
- Complete HTTP response (headers + body) showing HTML 404
- Timestamp of failed request for log correlation

**OpenAPI Schema:**
```bash
curl https://api.hokus.ai/openapi.json > openapi-schema.json
# Analyze to see if routes are registered
```

**Health Check Verification:**
```bash
curl https://api.hokus.ai/health
# Confirm API is reachable and responding
```
