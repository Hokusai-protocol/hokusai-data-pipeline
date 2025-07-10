# Deployment Fix - Infrastructure Prerequisites

## Issue Summary
The GitHub Actions deployment workflow was failing because it expected infrastructure components (ECS task definitions, services) to exist, but they hadn't been deployed yet.

## Root Cause
The deployment workflow assumes all infrastructure is already deployed:
- ECS cluster: `hokusai-development`
- Task definitions: `hokusai-api-development`, `hokusai-mlflow-development`
- ECS services: `hokusai-api`, `hokusai-mlflow`

However, these resources don't exist until the Terraform infrastructure is deployed.

## Fix Applied
Modified `.github/workflows/deploy.yml` to:
1. Check if infrastructure exists before attempting deployment
2. Skip missing components gracefully with clear warning messages
3. Provide instructions for deploying missing infrastructure
4. Continue with partial deployments when possible

## How to Deploy Infrastructure

### Prerequisites
1. AWS credentials configured
2. Required environment variables:
   ```bash
   export AWS_REGION=us-east-1
   export ENVIRONMENT=development
   export DATABASE_PASSWORD=<secure-password>
   export API_SECRET_KEY=<secure-key>
   ```

### Deploy Infrastructure
```bash
cd infrastructure
./scripts/deploy.sh
```

This script will:
1. Initialize Terraform
2. Create all AWS resources (VPC, ECS, RDS, etc.)
3. Build and push Docker images
4. Deploy ECS services

### After Infrastructure Deployment
The GitHub Actions workflow will work automatically for subsequent deployments.

## Deployment Workflow Behavior

### When infrastructure exists:
- Updates task definitions with new Docker images
- Deploys to ECS services
- Waits for services to stabilize

### When infrastructure is missing:
- Shows warning messages
- Provides specific terraform commands to deploy missing components
- Continues with available services
- Exits successfully (not as failure) to allow PR merges

## Manual Deployment Options

### Deploy only specific components:
```bash
# Deploy only API infrastructure
terraform apply -target=aws_ecs_task_definition.api -target=aws_ecs_service.api

# Deploy only MLflow infrastructure  
terraform apply -target=aws_ecs_task_definition.mlflow -target=aws_ecs_service.mlflow
```

### Check what exists:
```bash
# Check ECS cluster
aws ecs describe-clusters --clusters hokusai-development

# Check task definitions
aws ecs describe-task-definition --task-definition hokusai-api-development
aws ecs describe-task-definition --task-definition hokusai-mlflow-development

# Check services
aws ecs describe-services --cluster hokusai-development --services hokusai-api hokusai-mlflow
```

## Next Steps
1. Deploy the infrastructure using `infrastructure/scripts/deploy.sh`
2. Subsequent GitHub Actions deployments will work automatically
3. Monitor the deployment logs for any issues