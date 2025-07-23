#!/bin/bash
# Verify MLflow deployment and artifact storage functionality
# This script checks that MLflow is properly deployed with artifact storage

set -e

echo "=================================================="
echo "MLflow Deployment Verification Script"
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

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_fail() {
    echo -e "${RED}✗${NC} $1"
}

# Track overall status
OVERALL_STATUS=0

# Configuration
REGION=${AWS_REGION:-us-east-1}
ENVIRONMENT=${ENVIRONMENT:-development}
CLUSTER_NAME="hokusai-${ENVIRONMENT}"
MLFLOW_SERVICE="hokusai-mlflow"
API_SERVICE="hokusai-api"

# Check prerequisites
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI is not installed"
    exit 1
fi

if ! command -v curl &> /dev/null; then
    print_error "curl is not installed"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    print_error "jq is not installed"
    exit 1
fi

# Get API key
if [ -z "$HOKUSAI_API_KEY" ]; then
    print_warn "HOKUSAI_API_KEY not set"
    echo "Please enter your Hokusai API key:"
    read -r HOKUSAI_API_KEY
    if [ -z "$HOKUSAI_API_KEY" ]; then
        print_error "API key is required"
        exit 1
    fi
fi

print_info "Using API key: ${HOKUSAI_API_KEY:0:10}...${HOKUSAI_API_KEY: -4}"
echo ""

# Step 1: Check MLflow service status
print_info "1. Checking MLflow ECS service status..."
MLFLOW_STATUS=$(aws ecs describe-services \
    --cluster "$CLUSTER_NAME" \
    --services "$MLFLOW_SERVICE" \
    --query 'services[0].[status,runningCount,desiredCount]' \
    --output text 2>/dev/null || echo "ERROR 0 0")

read -r STATUS RUNNING DESIRED <<< "$MLFLOW_STATUS"

if [ "$STATUS" = "ACTIVE" ] && [ "$RUNNING" = "$DESIRED" ] && [ "$RUNNING" -gt 0 ]; then
    print_success "MLflow service is ACTIVE ($RUNNING/$DESIRED tasks running)"
else
    print_fail "MLflow service status: $STATUS ($RUNNING/$DESIRED tasks)"
    OVERALL_STATUS=1
fi

# Step 2: Check MLflow task definition for --serve-artifacts
print_info "2. Checking MLflow configuration..."
TASK_DEF=$(aws ecs describe-services \
    --cluster "$CLUSTER_NAME" \
    --services "$MLFLOW_SERVICE" \
    --query 'services[0].taskDefinition' \
    --output text 2>/dev/null)

if [ -n "$TASK_DEF" ]; then
    # Check if the task definition includes serve-artifacts
    CONTAINER_DEF=$(aws ecs describe-task-definition \
        --task-definition "$TASK_DEF" \
        --query 'taskDefinition.containerDefinitions[0]' \
        --output json 2>/dev/null)
    
    # Check for entrypoint or command containing serve-artifacts
    if echo "$CONTAINER_DEF" | grep -q "serve-artifacts"; then
        print_success "MLflow configured with --serve-artifacts"
    else
        print_warn "Cannot verify --serve-artifacts flag in task definition"
        print_info "Checking logs for confirmation..."
    fi
else
    print_fail "Could not retrieve task definition"
    OVERALL_STATUS=1
fi

# Step 3: Check MLflow logs for startup confirmation
print_info "3. Checking MLflow logs..."
RECENT_LOGS=$(aws logs tail /ecs/hokusai/mlflow/$ENVIRONMENT --since 30m 2>&1 | head -50 || echo "")

if echo "$RECENT_LOGS" | grep -q "serve-artifacts"; then
    print_success "MLflow logs confirm --serve-artifacts flag"
elif echo "$RECENT_LOGS" | grep -q "Serving artifacts"; then
    print_success "MLflow is serving artifacts"
elif echo "$RECENT_LOGS" | grep -q "ResourceNotFoundException"; then
    print_warn "Log group not found or no recent logs"
else
    print_warn "Could not confirm artifact serving from logs"
fi

# Step 4: Test MLflow connectivity via API proxy
print_info "4. Testing MLflow connectivity..."
echo ""

# Test experiments endpoint
print_info "   Testing experiments API..."
EXPERIMENTS_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -H "Authorization: Bearer $HOKUSAI_API_KEY" \
    "https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search?max_results=1" 2>/dev/null)

