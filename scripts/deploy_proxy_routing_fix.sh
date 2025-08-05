#!/bin/bash

# Deployment script for proxy routing fixes
# This script updates the infrastructure and deploys the improved MLflow proxy

set -e  # Exit on error

echo "=== MLflow Proxy Routing Fix Deployment ==="
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

echo "Environment: $ENVIRONMENT"
echo "AWS Region: $AWS_REGION"
echo "AWS Account: $AWS_ACCOUNT_ID"
echo

# Step 1: Apply Terraform changes for service discovery
echo -e "${YELLOW}Step 1: Applying Terraform changes for service discovery...${NC}"
cd infrastructure/terraform

# Initialize Terraform if needed
if [ ! -d ".terraform" ]; then
    terraform init
    check_status "Terraform initialization"
fi

# Plan the changes
terraform plan -out=tfplan \
    -var="environment=$ENVIRONMENT" \
    -var="aws_region=$AWS_REGION"
check_status "Terraform plan"

echo
read -p "Review the plan above. Continue with apply? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled"
    exit 1
fi

# Apply the changes
terraform apply tfplan
check_status "Terraform apply"

# Get the internal MLflow DNS name
MLFLOW_INTERNAL_DNS=$(terraform output -raw mlflow_internal_dns 2>/dev/null || echo "mlflow.hokusai-${ENVIRONMENT}.local")
echo -e "${GREEN}MLflow internal DNS: $MLFLOW_INTERNAL_DNS${NC}"

cd ../..

# Step 2: Build and push updated API container
echo
echo -e "${YELLOW}Step 2: Building and pushing updated API container...${NC}"

# Build the API container
docker build -f Dockerfile -t hokusai-api:latest .
check_status "Docker build"

# Tag for ECR
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/hokusai-api"
docker tag hokusai-api:latest ${ECR_REPO}:latest
docker tag hokusai-api:latest ${ECR_REPO}:proxy-routing-fix
check_status "Docker tag"

# Login to ECR
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REPO}
check_status "ECR login"

# Push to ECR
docker push ${ECR_REPO}:latest
docker push ${ECR_REPO}:proxy-routing-fix
check_status "Docker push"

# Step 3: Update ECS service with new task definition
echo
echo -e "${YELLOW}Step 3: Updating ECS service...${NC}"

# Get the current task definition
TASK_DEF_ARN=$(aws ecs describe-services \
    --cluster hokusai-${ENVIRONMENT} \
    --services hokusai-api \
    --region ${AWS_REGION} \
    --query 'services[0].taskDefinition' \
    --output text)

TASK_DEF_FAMILY=$(aws ecs describe-task-definition \
    --task-definition ${TASK_DEF_ARN} \
    --region ${AWS_REGION} \
    --query 'taskDefinition.family' \
    --output text)

# Create new task definition with updated environment variables
CONTAINER_DEFS=$(aws ecs describe-task-definition \
    --task-definition ${TASK_DEF_ARN} \
    --region ${AWS_REGION} \
    --query 'taskDefinition.containerDefinitions' \
    --output json | \
    jq --arg mlflow_url "http://${MLFLOW_INTERNAL_DNS}:5000" \
    '.[0].environment |= map(
        if .name == "MLFLOW_SERVER_URL" then .value = $mlflow_url
        elif .name == "MLFLOW_TRACKING_URI" then .value = $mlflow_url
        else . end
    ) + [{"name": "MLFLOW_PROXY_DEBUG", "value": "true"}]')

# Register new task definition
NEW_TASK_DEF=$(aws ecs register-task-definition \
    --family ${TASK_DEF_FAMILY} \
    --container-definitions "${CONTAINER_DEFS}" \
    --requires-compatibilities FARGATE \
    --network-mode awsvpc \
    --cpu "$(aws ecs describe-task-definition --task-definition ${TASK_DEF_ARN} --query 'taskDefinition.cpu' --output text)" \
    --memory "$(aws ecs describe-task-definition --task-definition ${TASK_DEF_ARN} --query 'taskDefinition.memory' --output text)" \
    --execution-role-arn "$(aws ecs describe-task-definition --task-definition ${TASK_DEF_ARN} --query 'taskDefinition.executionRoleArn' --output text)" \
    --task-role-arn "$(aws ecs describe-task-definition --task-definition ${TASK_DEF_ARN} --query 'taskDefinition.taskRoleArn' --output text)" \
    --region ${AWS_REGION})

NEW_TASK_DEF_ARN=$(echo $NEW_TASK_DEF | jq -r '.taskDefinition.taskDefinitionArn')
check_status "Task definition registration"

# Update the service
aws ecs update-service \
    --cluster hokusai-${ENVIRONMENT} \
    --service hokusai-api \
    --task-definition ${NEW_TASK_DEF_ARN} \
    --force-new-deployment \
    --region ${AWS_REGION} \
    --output json > /dev/null

check_status "ECS service update"

# Step 4: Wait for deployment to complete
echo
echo -e "${YELLOW}Step 4: Waiting for deployment to complete...${NC}"
echo "This may take several minutes..."

# Wait for service to stabilize
aws ecs wait services-stable \
    --cluster hokusai-${ENVIRONMENT} \
    --services hokusai-api \
    --region ${AWS_REGION}

check_status "Service deployment"

# Step 5: Verify the deployment
echo
echo -e "${YELLOW}Step 5: Verifying deployment...${NC}"

# Get the API endpoint
API_ENDPOINT="https://registry.hokus.ai"

# Test health endpoint
echo "Testing API health..."
curl -s ${API_ENDPOINT}/health | jq '.' || echo "Health check failed"

# Test MLflow proxy health
echo
echo "Testing MLflow proxy health..."
curl -s ${API_ENDPOINT}/mlflow/health/mlflow | jq '.' || echo "MLflow health check failed"

# Test detailed MLflow health
echo
echo "Testing detailed MLflow health..."
curl -s ${API_ENDPOINT}/mlflow/health/mlflow/detailed | jq '.' || echo "Detailed MLflow health check failed"

echo
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo
echo "Next steps:"
echo "1. Run test_real_registration.py to verify model registration works"
echo "2. Monitor CloudWatch logs for any errors"
echo "3. Check the MLflow UI at ${API_ENDPOINT}/mlflow"
echo
echo "To rollback if needed:"
echo "  aws ecs update-service --cluster hokusai-${ENVIRONMENT} --service hokusai-api --task-definition ${TASK_DEF_ARN}"