# Root Cause Hypotheses: Problems Registering Model

## Hypothesis Summary Table

| # | Hypothesis | Confidence | Complexity | Impact if True |
|---|------------|------------|------------|----------------|
| 1 | API keys are created with default read-only scope | High | Simple | Critical |
| 2 | Missing model:write permission in auth middleware | High | Medium | Critical |
| 3 | MLflow proxy incorrectly filtering write operations | Medium | Complex | Critical |
| 4 | Role-based access control restricts third-party users | Medium | Medium | High |
| 5 | Recent auth service deployment changed default permissions | Low | Simple | High |

## Detailed Hypotheses

### Hypothesis 1: API Keys Created with Default Read-Only Scope
**Confidence**: High (85%)
**Category**: Configuration/Permission Issue

#### Description
API keys are being generated with a default "read-only" scope when created for third-party users, missing the necessary write permissions for model registration. The auth service likely has different permission templates, and external users are assigned the restrictive one by default.

#### Supporting Evidence
- API key authenticates successfully (proves key is valid)
- Read operations work perfectly
- Write operations consistently return 403
- Error is authorization-based, not authentication
- Affects all third-party API keys consistently

#### Why This Causes the Bug
When the auth service generates API keys, it assigns permission scopes. If the default template for external users only includes read permissions (e.g., "model:read", "experiment:read") but lacks write permissions ("model:write", "experiment:write"), any attempt to create runs or register models will be rejected at the authorization layer.

#### Test Method
1. Query the auth service database for the specific API key's permissions
2. Compare permissions between working internal keys and non-working external keys
3. Check API key generation code for default scope assignment
4. Expected if TRUE: External keys will have only read permissions
5. Expected if FALSE: Keys will have identical permissions regardless of user type

#### Code/Configuration to Check
```bash
# Check auth service for API key permissions
grep -r "hk_live_" ../hokusai-auth-service/src/
grep -r "scope" ../hokusai-auth-service/src/api_keys/
grep -r "read.*only\|readonly" ../hokusai-auth-service/

# Look for permission definitions
find ../hokusai-auth-service -name "*.py" -o -name "*.ts" | xargs grep -l "model:write\|model:read"

# Check API service middleware
grep -r "403\|Forbidden" ./src/api/
grep -r "permission\|scope\|role" ./src/api/middleware/
```

#### Quick Fix Test
Manually update the API key's permissions in the database to include "model:write" scope and test if registration works.

---

### Hypothesis 2: Missing model:write Permission Check in Auth Middleware
**Confidence**: High (75%)
**Category**: Authorization Logic Issue

#### Description
The API service's authorization middleware is checking for a specific "model:write" or "mlflow:write" permission that isn't being granted to API keys, even though the keys might have general write permissions.

#### Supporting Evidence
- Specific endpoints failing (MLflow write operations)
- Consistent 403 errors
- Authentication passes but authorization fails
- Read endpoints work without issue

#### Why This Causes the Bug
The middleware protecting MLflow write endpoints may be checking for granular permissions (like "mlflow:write" or "model:register") that aren't included in the standard API key permission set. This creates a mismatch between what permissions are granted and what permissions are required.

#### Test Method
1. Examine the authorization middleware code in the API service
2. Identify exact permission strings being checked
3. Trace through a write request to see where it fails
4. Add debug logging to capture required vs provided permissions
5. Expected if TRUE: Middleware checks for specific permission not in key
6. Expected if FALSE: Middleware uses different authorization mechanism

#### Code/Configuration to Check
```bash
# Check API service authorization
grep -r "model.*write\|mlflow.*write" ./src/api/
grep -r "permission.*check\|authorize\|can.*write" ./src/api/

# Look for MLflow specific auth
find ./src -name "*auth*" -o -name "*permission*" | xargs grep -l "mlflow\|model"

# Check route definitions
grep -r "@.*auth\|@.*permission" ./src/api/routes/
```

#### Quick Fix Test
Temporarily modify the middleware to log required permissions without enforcing them, then attempt registration to see what permissions are being checked.

---

### Hypothesis 3: MLflow Proxy Incorrectly Filtering Write Operations
**Confidence**: Medium (50%)
**Category**: Proxy/Integration Issue

#### Description
The proxy layer between the API service and MLflow server is incorrectly intercepting and blocking write operations, possibly due to misconfigured routing rules or overly restrictive security policies.

#### Supporting Evidence
- MLflow is accessed through a proxy (registry.hokus.ai/api/mlflow)
- Only write operations are affected
- Read operations pass through successfully

#### Why This Causes the Bug
If the proxy layer has its own authorization logic or request filtering, it might be configured to block POST/PUT requests to MLflow endpoints for external API keys, regardless of the actual permissions assigned to those keys.