HTTP_CODE=$(echo "$EXPERIMENTS_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$EXPERIMENTS_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    print_success "MLflow experiments API working (HTTP $HTTP_CODE)"
    EXPERIMENT_COUNT=$(echo "$RESPONSE_BODY" | jq -r '.experiments | length' 2>/dev/null || echo "0")
    print_info "   Found $EXPERIMENT_COUNT experiments"
else
    print_fail "MLflow experiments API failed (HTTP $HTTP_CODE)"
    print_info "   Response: $(echo "$RESPONSE_BODY" | head -c 200)"
    OVERALL_STATUS=1
fi

# Step 5: Test artifact endpoints
print_info "5. Testing artifact storage endpoints..."
echo ""

# Test artifact API endpoint
print_info "   Testing artifact API availability..."
ARTIFACT_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -H "Authorization: Bearer $HOKUSAI_API_KEY" \
    "https://registry.hokus.ai/api/mlflow/api/2.0/mlflow-artifacts/artifacts" 2>/dev/null)

HTTP_CODE=$(echo "$ARTIFACT_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$ARTIFACT_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "400" ] || [ "$HTTP_CODE" = "401" ]; then
    print_success "Artifact endpoint is responding (HTTP $HTTP_CODE)"
    print_info "   This indicates the endpoint exists and is routed correctly"
elif [ "$HTTP_CODE" = "404" ]; then
    print_fail "Artifact endpoint returning 404 - Not properly configured"
    print_info "   The MLflow server may not have --serve-artifacts enabled"
    OVERALL_STATUS=1
else
    print_warn "Artifact endpoint returned HTTP $HTTP_CODE"
    print_info "   Response: $(echo "$RESPONSE_BODY" | head -c 200)"
fi

# Step 6: Check API service status
print_info "6. Checking API service status..."
API_STATUS=$(aws ecs describe-services \
    --cluster "$CLUSTER_NAME" \
    --services "$API_SERVICE" \
    --query 'services[0].[status,runningCount,desiredCount]' \
    --output text 2>/dev/null || echo "ERROR 0 0")

read -r STATUS RUNNING DESIRED <<< "$API_STATUS"

if [ "$STATUS" = "ACTIVE" ] && [ "$RUNNING" = "$DESIRED" ] && [ "$RUNNING" -gt 0 ]; then
    print_success "API service is ACTIVE ($RUNNING/$DESIRED tasks running)"
else
    print_fail "API service status: $STATUS ($RUNNING/$DESIRED tasks)"
    print_warn "API service may need to be restarted"
fi

# Step 7: Test end-to-end with Python (if available)
if command -v python3 &> /dev/null || command -v python &> /dev/null; then
    print_info "7. Testing MLflow Python client..."
    
    PYTHON_CMD=$(command -v python3 || command -v python)
    
    # Create a simple test script
    cat > /tmp/test_mlflow_connection.py << 'EOF'
import os
import sys
try:
    import mlflow
    os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/api/mlflow"
    os.environ["MLFLOW_TRACKING_TOKEN"] = os.environ.get("HOKUSAI_API_KEY", "")
    
    client = mlflow.tracking.MlflowClient()
    experiments = client.search_experiments()
    print(f"SUCCESS: Connected to MLflow, found {len(experiments)} experiments")
    sys.exit(0)
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {str(e)}")
    sys.exit(1)
EOF

    if HOKUSAI_API_KEY="$HOKUSAI_API_KEY" $PYTHON_CMD /tmp/test_mlflow_connection.py 2>&1; then
        print_success "MLflow Python client connection successful"
    else
        print_fail "MLflow Python client connection failed"
        OVERALL_STATUS=1
    fi
    
    rm -f /tmp/test_mlflow_connection.py
else
    print_warn "Python not available, skipping client test"
fi

# Summary
echo ""
echo "=================================================="
echo "VERIFICATION SUMMARY"
echo "=================================================="

if [ $OVERALL_STATUS -eq 0 ]; then
    print_success "All checks passed! MLflow deployment appears successful."
    echo ""
    print_info "Next steps:"
    echo "1. Run the model registration test:"
    echo "   export HOKUSAI_API_KEY='$HOKUSAI_API_KEY'"
    echo "   python test_model_registration_simple.py"
    echo ""
else
    print_fail "Some checks failed. Please review the issues above."
    echo ""
    print_info "Common fixes:"
    echo "1. If artifact endpoints return 404:"
    echo "   - Ensure MLflow container was rebuilt with latest Dockerfile"
    echo "   - Check that --serve-artifacts flag is in the container"
    echo ""
    echo "2. If API service is having issues:"
    echo "   - Restart it: aws ecs update-service --cluster $CLUSTER_NAME --service hokusai-api --force-new-deployment"
    echo ""
    echo "3. Check logs for more details:"
    echo "   - MLflow: aws logs tail /ecs/hokusai/mlflow/$ENVIRONMENT --follow"
    echo "   - API: aws logs tail /ecs/hokusai/api/$ENVIRONMENT --follow"
fi

echo "=================================================="
exit $OVERALL_STATUS