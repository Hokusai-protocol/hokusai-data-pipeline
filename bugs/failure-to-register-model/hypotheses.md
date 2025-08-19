# Bug Hypotheses: Failure to Register Model

## Hypothesis Summary Table

| # | Hypothesis | Confidence | Complexity | Impact if True |
|---|------------|------------|------------|----------------|
| 1 | API proxy not forwarding auth headers correctly to MLflow | High | Simple | Critical |
| 2 | MLflow endpoints not properly mounted/configured in API service | High | Medium | Critical |
| 3 | Recent webhook migration broke auth flow | Medium | Medium | High |
| 4 | API key validation service rejecting valid keys | Medium | Simple | Critical |
| 5 | Environment variables missing/misconfigured in ECS | Low | Simple | High |

## Detailed Hypotheses

### Hypothesis 1: API Proxy Not Forwarding Auth Headers Correctly
**Confidence**: High (85%)
**Category**: API Contract Violation

#### Description
The API proxy service is receiving the authentication headers but not properly forwarding them to the MLflow backend. The proxy may be stripping headers, transforming them incorrectly, or using the wrong header name.

#### Supporting Evidence
- Error message: "API key required" despite API key being provided
- Previous PR #60 mentioned "Hokusai auth headers are removed before proxying to MLflow"
- Partial success (run_id created) suggests some auth works but not all
- 403 Forbidden on model version creation indicates auth issue

#### Why This Causes the Bug
When the proxy strips or fails to forward authentication headers, MLflow receives requests without proper authentication. This causes MLflow to reject requests with "API key required" or return 403 Forbidden, even though the client provided valid credentials.

#### Test Method
1. Add logging to API proxy to confirm headers received
2. Add logging to show headers being forwarded to MLflow
3. Use curl to test directly with various header formats
4. Expected if TRUE: Headers missing or malformed in forwarded request
5. Expected if FALSE: Headers properly forwarded with correct values

#### Code/Configuration to Check
```bash
# Check proxy implementation
grep -r "proxy" src/api/routes/
grep -r "Authorization" src/api/routes/
grep -r "X-API-Key" src/api/routes/

# Test with curl
curl -H "Authorization: Bearer hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN" \
     https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search

# Check recent changes
git log -p --since="1 week ago" -- src/api/routes/mlflow_proxy.py
```

#### Quick Fix Test
Temporarily modify proxy to explicitly forward Authorization header without transformation.

---

### Hypothesis 2: MLflow Endpoints Not Properly Mounted
**Confidence**: High (80%)
**Category**: Configuration Mismatch

#### Description
The API service routing configuration doesn't properly handle the `/api/mlflow/*` path pattern, causing 404 errors. The route may be missing, misconfigured, or conflicting with other routes.

#### Supporting Evidence
- 404 Not Found errors on MLflow endpoints
- HTML error page returned instead of JSON
- Previous tickets mention "MLflow endpoints now accessible (return 401/502)"
- Documentation shows endpoints should be at `/api/mlflow/api/2.0/mlflow/*`

#### Why This Causes the Bug
If routes are not properly configured, requests never reach the proxy handler. Instead, they hit the default 404 handler, returning HTML error pages. This prevents any MLflow operations from succeeding.

#### Test Method
1. Review API service route configuration
2. Check if /api/mlflow routes are registered
3. Test each endpoint with curl
4. Expected if TRUE: Routes missing or incorrectly configured
5. Expected if FALSE: Routes properly configured and reachable

#### Code/Configuration to Check
```bash
# Check route configuration
find src/api -name "*.py" -exec grep -l "mlflow" {} \;
grep -r "@router" src/api/routes/

# Check main app route registration
grep -r "include_router" src/api/main.py

# Test route availability
curl https://registry.hokus.ai/api/mlflow/health
```

#### Quick Fix Test
Add explicit debug logging to show which routes are registered on startup.

---

### Hypothesis 3: Recent Webhook Migration Broke Auth Flow
**Confidence**: Medium (60%)
**Category**: Recent Change Impact

#### Description
The recent migration from Redis pub/sub to webhook system may have inadvertently broken the authentication flow or removed necessary auth middleware.

#### Supporting Evidence
- Current branch: feature/replace-redis-with-webhook
- Recent commits show webhook implementation
- Bug appeared after webhook work started
- Previous auth was working per completed tickets

#### Why This Causes the Bug
During refactoring for webhook support, authentication middleware or header processing code may have been accidentally removed or modified, breaking the auth flow for MLflow operations.