#### Test Method
1. Check proxy configuration in the API service
2. Test direct MLflow access (bypassing proxy) if possible
3. Review ALB routing rules for registry.hokus.ai
4. Examine proxy middleware for request filtering logic
5. Expected if TRUE: Proxy code contains write operation filtering
6. Expected if FALSE: Proxy passes all authenticated requests through

#### Code/Configuration to Check
```bash
# Check proxy configuration
grep -r "mlflow.*proxy\|proxy.*mlflow" ./src/
grep -r "registry\.hokus\.ai" ./src/

# Infrastructure routing
grep -r "registry" ../hokusai-infrastructure/environments/
grep -r "mlflow" ../hokusai-infrastructure/environments/

# Check for request method filtering
grep -r "POST\|PUT\|DELETE" ./src/api/ | grep -i "forbid\|deny\|block"
```

#### Quick Fix Test
If possible, test the same API key directly against the internal MLflow service URL (mlflow.hokusai-development.local:5000) to bypass the proxy layer.

---

### Hypothesis 4: Role-Based Access Control Restricts Third-Party Users
**Confidence**: Medium (45%)
**Category**: Role/User Type Issue

#### Description
Third-party users are assigned a different role (e.g., "external_user" vs "internal_user") that has inherent restrictions on model registration, regardless of API key permissions.

#### Supporting Evidence
- Issue specifically affects third-party users
- Internal users may not experience the same problem
- Consistent behavior across all external API keys

#### Why This Causes the Bug
The system may have role-based access control where certain operations (like model registration) are restricted to specific user roles. Even with proper API key permissions, the user's role might override and restrict access.

#### Test Method
1. Check user role assignment in auth service
2. Compare roles between internal and external users
3. Look for role-based checks in the authorization flow
4. Test with an internal user's API key
5. Expected if TRUE: External users have restrictive role
6. Expected if FALSE: No role-based distinction in permissions

#### Code/Configuration to Check
```bash
# Check role definitions
grep -r "role\|user_type\|external\|third.*party" ../hokusai-auth-service/

# Look for role-based authorization
grep -r "check.*role\|role.*permission" ./src/api/
grep -r "internal\|external" ./src/api/middleware/
```

#### Quick Fix Test
Temporarily assign an internal role to the third-party user account and test if model registration works.

---

### Hypothesis 5: Recent Auth Service Deployment Changed Default Permissions
**Confidence**: Low (25%)
**Category**: Deployment/Configuration Drift

#### Description
A recent deployment to the auth service inadvertently changed the default permission set for new API keys, removing write permissions that were previously included.

#### Supporting Evidence
- Bug was recently discovered
- May correlate with recent deployments
- Affects newly created keys

#### Why This Causes the Bug
Configuration changes, environment variable updates, or code changes in a recent deployment could have modified the default permission template used when generating new API keys.

#### Test Method
1. Check deployment history for auth service
2. Review recent commits to auth service repository
3. Compare current vs previous permission configurations
4. Test with an older API key if available
5. Expected if TRUE: Recent commits show permission changes
6. Expected if FALSE: No recent changes to permission logic

#### Code/Configuration to Check
```bash
# Check recent auth service changes
cd ../hokusai-auth-service && git log --since="2 weeks ago" --grep="permission\|scope\|api.*key"

# Check for environment variable changes
git diff HEAD~10 HEAD -- "*.env*" "*config*"

# Review deployment logs
aws logs tail /ecs/hokusai-auth-development --since 7d | grep -i "deploy\|permission"
```

#### Quick Fix Test
Roll back auth service to previous version and test API key generation.

---

## Testing Priority Order

1. Start with Hypothesis 1 because it's the most straightforward - checking database permissions directly will quickly confirm if keys lack write scope
2. If Hypothesis 1 is false, test Hypothesis 2 because middleware permission checks are the next most likely authorization point
3. Test Hypothesis 3 if permissions look correct but requests still fail at the proxy layer
4. Test Hypothesis 4 if permissions appear correct but role-based restrictions might apply
5. Test Hypothesis 5 last as it requires deployment history analysis

## Alternative Hypotheses to Consider if All Above Fail

- CORS or cross-origin restrictions blocking write operations
- Rate limiting specifically on write endpoints
- Database connection pool exhaustion for write operations
- MLflow server configuration restricting external writes
- Network security groups or firewall rules blocking POST requests
- API Gateway or ALB rules filtering HTTP methods
- Token expiration handling differs for write operations

## Data Needed for Further Investigation

If initial hypotheses don't pan out, gather:
- Full request/response headers for failed write operations
- Complete auth service logs during API key creation
- MLflow server configuration files
- Database audit logs for permission checks
- Network traces showing the full request path
- Comparison with successful internal API key usage
- Load balancer access logs for 403 responses