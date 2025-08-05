#!/bin/bash

# Simplified deployment script for proxy routing fixes
# This version updates only what's needed without full Terraform changes

set -e  # Exit on error

echo "=== MLflow Proxy Routing Fix - Simplified Deployment ==="
echo

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if AWS CLI is configured
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo -e "${RED}Error: AWS CLI not configured. Please run 'aws configure'${NC}"
    exit 1
fi

# Function to check command success
check_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ $1${NC}"
    else
        echo -e "${RED}✗ $1 failed${NC}"
        exit 1
    fi
}

# Get environment variables
ENVIRONMENT=${ENVIRONMENT:-development}
AWS_REGION=${AWS_REGION:-us-east-1}
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
PROJECT_NAME="hokusai"

echo "Environment: $ENVIRONMENT"
echo "AWS Region: $AWS_REGION"
echo "AWS Account: $AWS_ACCOUNT_ID"
echo "Project: $PROJECT_NAME"
echo

# Step 1: Build and push updated API container
echo -e "${YELLOW}Step 1: Building and pushing updated API container...${NC}"

# Check if we're in the right directory
if [ ! -f "Dockerfile.api" ]; then
    echo -e "${RED}Error: Dockerfile.api not found. Please run from the project root.${NC}"
    exit 1
fi

# Build the API container
echo "Building Docker image..."
docker build -f Dockerfile.api -t ${PROJECT_NAME}-api:latest .
check_status "Docker build"

# Tag for ECR
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}-api"
docker tag ${PROJECT_NAME}-api:latest ${ECR_REPO}:latest
docker tag ${PROJECT_NAME}-api:latest ${ECR_REPO}:proxy-routing-fix
check_status "Docker tag"

# Login to ECR
echo "Logging into ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REPO}
check_status "ECR login"

# Push to ECR
echo "Pushing to ECR..."
docker push ${ECR_REPO}:latest
docker push ${ECR_REPO}:proxy-routing-fix
check_status "Docker push"

# Step 2: Get current task definition and update it
echo
echo -e "${YELLOW}Step 2: Updating ECS task definition...${NC}"

# Get the current task definition
TASK_FAMILY="${PROJECT_NAME}-api-${ENVIRONMENT}"
echo "Getting current task definition for: $TASK_FAMILY"

# Download current task definition
aws ecs describe-task-definition \
    --task-definition ${TASK_FAMILY} \
    --region ${AWS_REGION} \
    --query 'taskDefinition' > current-task-def.json

check_status "Download task definition"

# Get MLflow service tasks to find internal IP
echo "Finding MLflow service internal IP..."
MLFLOW_TASK_ARN=$(aws ecs list-tasks \
    --cluster ${PROJECT_NAME}-${ENVIRONMENT} \
    --service-name ${PROJECT_NAME}-mlflow \
    --region ${AWS_REGION} \
    --query 'taskArns[0]' \
    --output text)

if [ "$MLFLOW_TASK_ARN" != "None" ] && [ -n "$MLFLOW_TASK_ARN" ]; then
    MLFLOW_IP=$(aws ecs describe-tasks \
        --cluster ${PROJECT_NAME}-${ENVIRONMENT} \
        --tasks ${MLFLOW_TASK_ARN} \
        --region ${AWS_REGION} \
        --query 'tasks[0].containers[0].networkInterfaces[0].privateIpv4Address' \
        --output text)
    
    if [ "$MLFLOW_IP" != "None" ] && [ -n "$MLFLOW_IP" ]; then
        echo -e "${GREEN}Found MLflow IP: $MLFLOW_IP${NC}"
        MLFLOW_URL="http://${MLFLOW_IP}:5000"
    else
        echo -e "${YELLOW}Could not find MLflow IP, using service name${NC}"
        MLFLOW_URL="http://mlflow.${PROJECT_NAME}-${ENVIRONMENT}.local:5000"
    fi
else
    echo -e "${YELLOW}MLflow service not running, using service name${NC}"
    MLFLOW_URL="http://mlflow.${PROJECT_NAME}-${ENVIRONMENT}.local:5000"
fi

# Update the task definition with new environment variables
echo "Updating task definition with MLflow URL: $MLFLOW_URL"

