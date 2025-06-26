#!/bin/bash
set -e

# Deployment script for Hokusai infrastructure
# This script deploys the Terraform infrastructure and ECS services

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"
PROJECT_ROOT="$SCRIPT_DIR/../.."

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check required environment variables
check_env_vars() {
    local required_vars=("AWS_REGION" "ENVIRONMENT" "DATABASE_PASSWORD" "API_SECRET_KEY")
    local missing_vars=()
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var}" ]]; then
            missing_vars+=("$var")
        fi
    done
    
    if [[ ${#missing_vars[@]} -ne 0 ]]; then
        print_error "Missing required environment variables: ${missing_vars[*]}"
        print_info "Please set the following environment variables:"
        for var in "${missing_vars[@]}"; do
            echo "  export $var=<value>"
        done
        exit 1
    fi
}

# Check AWS credentials
check_aws_credentials() {
    print_info "Checking AWS credentials..."
    if ! aws sts get-caller-identity &>/dev/null; then
        print_error "AWS credentials not configured properly"
        print_info "Please configure AWS credentials using 'aws configure' or environment variables"
        exit 1
    fi
    print_info "AWS credentials validated"
}

# Initialize Terraform
init_terraform() {
    print_info "Initializing Terraform..."
    cd "$TERRAFORM_DIR"
    
    # Create backend config if it doesn't exist
    if [[ ! -f backend.tfvars ]]; then
        print_warn "backend.tfvars not found. Creating from template..."
        cat > backend.tfvars <<EOF
bucket = "hokusai-terraform-state-${ENVIRONMENT}"
key    = "hokusai/terraform.tfstate"
region = "${AWS_REGION}"
EOF
    fi
    
    terraform init -backend-config=backend.tfvars
}

# Validate Terraform configuration
validate_terraform() {
    print_info "Validating Terraform configuration..."
    cd "$TERRAFORM_DIR"
    terraform validate
    print_info "Terraform configuration is valid"
}

# Plan Terraform changes
plan_terraform() {
    print_info "Planning Terraform changes..."
    cd "$TERRAFORM_DIR"
    
    terraform plan \
        -var="aws_region=${AWS_REGION}" \
        -var="environment=${ENVIRONMENT}" \
        -var="database_password=${DATABASE_PASSWORD}" \
        -var="api_secret_key=${API_SECRET_KEY}" \
        -out=tfplan
}

# Apply Terraform changes
apply_terraform() {
    print_info "Applying Terraform changes..."
    cd "$TERRAFORM_DIR"
    
    # Show plan and ask for confirmation
    terraform show tfplan
    
    echo ""
    read -p "Do you want to apply these changes? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        print_warn "Deployment cancelled"
        exit 0
    fi
    
    terraform apply tfplan
    
    # Save outputs
    terraform output -json > outputs.json
    print_info "Terraform outputs saved to outputs.json"
}

# Build Docker images
build_docker_images() {
    print_info "Building Docker images..."
    cd "$PROJECT_ROOT"
    
    # Get ECR repository URLs from Terraform outputs
    API_ECR_URL=$(cd "$TERRAFORM_DIR" && terraform output -raw api_ecr_repository_url 2>/dev/null || echo "")
    MLFLOW_ECR_URL=$(cd "$TERRAFORM_DIR" && terraform output -raw mlflow_ecr_repository_url 2>/dev/null || echo "")
    
    if [[ -z "$API_ECR_URL" ]] || [[ -z "$MLFLOW_ECR_URL" ]]; then
        print_warn "ECR repositories not found in Terraform outputs. Skipping Docker build."
        return
    fi
    
    # Build API image
    print_info "Building API Docker image..."
    docker build -f Dockerfile.api -t hokusai-api:latest .
    docker tag hokusai-api:latest "${API_ECR_URL}:latest"
    
    # Build MLflow image
    print_info "Building MLflow Docker image..."
    docker build -f Dockerfile.mlflow -t hokusai-mlflow:latest .
    docker tag hokusai-mlflow:latest "${MLFLOW_ECR_URL}:latest"
}

# Push Docker images to ECR
push_docker_images() {
    print_info "Pushing Docker images to ECR..."
    
    # Get ECR login token
    aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$(aws sts get-caller-identity --query Account --output text).dkr.ecr.${AWS_REGION}.amazonaws.com"
    
    # Get ECR repository URLs
    API_ECR_URL=$(cd "$TERRAFORM_DIR" && terraform output -raw api_ecr_repository_url 2>/dev/null || echo "")
    MLFLOW_ECR_URL=$(cd "$TERRAFORM_DIR" && terraform output -raw mlflow_ecr_repository_url 2>/dev/null || echo "")
    
    if [[ -n "$API_ECR_URL" ]]; then
        print_info "Pushing API image..."
        docker push "${API_ECR_URL}:latest"
    fi
    
    if [[ -n "$MLFLOW_ECR_URL" ]]; then
        print_info "Pushing MLflow image..."
        docker push "${MLFLOW_ECR_URL}:latest"
    fi
}

# Deploy ECS services
deploy_ecs_services() {
    print_info "Deploying ECS services..."
    
    # Get cluster name from Terraform outputs
    CLUSTER_NAME=$(cd "$TERRAFORM_DIR" && terraform output -raw ecs_cluster_name)
    
    # Update API service
    print_info "Updating API service..."
    aws ecs update-service \
        --cluster "$CLUSTER_NAME" \
        --service hokusai-api \
        --force-new-deployment \
        --region "$AWS_REGION" || print_warn "API service update failed (service might not exist yet)"
    
    # Update MLflow service
    print_info "Updating MLflow service..."
    aws ecs update-service \
        --cluster "$CLUSTER_NAME" \
        --service hokusai-mlflow \
        --force-new-deployment \
        --region "$AWS_REGION" || print_warn "MLflow service update failed (service might not exist yet)"
}

# Main deployment function
main() {
    print_info "Starting Hokusai infrastructure deployment..."
    print_info "Environment: $ENVIRONMENT"
    print_info "AWS Region: $AWS_REGION"
    
    # Run deployment steps
    check_env_vars
    check_aws_credentials
    init_terraform
    validate_terraform
    plan_terraform
    apply_terraform
    build_docker_images
    push_docker_images
    deploy_ecs_services
    
    print_info "Deployment completed successfully!"
    
    # Print access information
    API_ENDPOINT=$(cd "$TERRAFORM_DIR" && terraform output -raw api_endpoint)
    MLFLOW_ENDPOINT=$(cd "$TERRAFORM_DIR" && terraform output -raw mlflow_endpoint)
    
    echo ""
    print_info "Access Information:"
    echo "  API Endpoint: $API_ENDPOINT"
    echo "  MLflow UI: $MLFLOW_ENDPOINT"
}

# Run main function
main "$@"