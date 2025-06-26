#!/bin/bash
set -e

# Destroy script for Hokusai infrastructure
# This script safely destroys the Terraform infrastructure

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"

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

# Check if this is production
check_production_safety() {
    if [[ "${ENVIRONMENT}" == "production" ]]; then
        print_error "WARNING: You are about to destroy PRODUCTION infrastructure!"
        print_error "This action cannot be undone and will delete all resources."
        echo ""
        echo "Please confirm by typing 'destroy-production' exactly:"
        read -r confirmation
        
        if [[ "$confirmation" != "destroy-production" ]]; then
            print_info "Destruction cancelled"
            exit 0
        fi
        
        print_warn "Proceeding with production destruction in 10 seconds..."
        print_warn "Press Ctrl+C to cancel"
        sleep 10
    fi
}

# Backup important data
backup_data() {
    print_info "Creating backup of important configuration..."
    
    BACKUP_DIR="$SCRIPT_DIR/backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    # Save Terraform outputs
    if cd "$TERRAFORM_DIR" && terraform output -json > "$BACKUP_DIR/terraform_outputs.json" 2>/dev/null; then
        print_info "Terraform outputs backed up to $BACKUP_DIR/terraform_outputs.json"
    fi
    
    # Save Terraform state
    if [[ -f "$TERRAFORM_DIR/terraform.tfstate" ]]; then
        cp "$TERRAFORM_DIR/terraform.tfstate" "$BACKUP_DIR/"
        print_info "Terraform state backed up to $BACKUP_DIR/terraform.tfstate"
    fi
}

# Empty S3 buckets (required before deletion)
empty_s3_buckets() {
    print_info "Emptying S3 buckets before deletion..."
    
    cd "$TERRAFORM_DIR"
    
    # Get bucket names
    ARTIFACTS_BUCKET=$(terraform output -raw s3_artifacts_bucket 2>/dev/null || echo "")
    PIPELINE_BUCKET=$(terraform output -raw s3_pipeline_bucket 2>/dev/null || echo "")
    
    if [[ -n "$ARTIFACTS_BUCKET" ]]; then
        print_info "Emptying artifacts bucket: $ARTIFACTS_BUCKET"
        aws s3 rm "s3://${ARTIFACTS_BUCKET}" --recursive || true
    fi
    
    if [[ -n "$PIPELINE_BUCKET" ]]; then
        print_info "Emptying pipeline bucket: $PIPELINE_BUCKET"
        aws s3 rm "s3://${PIPELINE_BUCKET}" --recursive || true
    fi
}

# Stop ECS services
stop_ecs_services() {
    print_info "Stopping ECS services..."
    
    cd "$TERRAFORM_DIR"
    CLUSTER_NAME=$(terraform output -raw ecs_cluster_name 2>/dev/null || echo "")
    
    if [[ -n "$CLUSTER_NAME" ]]; then
        # Update services to 0 desired count
        aws ecs update-service \
            --cluster "$CLUSTER_NAME" \
            --service hokusai-api \
            --desired-count 0 \
            2>/dev/null || true
            
        aws ecs update-service \
            --cluster "$CLUSTER_NAME" \
            --service hokusai-mlflow \
            --desired-count 0 \
            2>/dev/null || true
            
        print_info "Waiting for services to stop..."
        sleep 30
    fi
}

# Plan destruction
plan_destruction() {
    print_info "Planning infrastructure destruction..."
    cd "$TERRAFORM_DIR"
    
    terraform plan -destroy \
        -var="aws_region=${AWS_REGION}" \
        -var="environment=${ENVIRONMENT}" \
        -var="database_password=dummy" \
        -var="api_secret_key=dummy" \
        -out=destroy.tfplan
}

# Execute destruction
execute_destruction() {
    print_info "Executing infrastructure destruction..."
    cd "$TERRAFORM_DIR"
    
    # Show destruction plan
    terraform show destroy.tfplan
    
    echo ""
    print_warn "This will destroy all infrastructure resources!"
    read -p "Are you sure you want to continue? (yes/no): " confirm
    
    if [[ "$confirm" != "yes" ]]; then
        print_info "Destruction cancelled"
        exit 0
    fi
    
    # Apply destruction
    terraform apply destroy.tfplan
}

# Clean up local files
cleanup_local_files() {
    print_info "Cleaning up local files..."
    
    cd "$TERRAFORM_DIR"
    
    # Remove plan files
    rm -f tfplan destroy.tfplan
    
    # Remove outputs file
    rm -f outputs.json
    
    print_info "Local cleanup complete"
}

# Main destruction function
main() {
    print_error "INFRASTRUCTURE DESTRUCTION INITIATED"
    print_info "Environment: ${ENVIRONMENT:-unknown}"
    print_info "AWS Region: ${AWS_REGION:-unknown}"
    echo ""
    
    # Safety checks
    if [[ -z "$ENVIRONMENT" ]] || [[ -z "$AWS_REGION" ]]; then
        print_error "ENVIRONMENT and AWS_REGION must be set"
        exit 1
    fi
    
    # Confirm destruction
    print_warn "This script will destroy all Hokusai infrastructure in ${ENVIRONMENT}"
    print_warn "This includes:"
    echo "  - ECS services and tasks"
    echo "  - RDS database"
    echo "  - S3 buckets and all data"
    echo "  - VPC and networking resources"
    echo "  - IAM roles and policies"
    echo ""
    read -p "Do you want to proceed? (yes/no): " initial_confirm
    
    if [[ "$initial_confirm" != "yes" ]]; then
        print_info "Destruction cancelled"
        exit 0
    fi
    
    # Run destruction steps
    check_production_safety
    backup_data
    stop_ecs_services
    empty_s3_buckets
    plan_destruction
    execute_destruction
    cleanup_local_files
    
    print_info "Infrastructure destruction completed"
    print_warn "Backup data saved in: $BACKUP_DIR"
}

# Run main function
main "$@"