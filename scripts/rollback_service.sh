#!/bin/bash

# Rollback Service Degradation Fixes
# This script rolls back the service to the previous stable version

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

echo -e "${YELLOW}=== Hokusai Service Rollback ===${NC}"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo ""

echo -e "${RED}WARNING: This will rollback the services to the previous version${NC}"
echo "Continue? (y/n)"
read -r response
if [[ "$response" != "y" ]]; then
    echo "Rollback cancelled"
    exit 0
fi

# Step 1: Get previous task definition revision
echo -e "${GREEN}Step 1: Getting previous task definition revisions...${NC}"

REGISTRY_PREV_REVISION=$(($(aws ecs describe-task-definition \
    --task-definition "hokusai-registry-api-${ENVIRONMENT}" \
    --region "$AWS_REGION" \
    --query 'taskDefinition.revision' \
    --output text) - 1))

MLFLOW_PREV_REVISION=$(($(aws ecs describe-task-definition \
    --task-definition "hokusai-mlflow-${ENVIRONMENT}" \
    --region "$AWS_REGION" \
    --query 'taskDefinition.revision' \
    --output text) - 1))

echo "Registry previous revision: $REGISTRY_PREV_REVISION"
echo "MLflow previous revision: $MLFLOW_PREV_REVISION"

# Step 2: Update services with previous task definitions
echo -e "${GREEN}Step 2: Rolling back services...${NC}"

# Rollback registry service
echo "Rolling back registry service..."
aws ecs update-service \
    --cluster "$CLUSTER_NAME" \
    --service "$REGISTRY_SERVICE" \
    --task-definition "hokusai-registry-api-${ENVIRONMENT}:${REGISTRY_PREV_REVISION}" \
    --force-new-deployment \
    --region "$AWS_REGION"

# Rollback MLflow service
echo "Rolling back MLflow service..."
aws ecs update-service \
    --cluster "$CLUSTER_NAME" \
    --service "$MLFLOW_SERVICE" \
    --task-definition "hokusai-mlflow-${ENVIRONMENT}:${MLFLOW_PREV_REVISION}" \
    --force-new-deployment \
    --region "$AWS_REGION"

# Step 3: Wait for services to stabilize
echo -e "${GREEN}Step 3: Waiting for services to stabilize...${NC}"
echo "This may take several minutes..."

aws ecs wait services-stable \
    --cluster "$CLUSTER_NAME" \
    --services "$REGISTRY_SERVICE" "$MLFLOW_SERVICE" \
    --region "$AWS_REGION"

echo "Services are stable"

# Step 4: Verify rollback
echo -e "${GREEN}Step 4: Verifying rollback...${NC}"

# Check service status
REGISTRY_RUNNING=$(aws ecs describe-services \
    --cluster "$CLUSTER_NAME" \
    --services "$REGISTRY_SERVICE" \
    --region "$AWS_REGION" \
    --query 'services[0].runningCount' \
    --output text)

MLFLOW_RUNNING=$(aws ecs describe-services \
    --cluster "$CLUSTER_NAME" \
    --services "$MLFLOW_SERVICE" \
    --region "$AWS_REGION" \
    --query 'services[0].runningCount' \
    --output text)

echo "Registry running tasks: $REGISTRY_RUNNING"
echo "MLflow running tasks: $MLFLOW_RUNNING"

# Check health endpoints
REGISTRY_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" https://registry.hokus.ai/health || echo "000")
AUTH_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" https://auth.hokus.ai/health || echo "000")

if [ "$REGISTRY_HEALTH" -eq "200" ] || [ "$REGISTRY_HEALTH" -eq "503" ]; then
    echo -e "${GREEN}✓ Registry service is responding${NC}"
else
    echo -e "${RED}✗ Registry service is not responding (HTTP $REGISTRY_HEALTH)${NC}"
fi

if [ "$AUTH_HEALTH" -eq "200" ]; then
    echo -e "${GREEN}✓ Auth service is healthy${NC}"
else
    echo -e "${RED}✗ Auth service is not responding (HTTP $AUTH_HEALTH)${NC}"
fi

echo ""
echo -e "${GREEN}=== Rollback Complete ===${NC}"
echo ""
echo "Please check:"
echo "1. CloudWatch logs for any errors"
echo "2. Service metrics in CloudWatch"
echo "3. Run diagnostic script: python scripts/diagnose_service_health.py"