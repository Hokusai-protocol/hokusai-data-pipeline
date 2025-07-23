#!/bin/bash
# Deploy MLflow container with artifact storage support
# This script builds and deploys ONLY the MLflow container

set -e

echo "=================================================="
echo "MLflow Container Deployment Script"
echo "=================================================="
echo "This script will:"
echo "1. Build the MLflow Docker image with artifact storage"
echo "2. Push to ECR"
echo "3. Update the MLflow ECS service"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

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
    print_error "Docker is not installed or not running"
    exit 1
fi

if ! command -v aws &> /dev/null; then
    print_error "AWS CLI is not installed"
    exit 1
fi

# Check AWS credentials
print_info "Verifying AWS credentials..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
if [ -z "$ACCOUNT_ID" ]; then
    print_error "AWS credentials not configured"
    print_info "Please run: aws configure"
    exit 1
fi

# Set variables
REGION=${AWS_REGION:-us-east-1}
ENVIRONMENT=${ENVIRONMENT:-development}
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/hokusai-mlflow"
CLUSTER_NAME="hokusai-${ENVIRONMENT}"
SERVICE_NAME="hokusai-mlflow"

print_info "Configuration:"
echo "  AWS Account: $ACCOUNT_ID"
echo "  Region: $REGION"
echo "  Environment: $ENVIRONMENT"
echo "  ECR Repository: $ECR_REPO"
echo "  ECS Cluster: $CLUSTER_NAME"
echo "  ECS Service: $SERVICE_NAME"
echo ""

# Confirm before proceeding
read -p "Do you want to continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warn "Deployment cancelled"
    exit 0
fi

# Step 1: Build Docker image
print_info "Building MLflow Docker image..."
if [ ! -f "Dockerfile.mlflow" ]; then
    print_error "Dockerfile.mlflow not found in current directory"
    print_info "Please run this script from the repository root"
    exit 1
fi

# Show the Dockerfile content for verification
print_info "Dockerfile.mlflow content:"
echo "----------------------------------------"
grep -E "serve-artifacts|ENTRYPOINT|CMD" Dockerfile.mlflow || true
echo "----------------------------------------"

docker build -f Dockerfile.mlflow -t hokusai-mlflow:latest . || {
    print_error "Docker build failed"
    exit 1
}

print_info "Docker image built successfully"

# Step 2: Tag the image
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
print_info "Tagging image..."
docker tag hokusai-mlflow:latest "${ECR_REPO}:latest"
docker tag hokusai-mlflow:latest "${ECR_REPO}:${TIMESTAMP}"

# Step 3: Login to ECR
print_info "Logging in to ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com" || {
    print_error "ECR login failed"
    exit 1
}

# Step 4: Push the image
print_info "Pushing image to ECR..."
print_info "This may take a few minutes..."
docker push "${ECR_REPO}:latest" || {
    print_error "Failed to push image to ECR"
    exit 1
}
docker push "${ECR_REPO}:${TIMESTAMP}"

print_info "Image pushed successfully"

# Step 5: Check current MLflow service status
print_info "Checking current MLflow service..."
CURRENT_TASK_DEF=$(aws ecs describe-services \
    --cluster "$CLUSTER_NAME" \
    --services "$SERVICE_NAME" \
    --query 'services[0].taskDefinition' \
    --output text 2>/dev/null || echo "")

if [ -z "$CURRENT_TASK_DEF" ]; then
    print_error "MLflow service not found"
    print_info "Please ensure the service exists in ECS"
    exit 1
fi

print_info "Current task definition: $CURRENT_TASK_DEF"

# Step 6: Update ECS service
print_info "Updating MLflow ECS service..."
UPDATE_RESULT=$(aws ecs update-service \
    --cluster "$CLUSTER_NAME" \
    --service "$SERVICE_NAME" \
    --force-new-deployment \
    --query 'service.deployments[0].id' \
    --output text 2>&1) || {
    print_error "Failed to update service: $UPDATE_RESULT"
    exit 1
}

print_info "Service update initiated. Deployment ID: $UPDATE_RESULT"

# Step 7: Wait for deployment to start
print_info "Waiting for deployment to start..."
sleep 10

# Step 8: Monitor deployment
print_info "Monitoring deployment progress..."
echo "You can monitor the deployment with:"
echo "  aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --query 'services[0].deployments'"
echo ""

# Check initial deployment status
for i in {1..6}; do
    STATUS=$(aws ecs describe-services \
        --cluster "$CLUSTER_NAME" \
        --services "$SERVICE_NAME" \
        --query 'services[0].deployments[0].rolloutState' \
        --output text 2>/dev/null || echo "UNKNOWN")
    
    RUNNING=$(aws ecs describe-services \
        --cluster "$CLUSTER_NAME" \
        --services "$SERVICE_NAME" \
        --query 'services[0].deployments[0].runningCount' \
        --output text 2>/dev/null || echo "0")
    
    DESIRED=$(aws ecs describe-services \
        --cluster "$CLUSTER_NAME" \
        --services "$SERVICE_NAME" \
        --query 'services[0].deployments[0].desiredCount' \
        --output text 2>/dev/null || echo "0")
    
    print_info "Deployment status: $STATUS (Running: $RUNNING/$DESIRED)"
    
    if [ "$STATUS" = "COMPLETED" ]; then
        print_info "Deployment completed successfully!"
        break
    elif [ "$STATUS" = "FAILED" ]; then
        print_error "Deployment failed!"
        print_info "Check logs with: aws logs tail /ecs/hokusai/mlflow/$ENVIRONMENT"
        exit 1
    fi
    
    if [ $i -lt 6 ]; then
        sleep 30
    fi
done

# Final instructions
echo ""
print_info "Deployment initiated successfully!"
echo ""
print_info "Next steps:"
echo "1. Monitor logs for startup confirmation:"
echo "   aws logs tail /ecs/hokusai/mlflow/$ENVIRONMENT --follow | grep -E 'serve-artifacts|Starting'"
echo ""
echo "2. Wait for the service to stabilize (usually 2-5 minutes)"
echo ""
echo "3. Test artifact endpoints:"
echo "   curl -H 'Authorization: Bearer \$HOKUSAI_API_KEY' https://registry.hokus.ai/api/mlflow/api/2.0/mlflow-artifacts/artifacts"
echo ""
echo "4. Run the model registration test:"
echo "   export HOKUSAI_API_KEY='your-api-key'"
echo "   python test_model_registration_simple.py"
echo ""

# Check if API service needs to be restarted
print_warn "Note: The API service may need to be restarted to connect to the updated MLflow service"
echo "If model registration still fails after MLflow is updated, restart the API service:"
echo "  aws ecs update-service --cluster $CLUSTER_NAME --service hokusai-api --force-new-deployment"
echo ""