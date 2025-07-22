# Hokusai API Routing Solution Design

## Critical Constraint: MLflow API Paths Are Fixed

After thorough investigation, MLflow clients have **hardcoded API paths** that cannot be modified:
- MLflow clients ALWAYS call `/api/2.0/mlflow/*` endpoints
- These paths are hardcoded in the MLflow Python/R/Java client libraries
- There is no configuration option to change these paths

This means **Option 2 (changing MLflow paths) is not viable**.

## Revised Solution Analysis

### Option 1: Make ALB Rules More Specific ✅ RECOMMENDED

**Changes Required:**
- Update ALB routing rule from `/api*` to `/api/v1/*` (or other specific paths)
- This allows `/api/mlflow/*` to pass through to a different target

**Pros:**
- Solves the routing conflict definitively
- Aligns with MLflow client expectations
- Enables proper API versioning
- Clean separation of concerns

**Cons:**
- Requires identifying all current API paths
- May need migration for unversioned API users
- Requires Terraform deployment

**Implementation:**
1. Audit all current `/api/*` endpoints
2. Update ALB rule to be more specific (e.g., `/api/v1/*`)
3. Add new rule for `/api/mlflow/*` → API service (which proxies to MLflow)

### Option 2: ~~Change MLflow Proxy Paths~~ ❌ NOT POSSIBLE

This option is not viable because MLflow clients have hardcoded paths.

### Option 3: Current Workaround (Status Quo) ⚠️ TEMPORARY

**Current State:**
- Clients must use `/mlflow/*` directly
- This bypasses the `/api*` conflict
- Requires custom client configuration

**Problems:**
- Non-standard for MLflow clients
- Requires all clients to override MLFLOW_TRACKING_URI
- Confusing and error-prone

## Critical Update: Auth Service Discovery

**IMPORTANT**: Both `auth.hokus.ai` and `registry.hokus.ai` point to the same ALB. The current `/api*` rule is required for auth service to work. Changing it without adding auth-specific rules would break authentication.

## Recommended Implementation Plan

### Phase 1: Immediate Fix
1. **Add auth service routing rules first**
   - Priority 80: `auth.hokus.ai` + `/api/*` → API Target Group
   - This preserves auth service functionality

2. **Document current workaround clearly**
   - Users must set `MLFLOW_TRACKING_URI=http://registry.hokus.ai/mlflow`
   - This bypasses the routing conflict

2. **Prepare for Phase 2**
   - Audit all existing `/api/*` endpoints
   - Identify which paths are actually in use
   - Plan migration strategy

### Phase 2: Permanent Solution
1. **Update ALB routing rules:**
```hcl
# Replace broad /api* rule with specific paths
resource "aws_lb_listener_rule" "api_v1" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 100
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    path_pattern {
      values = [
        "/api/v1/*",
        "/api/health",
        "/api/health/*",
        "/api/models",
        "/api/models/*",
        "/api/dspy",
        "/api/dspy/*"
      ]
    }
  }
}

# Add specific rule for MLflow proxy
resource "aws_lb_listener_rule" "api_mlflow_proxy" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 90  # Higher priority than api_v1
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    path_pattern {
      values = ["/api/mlflow/*"]
    }
  }
}
```

2. **Update API to handle `/api/mlflow/*` routing:**
```python
# In src/api/main.py - add second mount point
app.include_router(mlflow_proxy.router, prefix="/api/mlflow", tags=["mlflow"])
```

3. **The proxy already handles path translation:**
   - Receives: `/api/mlflow/api/2.0/mlflow/*`
   - Translates to: `ajax-api/2.0/mlflow/*` for the MLflow server

### Phase 3: Migration
1. **Announce the fix to users**
2. **Update documentation to show standard MLflow configuration:**
   ```python
   # Standard MLflow configuration will work after fix
   os.environ["MLFLOW_TRACKING_URI"] = "http://registry.hokus.ai/api/mlflow"
   ```
3. **Maintain backward compatibility** - keep `/mlflow/*` working
4. **Monitor usage** and deprecate `/mlflow/*` path after migration period

## Benefits of Recommended Approach

1. **Standards Compliance**: MLflow clients can use their default paths
2. **No Client Changes**: Once deployed, standard MLflow configuration works
3. **Clear API Structure**: Proper versioning and path organization
4. **Backward Compatible**: Existing `/mlflow/*` paths continue to work

## Implementation Priority

1. **High Priority**: Update ALB rules to be more specific
2. **Medium Priority**: Add `/api/mlflow/*` mount point in API
3. **Low Priority**: Deprecate direct `/mlflow/*` access (after migration)

This solution respects MLflow's constraints while fixing the routing conflict properly.