# Migration Status Report

## Current State

The ECS services are currently deployed and running but are using the old target groups:

- **API Service**: Using `hokusai-api-ded2-dev` target group
- **MLflow Service**: Using `hokusai-mlflow-ded2-dev` target group

## Required Actions

### 1. Update ECS Services to Use Centralized Target Groups

The services need to be updated to use the centralized infrastructure target groups:

- **API Service**: Should use `hokusai-api-tg-development` (ARN: arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81)
- **MLflow Service**: Should use `hokusai-mlflow-tg-development` (ARN: arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-mlflow-tg-development/9518cac0d6af96bb)

To update the services, run:
```bash
cd infrastructure/terraform
./update-services-to-central-tg.sh
```

This script will:
1. Update the API service to use the centralized API target group
2. Update the MLflow service to use the centralized MLflow target group
3. Force a new deployment of both services

### 2. Clean Up Terraform Configuration

The terraform configuration has multiple duplicate resources from various updates. To clean this up:

1. **Backup current configuration**:
   ```bash
   mkdir -p terraform-backup
   cp infrastructure/terraform/*.tf terraform-backup/
   ```

2. **Remove duplicate files**:
   - Keep only the main configuration files
   - Remove the various *-fix.tf and *-updates.tf files after verifying their changes are incorporated

3. **Use remote state integration**:
   - The `remote-state.tf` file is already created to reference the centralized infrastructure

### 3. Enable Listener Rules

Once the services are updated to use the centralized target groups, the infrastructure team needs to:

1. Enable the listener rules in the centralized repository
2. Use the configuration from `listener-rules-for-infra-team.tf.example`

## Files Created for Migration

1. **`remote-state.tf`** - Configures access to centralized infrastructure state
2. **`update-services-to-central-tg.sh`** - Script to update ECS services to use centralized target groups
3. **`migrate-to-central-infra.sh`** - Alternative migration script using Terraform
4. **`listener-rules-for-infra-team.tf.example`** - Listener rules configuration for infrastructure team
5. **`MIGRATION_GUIDE.md`** - Detailed migration instructions
6. **`ecs-services-updated.tf.example`** - Example of updated ECS service configuration

## Verification Steps

After running the update script:

1. **Check service deployment status**:
   ```bash
   aws ecs describe-services --cluster hokusai-development --services hokusai-api hokusai-mlflow \
     --query 'services[*].[serviceName,deployments[0].status]' --output table
   ```

2. **Verify target group health**:
   ```bash
   # API target group
   aws elbv2 describe-target-health \
     --target-group-arn arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81

   # MLflow target group  
   aws elbv2 describe-target-health \
     --target-group-arn arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-mlflow-tg-development/9518cac0d6af96bb
   ```

3. **Test endpoints** (after listener rules are enabled):
   - API: https://hokusai-dp-development-465790699.us-east-1.elb.amazonaws.com/api/health
   - MLflow: https://hokusai-dp-development-465790699.us-east-1.elb.amazonaws.com/mlflow

## Summary

The infrastructure is ready for migration. The key step is running the `update-services-to-central-tg.sh` script to point the ECS services to the centralized target groups. Once this is done and the infrastructure team enables the listener rules, the migration will be complete.