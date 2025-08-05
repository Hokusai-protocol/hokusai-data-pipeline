# Implementation Tasks - Fix MLflow Routing Configuration

## 1. [ ] Analyze Current ALB Configuration
   a. [ ] Identify the correct ALB (registry.hokus.ai)
   b. [ ] Review existing listener rules and priorities
   c. [ ] Check current target groups configuration
   d. [ ] Document current routing paths to avoid conflicts

## 2. [ ] Configure ALB Listener Rules
   a. [ ] Add listener rule for `/api/mlflow/*` path pattern
   b. [ ] Set forward action to MLflow target group
   c. [ ] Configure appropriate rule priority
   d. [ ] Apply changes via AWS console or CLI

## 3. [ ] Verify Target Group Configuration
   a. [ ] Check MLflow target group exists
   b. [ ] Verify port configuration (8000)
   c. [ ] Confirm health check path and settings
   d. [ ] Ensure target group has registered targets

## 4. [ ] Update Security Groups
   a. [ ] Check ALB security group outbound rules
   b. [ ] Verify ECS task security group inbound rules for port 8000
   c. [ ] Add missing rules if needed
   d. [ ] Document security group changes

## 5. [ ] Apply Terraform Configuration (Dependent on 2, 3, 4)
   a. [ ] Review infrastructure/terraform/alb-listener-rules.tf
   b. [ ] Update terraform files with new routing rules
   c. [ ] Run terraform plan to preview changes
   d. [ ] Apply terraform changes

## 6. [ ] Test MLflow Proxy Endpoints (Dependent on 5)
   a. [ ] Test GET `/api/mlflow/api/2.0/mlflow/experiments/search`
   b. [ ] Test POST `/api/mlflow/api/2.0/mlflow/experiments/create`
   c. [ ] Test POST `/api/mlflow/api/2.0/mlflow/runs/create`
   d. [ ] Test POST `/api/mlflow/api/2.0/mlflow/runs/log-metric`
   e. [ ] Test POST `/api/mlflow/api/2.0/mlflow/model-versions/create`

## 7. [ ] Verify Model Registration Flow (Dependent on 6)
   a. [ ] Run test_model_registration_flow.py
   b. [ ] Test with a valid API key
   c. [ ] Verify all stages complete successfully
   d. [ ] Check model appears in MLflow registry

## 8. [ ] Documentation
   a. [ ] Document ALB routing configuration
   b. [ ] Update README with MLflow endpoint information
   c. [ ] Create troubleshooting guide for common issues
   d. [ ] Document rollback procedure if needed