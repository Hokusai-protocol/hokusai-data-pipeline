# Routing Fix Deployment Guide

## Overview

This guide describes how to deploy the routing fix that resolves the `/api*` catch-all conflict preventing MLflow access via `/api/mlflow/*` paths.

## ⚠️ CRITICAL WARNING

The current `/api*` rule is REQUIRED for `auth.hokus.ai` to function. Both `auth.hokus.ai` and `registry.hokus.ai` point to the same ALB. DO NOT remove the old `/api*` rule without first deploying the new auth-specific routing rules.

## Pre-Deployment Checklist

- [ ] Review all changes in this branch
- [ ] Verify Terraform has correct AWS credentials
- [ ] Confirm you have deployment permissions
- [ ] Schedule deployment window (minimal downtime expected)

## Deployment Steps

### Step 1: Deploy New Routing Rules

1. **Review the new Terraform configuration:**
   ```bash
   cd infrastructure/terraform
   cat routing-fix.tf
   ```

2. **Plan the Terraform changes:**
   ```bash
   terraform plan -out=routing-fix.plan
   ```

3. **Review the plan carefully:**
   - New rules should be created at priorities 80, 90 and 100
   - Priority 80: auth.hokus.ai routing (CRITICAL)
   - Priority 90: /api/mlflow/* routing
   - Priority 100: /api/v1/* routing
   - Old rules should remain unchanged (for now)
   - No resources should be destroyed

4. **Apply the new rules:**
   ```bash
   terraform apply routing-fix.plan
   ```

### Step 2: Deploy API Code Changes

1. **Build and push new API container:**
   ```bash
   docker build -t hokusai-api:routing-fix .
   docker tag hokusai-api:routing-fix <your-ecr-repo>/hokusai-api:routing-fix
   docker push <your-ecr-repo>/hokusai-api:routing-fix
   ```

2. **Update ECS task definition** to use the new image

3. **Deploy the new task definition** (rolling update)

### Step 3: Verify Deployment

1. **Run the routing test script:**
   ```bash
   export HOKUSAI_API_KEY="your_test_key"
   python test_routing_behavior.py
   ```

2. **Test specific endpoints:**
   ```bash
   # Should now work (was broken before)
   curl http://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search \
     -H "Authorization: Bearer $HOKUSAI_API_KEY"
   
   # Should still work (backward compatibility)
   curl http://registry.hokus.ai/mlflow/api/2.0/mlflow/experiments/search \
     -H "Authorization: Bearer $HOKUSAI_API_KEY"
   ```

3. **Run model registration test:**
   ```bash
   python test_real_registration.py
   ```

### Step 4: Remove Old Rules (Optional)

After confirming everything works:

1. **Comment out old rules in Terraform:**
   - In `main.tf`: Comment out `aws_lb_listener_rule.api`
   - In `https-updates.tf`: Comment out `aws_lb_listener_rule.https_api`

2. **Apply changes:**
   ```bash
   terraform plan
   terraform apply
   ```

## Rollback Plan

If issues occur:

### Quick Rollback (API only):
1. Revert ECS task definition to previous version
2. The old `/mlflow/*` paths will continue to work

### Full Rollback:
1. Remove the new Terraform rules:
   ```bash
   terraform destroy -target=aws_lb_listener_rule.api_v1
   terraform destroy -target=aws_lb_listener_rule.api_mlflow_proxy
   ```
2. Revert API code changes

## Post-Deployment

### Update Documentation
- Update public docs to show standard MLflow configuration
- Remove workaround notices
- Update integration guides

### Notify Users
Send notification about the fix:
```
Subject: MLflow API Routing Fix Deployed

The routing issue affecting MLflow access via /api/mlflow/* paths has been resolved.

You can now use the standard MLflow configuration:
- MLFLOW_TRACKING_URI = http://registry.hokus.ai/api/mlflow
- MLFLOW_TRACKING_TOKEN = your_api_key

The legacy /mlflow/* paths continue to work for backward compatibility.
```

### Monitor
- Watch ALB metrics for any 404 errors
- Monitor MLflow proxy logs
- Check for any authentication issues

## Testing Endpoints

### Health Checks
```bash
# API health
curl http://registry.hokus.ai/health

# MLflow health (both should work)
curl http://registry.hokus.ai/api/mlflow/health/mlflow -H "Authorization: Bearer $API_KEY"
curl http://registry.hokus.ai/mlflow/health/mlflow
```

### MLflow API
```bash
# Standard path (newly fixed)
curl http://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search \
  -H "Authorization: Bearer $API_KEY"

# Legacy path (still works)
curl http://registry.hokus.ai/mlflow/api/2.0/mlflow/experiments/search \
  -H "Authorization: Bearer $API_KEY"
```

## Troubleshooting

### "404 Not Found" on /api/mlflow/*
- Check if new ALB rules are active: `aws elbv2 describe-rules`
- Verify API deployment has the new code
- Check ALB target health

### "502 Bad Gateway"
- MLflow backend may be down
- Check MLflow container logs
- Verify MLflow target group health

### "403 Forbidden"
- API key authentication issue
- Verify API key is valid
- Check auth middleware logs

## Success Criteria

The deployment is successful when:
1. `/api/mlflow/*` paths return 200 (not 404)
2. `test_real_registration.py` completes successfully
3. Standard MLflow client configuration works
4. No increase in error rates
5. Backward compatibility maintained