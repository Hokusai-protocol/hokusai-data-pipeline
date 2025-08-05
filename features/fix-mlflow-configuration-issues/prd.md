# Product Requirements Document - Fix MLflow Routing Configuration

## Objectives

Get MLflow model registration working by fixing ALB routing configuration. Currently all `/api/mlflow/*` endpoints return 404 errors because ALB listener rules are missing.

## Personas

**Data Scientists**: Need working MLflow endpoints to register models.

**Third-party Developers**: Require functional MLflow API access.

## Success Criteria

1. MLflow API endpoints (`/api/mlflow/*`) respond with 200/201 instead of 404
2. Model registration workflow completes successfully
3. MLflow proxy forwards requests correctly to MLflow service

## Technical Requirements

### ALB Routing Fix

Add listener rules to Application Load Balancer:
- Configure `/api/mlflow/*` path pattern
- Forward to MLflow target group on port 8000
- Apply to registry.hokus.ai ALB

### Security Groups

Ensure traffic can flow:
- ALB can reach ECS tasks on port 8000
- ECS tasks accept traffic from ALB

### MLflow Service

Verify service is running:
- Container listening on port 8000
- Health checks configured correctly

## Implementation Tasks

### Configure ALB Routing

1. Identify correct ALB for registry.hokus.ai
2. Add listener rule for `/api/mlflow/*` paths
3. Point to MLflow target group
4. Apply configuration immediately

### Verify Security Groups

1. Check ALB security group egress rules
2. Check ECS security group ingress rules
3. Update as needed for port 8000

### Test MLflow Endpoints

1. Test `/api/mlflow/api/2.0/mlflow/experiments/search`
2. Test `/api/mlflow/api/2.0/mlflow/runs/create`
3. Test `/api/mlflow/api/2.0/mlflow/model-versions/create`
4. Verify model registration works end-to-end

## Constraints

None - service is not operational, so changes can be applied immediately.

## Dependencies

- AWS console or CLI access for ALB configuration
- Terraform files for infrastructure as code
- MLflow service running in ECS