#### Test Method
1. Compare auth flow before and after webhook changes
2. Check git diff for auth-related changes
3. Test on main branch vs feature branch
4. Expected if TRUE: Auth works on main, broken on feature branch
5. Expected if FALSE: Both branches have same auth behavior

#### Code/Configuration to Check
```bash
# Check webhook-related changes
git diff main...feature/replace-redis-with-webhook -- src/api/

# Look for auth middleware changes
git diff main...feature/replace-redis-with-webhook | grep -C 5 "auth\|Auth\|API"

# Check if auth dependencies removed
git diff main...feature/replace-redis-with-webhook -- requirements.txt
```

#### Quick Fix Test
Temporarily revert auth-related changes from webhook branch.

---

### Hypothesis 4: API Key Validation Service Rejecting Valid Keys
**Confidence**: Medium (50%)
**Category**: Authorization Issue

#### Description
The auth service is receiving the API key but incorrectly rejecting it as invalid, possibly due to format validation, database lookup issues, or key expiration.

#### Supporting Evidence
- API key format appears correct: "hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN"
- Error: "API key required" suggests key not recognized
- Multiple retry attempts all fail
- Previous tickets show auth service was "fully operational"

#### Why This Causes the Bug
If the auth service incorrectly validates API keys, all authenticated requests fail regardless of valid credentials being provided.

#### Test Method
1. Query auth database directly for API key
2. Test auth service endpoint directly
3. Check auth service logs for validation errors
4. Expected if TRUE: Key not found or validation fails
5. Expected if FALSE: Key validates successfully

#### Code/Configuration to Check
```bash
# Check auth service logs
aws logs tail /ecs/hokusai-auth-development --follow --since 1h

# Test auth directly
curl -H "X-API-Key: hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN" \
     https://auth.hokus.ai/api/validate

# Check database for key
echo "SELECT * FROM api_keys WHERE key LIKE 'hk_live_pIDV%';" | psql $AUTH_DB_URL
```

#### Quick Fix Test
Create a new API key and test with it.

---

### Hypothesis 5: Environment Variables Missing in ECS
**Confidence**: Low (30%)
**Category**: Configuration Issue

#### Description
Required environment variables for auth or MLflow connectivity are missing from the ECS task definition, causing services to use defaults or fail.

#### Supporting Evidence
- Previous tickets mention "Missing: DB_PASSWORD"
- Environment-specific configuration documented
- Services were working before infrastructure migration

#### Why This Causes the Bug
Missing environment variables cause services to fail auth checks or use incorrect endpoints, preventing successful model registration.

#### Test Method
1. Check ECS task definitions for all services
2. Compare with required variables in documentation
3. Verify secrets are properly mounted
4. Expected if TRUE: Critical variables missing
5. Expected if FALSE: All required variables present

#### Code/Configuration to Check
```bash
# Check ECS task definitions
aws ecs describe-task-definition --task-definition hokusai-api-development \
  --query 'taskDefinition.containerDefinitions[0].environment'

# Check secrets configuration
aws ecs describe-task-definition --task-definition hokusai-api-development \
  --query 'taskDefinition.containerDefinitions[0].secrets'

# Verify environment variables in running task
aws ecs describe-tasks --cluster hokusai-development \
  --tasks $(aws ecs list-tasks --cluster hokusai-development --service-name hokusai-api-development --query 'taskArns[0]' --output text)
```

#### Quick Fix Test
Add missing environment variables to ECS task definition.

---

## Testing Priority Order

1. Start with Hypothesis 1 (auth header forwarding) - Most likely given error messages
2. If false, test Hypothesis 2 (route configuration) - Would explain 404 errors
3. Then Hypothesis 3 (webhook migration impact) - Recent changes often cause bugs
4. Follow with Hypothesis 4 (API key validation) - Less likely but critical
5. Finally Hypothesis 5 (environment variables) - Simple to check and fix

## Alternative Hypotheses to Consider if All Above Fail

- ALB routing rules not forwarding to correct target group
- MLflow service not actually running or healthy
- Network security groups blocking internal communication
- CORS configuration preventing proper headers
- Rate limiting or throttling on API endpoints
- Certificate/TLS issues between services
- Database connection pool exhausted

## Data Needed for Further Investigation

If initial hypotheses don't pan out, gather:
- Full request/response traces with headers
- ALB access logs for failed requests
- Inter-service network traffic captures
- Database connection pool metrics
- Service discovery DNS resolution logs
- Container resource utilization metrics