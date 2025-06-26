#!/bin/bash
set -e

# Validation script for Hokusai infrastructure deployment
# This script validates that all services are running correctly

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"
MAX_RETRIES=30
RETRY_DELAY=10

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

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Check if Terraform outputs exist
check_terraform_outputs() {
    print_info "Checking Terraform outputs..."
    cd "$TERRAFORM_DIR"
    
    if ! terraform output &>/dev/null; then
        print_error "Unable to read Terraform outputs. Have you run terraform apply?"
        exit 1
    fi
    
    print_success "Terraform outputs available"
}

# Validate API health
validate_api_health() {
    print_info "Validating API health..."
    
    API_ENDPOINT=$(cd "$TERRAFORM_DIR" && terraform output -raw api_endpoint)
    HEALTH_URL="${API_ENDPOINT}/health"
    
    local retries=0
    while [ $retries -lt $MAX_RETRIES ]; do
        print_info "Checking API health (attempt $((retries + 1))/$MAX_RETRIES)..."
        
        if curl -sf "$HEALTH_URL" > /dev/null; then
            print_success "API is healthy"
            return 0
        fi
        
        retries=$((retries + 1))
        if [ $retries -lt $MAX_RETRIES ]; then
            print_warn "API not ready yet. Waiting ${RETRY_DELAY}s..."
            sleep $RETRY_DELAY
        fi
    done
    
    print_error "API health check failed after $MAX_RETRIES attempts"
    return 1
}

# Validate MLflow health
validate_mlflow_health() {
    print_info "Validating MLflow health..."
    
    MLFLOW_ENDPOINT=$(cd "$TERRAFORM_DIR" && terraform output -raw mlflow_endpoint)
    HEALTH_URL="${MLFLOW_ENDPOINT}/health"
    
    local retries=0
    while [ $retries -lt $MAX_RETRIES ]; do
        print_info "Checking MLflow health (attempt $((retries + 1))/$MAX_RETRIES)..."
        
        if curl -sf "$HEALTH_URL" > /dev/null; then
            print_success "MLflow is healthy"
            return 0
        fi
        
        retries=$((retries + 1))
        if [ $retries -lt $MAX_RETRIES ]; then
            print_warn "MLflow not ready yet. Waiting ${RETRY_DELAY}s..."
            sleep $RETRY_DELAY
        fi
    done
    
    print_error "MLflow health check failed after $MAX_RETRIES attempts"
    return 1
}

# Validate S3 buckets
validate_s3_buckets() {
    print_info "Validating S3 buckets..."
    
    ARTIFACTS_BUCKET=$(cd "$TERRAFORM_DIR" && terraform output -raw s3_artifacts_bucket)
    PIPELINE_BUCKET=$(cd "$TERRAFORM_DIR" && terraform output -raw s3_pipeline_bucket)
    
    # Check artifacts bucket
    if aws s3 ls "s3://${ARTIFACTS_BUCKET}" &>/dev/null; then
        print_success "Artifacts bucket accessible: $ARTIFACTS_BUCKET"
    else
        print_error "Cannot access artifacts bucket: $ARTIFACTS_BUCKET"
        return 1
    fi
    
    # Check pipeline bucket
    if aws s3 ls "s3://${PIPELINE_BUCKET}" &>/dev/null; then
        print_success "Pipeline bucket accessible: $PIPELINE_BUCKET"
    else
        print_error "Cannot access pipeline bucket: $PIPELINE_BUCKET"
        return 1
    fi
}

# Validate RDS database
validate_rds_database() {
    print_info "Validating RDS database..."
    
    DB_INSTANCE_ID=$(cd "$TERRAFORM_DIR" && terraform output -raw database_endpoint | cut -d: -f1)
    
    # Check database status
    DB_STATUS=$(aws rds describe-db-instances \
        --db-instance-identifier "$DB_INSTANCE_ID" \
        --query 'DBInstances[0].DBInstanceStatus' \
        --output text 2>/dev/null || echo "not-found")
    
    if [ "$DB_STATUS" = "available" ]; then
        print_success "RDS database is available"
    else
        print_error "RDS database status: $DB_STATUS (expected: available)"
        return 1
    fi
}

