# Terraform Deployment Fix

## Issues Found

1. **Priority Conflicts**: The existing `aws_lb_listener_rule.api` uses priority 100, which conflicts with our new rule
   - Fixed: Changed new rules to use priority 95 instead

2. **S3 Bucket Lifecycle**: The plan shows issues with S3 bucket having `prevent_destroy = true`
   - This appears to be unrelated to our routing changes

## Deployment Approach

### Option 1: Targeted Apply (Recommended)
Apply only the routing rules to avoid unrelated changes:

```bash
# Apply only the new routing rules
terraform apply \
  -target=aws_lb_listener_rule.auth_service_api \
  -target=aws_lb_listener_rule.api_mlflow_proxy \
  -target=aws_lb_listener_rule.api_v1 \
  -target=aws_lb_listener_rule.https_auth_service_api \
  -target=aws_lb_listener_rule.https_api_mlflow_proxy \
  -target=aws_lb_listener_rule.https_api_v1
```

### Option 2: Fix All Issues
If you want to address all issues in the plan:

1. **Password Change**: The RDS password appears to be changing. If intentional, proceed. If not, check your secrets.

2. **Task Definition**: The ECS task definition is reverting from :31 to :30. You may want to update this separately.

3. **S3 Bucket**: If the S3 bucket error persists, you may need to refresh state:
   ```bash
   terraform refresh
   ```

## Verification After Apply

After applying the routing rules:

```bash
# Check ALB rules were created
aws elbv2 describe-rules \
  --listener-arn $(terraform output -raw http_listener_arn) \
  --query 'Rules[?Priority==`80`||Priority==`90`||Priority==`95`].[Priority,Conditions[0]]' \
  --output table

# Test auth service
curl -I https://auth.hokus.ai/api/v1/keys/validate

# Test new MLflow routing (after API deployment)
curl -I https://registry.hokus.ai/api/mlflow/health/mlflow \
  -H "Authorization: Bearer $HOKUSAI_API_KEY"
```

## Current ALB Rule Priorities

After deployment, you'll have:
- Priority 40: registry.hokus.ai + /mlflow/*
- Priority 50: registry.hokus.ai + /* (catch-all)
- Priority 80: auth.hokus.ai + /api/* (NEW)
- Priority 90: /api/mlflow/* (NEW)
- Priority 95: /api/v1/*, /api/health, /api/health/* (NEW)
- Priority 100: /api* (OLD - to be removed later)
- Priority 200: /mlflow/*

The new rules at priorities 80, 90, and 95 will take precedence over the old rule at 100.