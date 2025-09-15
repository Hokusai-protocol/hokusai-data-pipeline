# Root Cause Analysis: Problems Registering Model

## Executive Summary
Third-party users cannot register models because the API service lacks authorization checks for write operations. While the authentication middleware successfully validates API keys and retrieves permission scopes, it never verifies if those scopes permit the requested operation.

## Root Cause
**Missing Authorization Logic in API Middleware**

The `APIKeyAuthMiddleware` in `src/middleware/auth.py` performs authentication but not authorization:
- ✅ Validates API keys with the auth service
- ✅ Retrieves user permission scopes
- ✅ Stores scopes in request state
- ❌ **Never checks if scopes permit the operation**

## Technical Explanation

### Current Flow
1. User sends request with API key to register a model (POST /api/mlflow/...)
2. `APIKeyAuthMiddleware` validates the key with auth service
3. Auth service returns validation with scopes: `["model:read", "model:write", "mlflow:access"]`
4. Middleware stores scopes in `request.state.scopes`
5. **BUG**: Middleware allows ALL authenticated requests through
6. Request is proxied to MLflow without permission checks
7. MLflow (or another downstream service) returns 403 if user lacks permissions

### Expected Flow
1. User sends request with API key to register a model
2. Middleware validates the key
3. Middleware checks if operation requires write scope
4. Middleware verifies user has required scope
5. Only if authorized, forward to MLflow
6. Return 403 immediately if unauthorized

## Why It Wasn't Caught Earlier

### Design Assumptions
- The system was likely designed assuming MLflow would handle authorization
- Or it assumed all authenticated users would have write permissions
- The separation between authentication and authorization wasn't clearly defined

### Testing Gaps
- No integration tests for permission-based access control
- No tests verifying that read-only keys cannot perform write operations
- Internal users likely all have write permissions, masking the issue

## Impact Assessment

### Affected Users
- All third-party/external users trying to register models
- New users onboarding to the platform
- CI/CD pipelines using API keys for model deployment

### Business Impact
- Blocks core platform functionality for external contributors
- Prevents model marketplace growth
- May cause customer churn if not resolved quickly

### Security Considerations
- Current bug is "fail-secure" - it blocks access rather than allowing it
- Fix must ensure proper authorization without creating security holes
- Need to maintain audit trail of authorization decisions

## Related Code Sections

### Files Requiring Changes
1. `src/middleware/auth.py` - Add scope checking logic
2. `src/api/routes/mlflow_proxy.py` - Add write operation detection
3. `src/api/routes/mlflow_proxy_improved.py` - Add write operation detection

### Specific Locations
- `src/middleware/auth.py:227-319` - dispatch() method needs scope validation
- `src/api/routes/mlflow_proxy_improved.py:185-188` - Route handler needs permission decorator

## Prevention Measures

### Immediate
- Add authorization checks to middleware
- Create permission decorators for routes
- Implement scope validation for MLflow write operations

### Long-term
- Establish clear authentication vs authorization boundaries
- Add integration tests for permission scenarios
- Document permission model for developers
- Implement role-based access control (RBAC) properly

## Similar Issues to Check
- Other write operations may have same issue
- Model deletion endpoints
- Experiment creation endpoints
- Artifact upload endpoints
- Admin operations