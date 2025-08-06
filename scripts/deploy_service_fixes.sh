#!/bin/bash

# Deploy Service Degradation Fixes
# This script safely deploys the fixes for the registry service degradation issue

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT=${ENVIRONMENT:-development}
AWS_REGION=${AWS_REGION:-us-east-1}
CLUSTER_NAME="hokusai-${ENVIRONMENT}"
REGISTRY_SERVICE="hokusai-registry-api-${ENVIRONMENT}"
MLFLOW_SERVICE="hokusai-mlflow-${ENVIRONMENT}"

echo -e "${GREEN}=== Hokusai Registry Service Degradation Fix Deployment ===${NC}"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo ""

# Function to check service health
check_service_health() {
    local service_name=$1
    echo -e "${YELLOW}Checking health of $service_name...${NC}"
    
    # Get running task count
    RUNNING_TASKS=$(aws ecs describe-services \
        --cluster "$CLUSTER_NAME" \
        --services "$service_name" \
        --region "$AWS_REGION" \
        --query 'services[0].runningCount' \
        --output text)
    
    echo "Running tasks: $RUNNING_TASKS"
    
    if [ "$RUNNING_TASKS" -eq "0" ]; then
        echo -e "${RED}Warning: No running tasks for $service_name${NC}"
        return 1
    fi
    return 0
}

# Function to get ALB target health
check_alb_health() {
    local target_group_arn=$1
    echo -e "${YELLOW}Checking ALB target health...${NC}"
    
    HEALTHY_TARGETS=$(aws elbv2 describe-target-health \
        --target-group-arn "$target_group_arn" \
        --region "$AWS_REGION" \
        --query 'TargetHealthDescriptions[?TargetHealth.State==`healthy`] | length(@)' \
        --output text)
    
    echo "Healthy targets: $HEALTHY_TARGETS"
    
    if [ "$HEALTHY_TARGETS" -eq "0" ]; then
        echo -e "${RED}Warning: No healthy targets in ALB${NC}"
        return 1
    fi
    return 0
}

# Step 1: Backup current task definitions
echo -e "${GREEN}Step 1: Backing up current task definitions...${NC}"
aws ecs describe-task-definition \
    --task-definition "hokusai-registry-api-${ENVIRONMENT}" \
    --region "$AWS_REGION" \
    > backup/registry-task-def-$(date +%Y%m%d-%H%M%S).json

aws ecs describe-task-definition \
    --task-definition "hokusai-mlflow-${ENVIRONMENT}" \
    --region "$AWS_REGION" \
    > backup/mlflow-task-def-$(date +%Y%m%d-%H%M%S).json

echo "Backups created in backup/ directory"

# Step 2: Check current service status
echo -e "${GREEN}Step 2: Checking current service status...${NC}"
check_service_health "$REGISTRY_SERVICE"
check_service_health "$MLFLOW_SERVICE"

# Step 3: Deploy application code changes
echo -e "${GREEN}Step 3: Building and pushing Docker images...${NC}"

# Build registry API image with fixes
echo "Building registry API image..."
docker build -t hokusai-registry-api:fix-degradation \
    -f Dockerfile \
    --build-arg VERSION=fix-degradation \
    .

# Tag and push to ECR
ECR_REGISTRY=$(aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin)
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/hokusai-registry"

docker tag hokusai-registry-api:fix-degradation "${ECR_REPO}:fix-degradation"
docker tag hokusai-registry-api:fix-degradation "${ECR_REPO}:latest"
docker push "${ECR_REPO}:fix-degradation"
docker push "${ECR_REPO}:latest"

echo "Docker images pushed successfully"

# Step 4: Apply Terraform changes
echo -e "${GREEN}Step 4: Applying infrastructure updates...${NC}"
cd infrastructure/terraform

# Plan changes first
terraform plan \
    -var="environment=$ENVIRONMENT" \
    -out=tfplan

echo -e "${YELLOW}Review the above plan. Continue with apply? (y/n)${NC}"
read -r response
if [[ "$response" != "y" ]]; then
    echo "Deployment cancelled"
    exit 1
fi

# Apply changes
terraform apply tfplan
cd ../..

# Step 5: Update ECS services with new task definitions
echo -e "${GREEN}Step 5: Updating ECS services...${NC}"

# Update registry service
echo "Updating registry service..."
aws ecs update-service \
    --cluster "$CLUSTER_NAME" \
    --service "$REGISTRY_SERVICE" \
    --force-new-deployment \
    --region "$AWS_REGION"

# Update MLflow service
echo "Updating MLflow service..."
aws ecs update-service \
    --cluster "$CLUSTER_NAME" \
    --service "$MLFLOW_SERVICE" \
    --force-new-deployment \
    --region "$AWS_REGION"

# Step 6: Wait for services to stabilize
echo -e "${GREEN}Step 6: Waiting for services to stabilize...${NC}"
echo "This may take several minutes..."

aws ecs wait services-stable \
    --cluster "$CLUSTER_NAME" \
    --services "$REGISTRY_SERVICE" "$MLFLOW_SERVICE" \
    --region "$AWS_REGION"

echo "Services are stable"

# Step 7: Run diagnostic script
echo -e "${GREEN}Step 7: Running diagnostics...${NC}"
python scripts/diagnose_service_health.py

# Step 8: Run health check tests
echo -e "${GREEN}Step 8: Running health check tests...${NC}"
python scripts/test_enhanced_health_checks.py

# Step 9: Check if recovery is needed
echo -e "${GREEN}Step 9: Checking if recovery is needed...${NC}"
python scripts/recover_service.py --dry-run

# Step 10: Final verification
echo -e "${GREEN}Step 10: Final verification...${NC}"

# Check registry endpoint
REGISTRY_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" https://registry.hokus.ai/health/status)
if [ "$REGISTRY_HEALTH" -eq "200" ]; then
    echo -e "${GREEN}✓ Registry service is healthy${NC}"
else
    echo -e "${RED}✗ Registry service health check failed (HTTP $REGISTRY_HEALTH)${NC}"
fi

# Check auth endpoint
AUTH_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" https://auth.hokus.ai/health)
if [ "$AUTH_HEALTH" -eq "200" ]; then
    echo -e "${GREEN}✓ Auth service is healthy${NC}"
else
    echo -e "${RED}✗ Auth service health check failed (HTTP $AUTH_HEALTH)${NC}"
fi

echo ""
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo "Next steps:"
echo "1. Monitor CloudWatch metrics for any anomalies"
echo "2. Check application logs for errors"
echo "3. Run integration tests to verify functionality"
echo "4. Update monitoring dashboards"
echo ""
echo "Rollback command (if needed):"
echo "  ./scripts/rollback_service.sh"