# Data Pipeline Infrastructure Migration Guide

## Overview

This guide outlines the steps to complete the migration of the data pipeline infrastructure to use the centralized hokusai-infrastructure repository resources.

## Migration Steps

### Step 1: Deploy ECS Services (Completed)

The ECS services have been configured to use the centralized infrastructure resources. The following files have been created:

1. **remote-state.tf** - Configures access to the centralized infrastructure state
2. **ecs-services-updated.tf** - Updated ECS service definitions using centralized resources

The services will use the following target groups from the centralized infrastructure:
- API Service: `hokusai-api-tg-development` (ARN: arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81)
- MLflow Service: `hokusai-mlflow-tg-development` (ARN: arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-mlflow-tg-development/9518cac0d6af96bb)

### Step 2: Enable Listener Rules (In Progress)

The listener rules need to be enabled in the centralized infrastructure repository. The rules are currently disabled in the file:
`environments/data-pipeline-ecs-alb-integration.tf.disabled`

To enable them:
1. Navigate to the hokusai-infrastructure repository
2. Rename the file from `.tf.disabled` to `.tf`
3. Update any placeholder ARNs with the actual target group ARNs listed above
4. Run `terraform plan` to verify the changes
5. Run `terraform apply` to create the routing rules

### Step 3: Update Service Configuration (Pending)

After the listener rules are enabled, update the data pipeline terraform configuration:

1. **Disable old resources** - Comment out or remove the old ALB, target group, and listener definitions from main.tf
2. **Update service references** - Ensure all services reference the centralized infrastructure resources
3. **Test the configuration** - Run terraform plan to ensure no conflicts

## Terraform Commands

```bash
# Initialize terraform with backend configuration
terraform init -backend-config="bucket=hokusai-infrastructure-tfstate" \
               -backend-config="key=data-pipeline/terraform.tfstate" \
               -backend-config="region=us-east-1"

# Plan the changes
terraform plan

# Apply the updated configuration
terraform apply
```

## Verification Steps

1. **Check ECS Service Health**
   ```bash
   aws ecs describe-services --cluster hokusai-development \
     --services hokusai-api hokusai-mlflow
   ```

2. **Verify Target Group Health**
   ```bash
   aws elbv2 describe-target-health \
     --target-group-arn arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81
   ```

3. **Test Endpoints**
   - API Health: `https://hokusai-dp-development-465790699.us-east-1.elb.amazonaws.com/api/health`
   - MLflow: `https://hokusai-dp-development-465790699.us-east-1.elb.amazonaws.com/mlflow`

## Rollback Plan

If issues occur during migration:

1. Keep the original main.tf configuration as backup
2. Revert to using local ALB and target groups by commenting out remote-state.tf
3. Re-apply the original configuration

## Notes

- The registry ALB and auth target group were imported (not recreated) to preserve existing services
- All ALBs are configured with HTTPS listeners using the wildcard certificate
- HTTP traffic is automatically redirected to HTTPS
- The infrastructure is now managed by terraform in the centralized repository