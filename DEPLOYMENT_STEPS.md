# Step-by-Step Deployment Guide for Routing Fix

## Pre-Deployment Checklist

- [ ] Confirm you have AWS credentials configured
- [ ] Verify Terraform access to the AWS account
- [ ] Have an API key ready for testing
- [ ] Schedule a maintenance window (low-risk, but good practice)

## Phase 1: Deploy Infrastructure Changes (Terraform)

### Step 1: Review Changes
```bash
cd infrastructure/terraform

# Review the new routing rules
cat routing-fix.tf

# Key changes to verify:
# - Priority 80: auth.hokus.ai + /api/* (CRITICAL - preserves auth)
# - Priority 90: /api/mlflow/* (fixes MLflow routing)
# - Priority 100: /api/v1/* (replaces broad /api*)
```

### Step 2: Plan Terraform Changes
```bash
# Initialize Terraform if needed
terraform init

# Create a plan
terraform plan -out=routing-fix.plan

# Review the plan output carefully
# You should see:
# - 4 new aws_lb_listener_rule resources to be created
# - NO resources to be destroyed (critical!)
```

### Step 3: Apply Infrastructure Changes
```bash
# Apply the plan
terraform apply routing-fix.plan

# This creates new rules but keeps old ones
# Zero downtime - both old and new paths work
```

### Step 4: Verify ALB Rules
```bash
# Check that new rules are active
aws elbv2 describe-rules \
  --listener-arn <your-listener-arn> \
  --query 'Rules[?Priority==`80`||Priority==`90`||Priority==`100`].[Priority,Conditions,Actions]' \
  --output table
```

## Phase 2: Deploy API Code Changes

### Step 1: Build and Push Docker Image
```bash
# From repository root
docker build -t hokusai-api:routing-fix .

# Tag for your ECR repository
docker tag hokusai-api:routing-fix <account-id>.dkr.ecr.<region>.amazonaws.com/hokusai-api:routing-fix

# Push to ECR
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/hokusai-api:routing-fix
```

### Step 2: Update ECS Task Definition
```bash
# Update the task definition to use new image
# This can be done via AWS Console or CLI
# Key change: /api/mlflow mount point added in src/api/main.py
```

### Step 3: Deploy ECS Service Update
```bash
# Update service with new task definition
aws ecs update-service \
  --cluster <your-cluster> \
  --service hokusai-api \
  --task-definition <new-task-definition-arn>

# Monitor deployment
aws ecs wait services-stable \
  --cluster <your-cluster> \
  --services hokusai-api
```

## Phase 3: Verification Testing

### Step 1: Test Auth Service (CRITICAL)
```bash
# Auth MUST continue working
curl -X POST https://auth.hokus.ai/api/v1/keys/validate \
  -H "Content-Type: application/json" \
  -d '{"api_key": "test"}' \
  -w "\nStatus: %{http_code}\n"

# Expected: 401 (NOT 404!)
```

### Step 2: Test New MLflow Routing
```bash
# This should now work (was 404 before)
export HOKUSAI_API_KEY="your_api_key"

curl https://registry.hokus.ai/api/mlflow/health/mlflow \
  -H "Authorization: Bearer $HOKUSAI_API_KEY" \
  -w "\nStatus: %{http_code}\n"

# Expected: 200
```

### Step 3: Run Comprehensive Test
```bash
# Run the routing behavior test
python test_routing_behavior.py

# All tests should pass, especially:
# - Auth service endpoints
# - New /api/mlflow/* paths
# - Existing /mlflow/* paths (backward compatibility)
```

### Step 4: Test Model Registration
```bash
# Finally, test the original goal
python test_real_registration.py

# Should successfully register a model
```

## Phase 4: Cleanup Old Rules (OPTIONAL - After Verification)

**⚠️ ONLY do this after confirming everything works!**

### Step 1: Comment Out Old Rules
```hcl
# In main.tf, comment out:
# resource "aws_lb_listener_rule" "api" { ... }

# In https-updates.tf, comment out:
# resource "aws_lb_listener_rule" "https_api" { ... }
```

### Step 2: Apply Removal
```bash
terraform plan
# Verify it only destroys the old /api* rules

terraform apply
```

## Monitoring Post-Deployment

### What to Watch
1. **Auth Service Errors** - Any 404s on auth.hokus.ai would be critical
2. **MLflow Proxy Success Rate** - Should see traffic on /api/mlflow/*
3. **API Error Rates** - Should remain stable
4. **ECS Task Health** - All tasks should remain healthy

### Rollback Plan

If issues occur:

#### Quick Rollback (API only)
```bash
# Revert ECS task definition
aws ecs update-service \
  --cluster <your-cluster> \
  --service hokusai-api \
  --task-definition <previous-task-definition-arn>
```

#### Full Rollback (Including Terraform)
```bash
# Remove new rules (keeps old ones since we didn't delete them)
terraform destroy \
  -target=aws_lb_listener_rule.auth_service_api \
  -target=aws_lb_listener_rule.api_v1 \
  -target=aws_lb_listener_rule.api_mlflow_proxy \
  -target=aws_lb_listener_rule.https_auth_service_api \
  -target=aws_lb_listener_rule.https_api_v1 \
  -target=aws_lb_listener_rule.https_api_mlflow_proxy
```

## Success Criteria

The deployment is successful when:
- [ ] Auth service continues to work (no 404 errors)
- [ ] `/api/mlflow/*` returns 200 (not 404)
- [ ] Existing APIs continue to work
- [ ] `test_real_registration.py` completes successfully
- [ ] No increase in error rates

## Post-Deployment Communication

Send update to users:
```
Subject: MLflow Routing Fix Deployed

The routing issue preventing MLflow access via standard paths has been resolved.

What's New:
- Standard MLflow configuration now works: MLFLOW_TRACKING_URI=https://registry.hokus.ai/api/mlflow
- Legacy configuration still supported: MLFLOW_TRACKING_URI=https://registry.hokus.ai/mlflow

No action required if your integration is currently working. 
If you've been using the workaround, you can now switch to the standard configuration.
```