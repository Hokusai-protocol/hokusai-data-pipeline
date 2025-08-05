#!/bin/bash
# Deploy MLflow container with artifact storage fixes

set -e  # Exit on error

echo "=================================================="
echo "MLflow Artifact Storage Fix Deployment"
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
print_info "Checking prerequisites..."
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed"
    exit 1
fi

if ! command -v aws &> /dev/null; then
    print_error "AWS CLI is not installed"
    exit 1
fi

# Check AWS credentials
print_info "Verifying AWS access..."
if ! aws sts get-caller-identity &> /dev/null; then
    print_error "AWS credentials not configured"
    exit 1
fi

# Get AWS account info
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_REGION:-us-east-1}
ENVIRONMENT=${ENVIRONMENT:-production}

print_info "AWS Account: $ACCOUNT_ID"
print_info "AWS Region: $REGION"
print_info "Environment: $ENVIRONMENT"

# ECR repository URL
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/hokusai-mlflow-${ENVIRONMENT}"
print_info "ECR Repository: $ECR_REPO"

# Build MLflow Docker image
print_info "Building MLflow Docker image with artifact storage fixes..."
if [[ -f "Dockerfile.mlflow" ]]; then
    docker build -f Dockerfile.mlflow -t hokusai-mlflow:latest .
else
    print_error "Dockerfile.mlflow not found!"
    exit 1
fi

# Tag the image
print_info "Tagging image for ECR..."
docker tag hokusai-mlflow:latest "${ECR_REPO}:latest"
docker tag hokusai-mlflow:latest "${ECR_REPO}:$(date +%Y%m%d-%H%M%S)"

# Login to ECR
print_info "Logging in to ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# Push the image
print_info "Pushing image to ECR..."
docker push "${ECR_REPO}:latest"
docker push "${ECR_REPO}:$(date +%Y%m%d-%H%M%S)"

# Get ECS cluster and service names
CLUSTER_NAME="hokusai-${ENVIRONMENT}"
SERVICE_NAME="hokusai-mlflow"

print_info "ECS Cluster: $CLUSTER_NAME"
print_info "ECS Service: $SERVICE_NAME"

# Update ECS service to use new image
print_info "Updating ECS service with new image..."
aws ecs update-service \
    --cluster "$CLUSTER_NAME" \
    --service "$SERVICE_NAME" \
    --force-new-deployment \
    --region "$REGION"

# Wait for deployment to stabilize
print_info "Waiting for service to stabilize (this may take a few minutes)..."
aws ecs wait services-stable \
    --cluster "$CLUSTER_NAME" \
    --services "$SERVICE_NAME" \
    --region "$REGION"

print_info "Deployment complete!"

# Check service status
print_info "Checking service status..."
aws ecs describe-services \
    --cluster "$CLUSTER_NAME" \
    --services "$SERVICE_NAME" \
    --region "$REGION" \
    --query "services[0].deployments[*].[status,taskDefinition,desiredCount,runningCount]" \
    --output table

echo ""
print_info "Next steps:"
echo "1. Monitor CloudWatch logs: aws logs tail /ecs/hokusai/mlflow/${ENVIRONMENT} --follow"
echo "2. Test artifact endpoints: curl -H 'Authorization: Bearer \$HOKUSAI_API_KEY' https://registry.hokus.ai/api/mlflow/api/2.0/mlflow-artifacts/artifacts"
echo "3. Run registration test: python test_model_registration_simple.py"
echo ""