# Critical Routing Discovery - Auth Service Impact

## Critical Finding

**Both `auth.hokus.ai` and `registry.hokus.ai` point to the SAME Application Load Balancer (ALB)**:
- ALB: `hokusai-development-794046971.us-east-1.elb.amazonaws.com`
- IPs: 34.239.97.120, 98.83.190.138, 3.95.46.121

This means our ALB routing rules affect BOTH domains!

## Current Routing Analysis

### What We Found

1. **No Host-Based Rules for auth.hokus.ai**
   - Only `registry.hokus.ai` has host-based routing rules
   - `auth.hokus.ai` traffic falls through to the default rules

2. **The `/api*` Rule Catches Auth Service Traffic**
   - Priority 100: `/api*` → API Target Group
   - This means `auth.hokus.ai/api/v1/keys/*` goes to the API service
   - The API service must be running the auth service endpoints

3. **Auth Service is Responding**
   - `curl https://auth.hokus.ai/` returns auth service info
   - `curl https://auth.hokus.ai/api/v1/keys/validate` returns 401 (expected)
   - Auth service IS working through the current routing

## Impact of Changing `/api*` to `/api/v1/*`

### CRITICAL RISK IDENTIFIED

If we change the routing from `/api*` to `/api/v1/*`:
- ✅ `registry.hokus.ai/api/v1/*` - Would still work
- ✅ `registry.hokus.ai/api/mlflow/*` - Would be fixed (our goal)
- ❌ `auth.hokus.ai/api/v1/*` - **WOULD BREAK** (no longer caught by any rule)

### Why This Would Break Auth

1. `auth.hokus.ai` has no specific routing rules
2. Currently relies on the catch-all `/api*` rule
3. Changing to `/api/v1/*` would cause auth requests to fall through to default
4. Default likely goes to a different service or returns 404

## Safe Solution Options

### Option 1: Add Host-Based Rules for Auth Service
```hcl
resource "aws_lb_listener_rule" "auth_api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 80  # Higher than other rules
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  
  condition {
    host_header {
      values = ["auth.hokus.ai"]
    }
  }
  
  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}
```

### Option 2: Keep `/api*` but Add Higher Priority Exception
```hcl
# Add this BEFORE changing the main rule
resource "aws_lb_listener_rule" "api_mlflow_exception" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 90  # Higher than 100
  
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

### Option 3: Create Separate Auth Service Infrastructure
- Deploy auth service to its own target group
- Add proper routing rules for auth.hokus.ai
- This is the cleanest long-term solution

## Recommendation

**DO NOT proceed with changing `/api*` to `/api/v1/*` without first:**

1. **Adding explicit routing for auth.hokus.ai** (Option 1)
2. **OR keeping the `/api*` rule** and just adding the MLflow exception (Option 2)
3. **Testing thoroughly** that auth service still works

## Testing Commands

```bash
# Before ANY changes - save these baselines
curl -s https://auth.hokus.ai/api/v1/keys/validate -X POST -H "Content-Type: application/json" -d '{"api_key": "test"}' -w "\nStatus: %{http_code}\n"

curl -s https://registry.hokus.ai/api/v1/dspy/health -w "\nStatus: %{http_code}\n"

curl -s https://registry.hokus.ai/api/mlflow/health -w "\nStatus: %{http_code}\n"

# After changes - all should return same status codes
```

## Conclusion

The original `/api*` rule was likely added specifically to handle auth.hokus.ai traffic. Removing or changing it without adding auth-specific rules would break authentication for the entire platform.