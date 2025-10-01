# ✅ ROOT CAUSE CONFIRMED: Missing HTTPS Listener Rules

## Critical Finding

**ROOT CAUSE:** The ALB listener rules for `/api/v1/*` paths are **ONLY configured for HTTP (port 80)**, NOT for HTTPS (port 443).

**Location:** `/Users/timothyogilvie/Dropbox/Hokusai/hokusai-infrastructure/terraform_module/data-pipeline/listeners.tf`

## Evidence

### The Problem

#### HTTPS Listener Configuration (lines 20-37):
```terraform
resource "aws_lb_listener" "main_https" {
  count = var.certificate_arn != "" ? 1 : 0

  load_balancer_arn = aws_lb.main.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = var.certificate_arn

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"      # ❌ RETURNS TEXT/PLAIN
      message_body = "Not Found"        # ❌ RETURNS "Not Found"
      status_code  = "404"              # ❌ RETURNS 404
    }
  }
}
```

**Problem:** The HTTPS listener has NO routing rules, so ALL requests fall through to the default action which returns a 404 with plain text "Not Found".

#### HTTP Listener Has the Rules (lines 184-202):
```terraform
resource "aws_lb_listener_rule" "api_v1" {
  listener_arn = aws_lb_listener.main_http.arn  # ✅ HTTP only!
  priority     = 95

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = [
        "/api/v1/*",          # ✅ This matches our path
        "/api/health",
        "/api/health/*"
      ]
    }
  }
}
```

**Problem:** This rule is attached to `main_http` listener (port 80) but NOT to `main_https` (port 443).

### Why This Causes the Bug

1. Third-party makes request to: `https://api.hokus.ai/api/v1/models/21/predict`
2. Request hits ALB on port 443 (HTTPS)
3. ALB checks `main_https` listener rules
4. NO rules match (because there are no rules defined!)
5. Falls through to default action
6. Returns 404 with "Not Found" plain text message

**This explains:**
- ✅ Why we get 404 errors
- ✅ Why responses might appear as "HTML" or non-JSON (actually plain text)
- ✅ Why the third party can't access Model ID 21

## Impact

### Current Impact
- **CRITICAL:** ALL API endpoints on HTTPS return 404
- This affects:
  - `/api/v1/models/*` (Model serving endpoints)
  - `/api/v1/*` (All v1 API endpoints)
  - `/api/health/*` (Health check endpoints)

### What Still Works
- HTTP requests (port 80) work fine
- But most clients use HTTPS by default
- Browsers and API clients typically use HTTPS

## The Fix

We need to add corresponding listener rules to the HTTPS listener. The fix is to duplicate all the HTTP listener rules for HTTPS.

### Required Changes in listeners.tf

Add these rules after the HTTP rules (around line 220):

```terraform
# HTTPS Routing Rules (mirroring HTTP rules)

# API v1 routing (HTTPS)
resource "aws_lb_listener_rule" "api_v1_https" {
  count = var.certificate_arn != "" ? 1 : 0

  listener_arn = aws_lb_listener.main_https[0].arn  # HTTPS listener
  priority     = 95

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = [
        "/api/v1/*",
        "/api/health",
        "/api/health/*"
      ]
    }
  }
}

# General API routing (HTTPS)
resource "aws_lb_listener_rule" "api_https" {
  count = var.certificate_arn != "" ? 1 : 0

  listener_arn = aws_lb_listener.main_https[0].arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api*"]
    }
  }
}

# MLflow proxy routing (HTTPS)
resource "aws_lb_listener_rule" "api_mlflow_proxy_https" {
  count = var.certificate_arn != "" ? 1 : 0

  listener_arn = aws_lb_listener.main_https[0].arn
  priority     = 85

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

# MLflow direct routing (HTTPS)
resource "aws_lb_listener_rule" "mlflow_https" {
  count = var.certificate_arn != "" ? 1 : 0

  listener_arn = aws_lb_listener.main_https[0].arn
  priority     = 200

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.mlflow.arn
  }

  condition {
    path_pattern {
      values = ["/mlflow", "/mlflow/*"]
    }
  }
}
```

## Why This Wasn't Caught Earlier

1. **No end-to-end tests:** Testing was likely done over HTTP (port 80) which works
2. **Local development uses HTTP:** Developers test locally without TLS
3. **Infrastructure review gap:** HTTPS rules weren't added when HTTP rules were created
4. **Implicit assumption:** Assumed rules would apply to both HTTP and HTTPS

## Verification Steps

After applying the fix:

1. **Check ALB listener rules:**
   ```bash
   aws elbv2 describe-rules \
     --listener-arn $(aws elbv2 describe-listeners \
       --load-balancer-arn <main-alb-arn> \
       --query 'Listeners[?Port==`443`].ListenerArn' \
       --output text)
   ```

2. **Test HTTPS endpoint:**
   ```bash
   curl -v https://api.hokus.ai/api/v1/models/21/info \
     -H "Authorization: Bearer <valid-api-key>"
   ```

3. **Verify response is JSON, not 404:**
   Expected: JSON response with model info or 401 if auth fails
   Not expected: 404 "Not Found" plain text

## Related Issues

This same pattern likely affects other ALBs:
- Check `auth_https` listener (lines 55-68) - has default forward, might be OK
- Check `registry_https` listener (lines 86-99) - has default forward, might be OK
- But verify all critical paths have explicit rules

## Files to Change

1. **Infrastructure:**
   - `/Users/timothyogilvie/Dropbox/Hokusai/hokusai-infrastructure/terraform_module/data-pipeline/listeners.tf`

2. **Tests to Add (in hokusai-data-pipeline):**
   - Integration test for HTTPS endpoint
   - Test for `/api/v1/models/21/info`
   - Test for `/api/v1/models/21/predict`
   - Test for `/api/v1/models/21/health`

3. **Documentation:**
   - API documentation confirming HTTPS endpoints
   - Update deployment checklist to verify HTTPS routing

## Priority

**P0 - CRITICAL:** This blocks ALL third-party API access over HTTPS, which is the standard protocol for API calls.

## Next Steps

1. ✅ Root cause identified
2. ⏭️ Create fix in infrastructure repository
3. ⏭️ Apply Terraform changes
4. ⏭️ Verify fix in production
5. ⏭️ Add integration tests
6. ⏭️ Update documentation