# Use jq to update the environment variables
jq --arg mlflow_url "$MLFLOW_URL" \
   --arg image "${ECR_REPO}:proxy-routing-fix" \
   '.containerDefinitions[0].image = $image |
    .containerDefinitions[0].environment |= map(
        if .name == "MLFLOW_TRACKING_URI" then .value = $mlflow_url
        else . end
    ) |
    .containerDefinitions[0].environment += [
        {"name": "MLFLOW_SERVER_URL", "value": $mlflow_url},
        {"name": "MLFLOW_SERVE_ARTIFACTS", "value": "true"},
        {"name": "MLFLOW_PROXY_DEBUG", "value": "true"}
    ] |
    del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy)' \
    current-task-def.json > new-task-def.json

check_status "Update task definition JSON"

# Register the new task definition
echo "Registering new task definition..."
NEW_TASK_DEF_ARN=$(aws ecs register-task-definition \
    --cli-input-json file://new-task-def.json \
    --region ${AWS_REGION} \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

check_status "Register task definition"
echo "New task definition: $NEW_TASK_DEF_ARN"

# Step 3: Update the ECS service
echo
echo -e "${YELLOW}Step 3: Updating ECS service...${NC}"

aws ecs update-service \
    --cluster ${PROJECT_NAME}-${ENVIRONMENT} \
    --service ${PROJECT_NAME}-api \
    --task-definition ${NEW_TASK_DEF_ARN} \
    --force-new-deployment \
    --region ${AWS_REGION} \
    --output json > service-update.json

check_status "Update ECS service"

# Step 4: Wait for deployment
echo
echo -e "${YELLOW}Step 4: Waiting for deployment to complete...${NC}"
echo "This may take several minutes..."

# Wait for service to stabilize (with timeout)
timeout=600  # 10 minutes
elapsed=0
interval=30

while [ $elapsed -lt $timeout ]; do
    DEPLOYMENT_COUNT=$(aws ecs describe-services \
        --cluster ${PROJECT_NAME}-${ENVIRONMENT} \
        --services ${PROJECT_NAME}-api \
        --region ${AWS_REGION} \
        --query 'services[0].deployments | length(@)' \
        --output text)
    
    if [ "$DEPLOYMENT_COUNT" -eq "1" ]; then
        echo -e "${GREEN}Deployment completed!${NC}"
        break
    fi
    
    echo "Waiting for deployment to complete... ($elapsed seconds elapsed)"
    sleep $interval
    elapsed=$((elapsed + interval))
done

if [ $elapsed -ge $timeout ]; then
    echo -e "${YELLOW}Warning: Deployment is taking longer than expected${NC}"
fi

# Step 5: Verify deployment
echo
echo -e "${YELLOW}Step 5: Verifying deployment...${NC}"

# Get the API endpoint
API_ENDPOINT="https://registry.hokus.ai"

# Test health endpoint
echo "Testing API health..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" ${API_ENDPOINT}/health || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✓ API health check passed${NC}"
else
    echo -e "${YELLOW}⚠ API health returned: $HTTP_CODE${NC}"
fi

# Test MLflow proxy health
echo
echo "Testing MLflow proxy health..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" ${API_ENDPOINT}/api/mlflow/health/mlflow || echo "000")
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "404" ]; then
    if [ "$HTTP_CODE" = "404" ]; then
        echo -e "${YELLOW}⚠ MLflow health endpoint not found (404) - routes may not be deployed yet${NC}"
    else
        echo -e "${GREEN}✓ MLflow proxy health check passed${NC}"
    fi
else
    echo -e "${YELLOW}⚠ MLflow proxy health returned: $HTTP_CODE${NC}"
fi

# Cleanup
rm -f current-task-def.json new-task-def.json service-update.json

echo
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo
echo "Summary:"
echo "- API container updated with improved proxy routing"
echo "- MLflow URL configured: $MLFLOW_URL"
echo "- Task definition updated: $NEW_TASK_DEF_ARN"
echo
echo "Next steps:"
echo "1. Monitor CloudWatch logs for any errors:"
echo "   aws logs tail /aws/ecs/${PROJECT_NAME}-api --follow"
echo
echo "2. Test model registration:"
echo "   export HOKUSAI_API_KEY='your-api-key'"
echo "   python test_real_registration.py"
echo
echo "3. Check proxy debug logs (MLFLOW_PROXY_DEBUG is enabled)"
echo
echo "To rollback if needed:"
echo "  aws ecs update-service --cluster ${PROJECT_NAME}-${ENVIRONMENT} --service ${PROJECT_NAME}-api --task-definition ${TASK_FAMILY}"