# Validate ECS services
validate_ecs_services() {
    print_info "Validating ECS services..."
    
    CLUSTER_NAME=$(cd "$TERRAFORM_DIR" && terraform output -raw ecs_cluster_name)
    
    # Check API service
    API_STATUS=$(aws ecs describe-services \
        --cluster "$CLUSTER_NAME" \
        --services hokusai-api \
        --query 'services[0].desiredCount' \
        --output text 2>/dev/null || echo "0")
    
    if [ "$API_STATUS" -gt 0 ]; then
        print_success "API service is running with $API_STATUS tasks"
    else
        print_warn "API service not found or not running"
    fi
    
    # Check MLflow service
    MLFLOW_STATUS=$(aws ecs describe-services \
        --cluster "$CLUSTER_NAME" \
        --services hokusai-mlflow \
        --query 'services[0].desiredCount' \
        --output text 2>/dev/null || echo "0")
    
    if [ "$MLFLOW_STATUS" -gt 0 ]; then
        print_success "MLflow service is running with $MLFLOW_STATUS tasks"
    else
        print_warn "MLflow service not found or not running"
    fi
}

# Validate load balancer
validate_load_balancer() {
    print_info "Validating load balancer..."
    
    ALB_ARN=$(cd "$TERRAFORM_DIR" && terraform output -raw alb_arn 2>/dev/null || echo "")
    
    if [ -z "$ALB_ARN" ]; then
        print_warn "Load balancer ARN not found in outputs"
        return
    fi
    
    # Check ALB status
    ALB_STATUS=$(aws elbv2 describe-load-balancers \
        --load-balancer-arns "$ALB_ARN" \
        --query 'LoadBalancers[0].State.Code' \
        --output text 2>/dev/null || echo "not-found")
    
    if [ "$ALB_STATUS" = "active" ]; then
        print_success "Load balancer is active"
    else
        print_error "Load balancer status: $ALB_STATUS (expected: active)"
        return 1
    fi
}

# Run basic API tests
run_api_tests() {
    print_info "Running basic API tests..."
    
    API_ENDPOINT=$(cd "$TERRAFORM_DIR" && terraform output -raw api_endpoint)
    
    # Test health endpoint
    if curl -sf "${API_ENDPOINT}/health" > /dev/null; then
        print_success "Health endpoint test passed"
    else
        print_error "Health endpoint test failed"
        return 1
    fi
    
    # Test API docs
    if curl -sf "${API_ENDPOINT}/docs" > /dev/null; then
        print_success "API documentation accessible"
    else
        print_warn "API documentation not accessible"
    fi
}

# Generate validation report
generate_report() {
    print_info "Generating validation report..."
    
    REPORT_FILE="$SCRIPT_DIR/validation_report_$(date +%Y%m%d_%H%M%S).txt"
    
    {
        echo "Hokusai Infrastructure Validation Report"
        echo "========================================"
        echo "Date: $(date)"
        echo "Environment: ${ENVIRONMENT:-unknown}"
        echo "AWS Region: ${AWS_REGION:-unknown}"
        echo ""
        echo "Endpoints:"
        cd "$TERRAFORM_DIR"
        echo "  API: $(terraform output -raw api_endpoint 2>/dev/null || echo 'N/A')"
        echo "  MLflow: $(terraform output -raw mlflow_endpoint 2>/dev/null || echo 'N/A')"
        echo ""
        echo "Resources:"
        echo "  S3 Artifacts: $(terraform output -raw s3_artifacts_bucket 2>/dev/null || echo 'N/A')"
        echo "  S3 Pipeline: $(terraform output -raw s3_pipeline_bucket 2>/dev/null || echo 'N/A')"
        echo "  ECS Cluster: $(terraform output -raw ecs_cluster_name 2>/dev/null || echo 'N/A')"
    } > "$REPORT_FILE"
    
    print_info "Validation report saved to: $REPORT_FILE"
}

# Main validation function
main() {
    print_info "Starting Hokusai infrastructure validation..."
    
    local all_passed=true
    
    # Run validation checks
    check_terraform_outputs || all_passed=false
    validate_api_health || all_passed=false
    validate_mlflow_health || all_passed=false
    validate_s3_buckets || all_passed=false
    validate_rds_database || all_passed=false
    validate_ecs_services || all_passed=false
    validate_load_balancer || all_passed=false
    run_api_tests || all_passed=false
    
    # Generate report
    generate_report
    
    # Summary
    echo ""
    if [ "$all_passed" = true ]; then
        print_success "All validation checks passed!"
        exit 0
    else
        print_error "Some validation checks failed. Please review the output above."
        exit 1
    fi
}

# Run main function
main "$@"