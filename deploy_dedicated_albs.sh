#!/bin/bash
# Deploy Dedicated ALBs for Hokusai Platform
# This script deploys ALBs without Route53 configuration

set -e  # Exit on error

echo "=================================================="
echo "Hokusai Dedicated ALB Deployment Script"
echo "=================================================="
echo ""

# Check prerequisites
echo "Checking prerequisites..."
if ! command -v terraform &> /dev/null; then
    echo "ERROR: Terraform is not installed"
    exit 1
fi

if ! command -v aws &> /dev/null; then
    echo "ERROR: AWS CLI is not installed"
    exit 1
fi

# Verify AWS credentials
echo "Verifying AWS access..."
if ! aws sts get-caller-identity &> /dev/null; then
    echo "ERROR: AWS credentials not configured"
    exit 1
fi

# Get into the right directory
cd "$(dirname "$0")/infrastructure/terraform"

# Initialize Terraform
echo ""
echo "Initializing Terraform..."
terraform init

# Create a plan
echo ""
echo "Creating deployment plan..."
terraform plan -out=dedicated-albs.tfplan \
  -target=aws_lb_target_group.auth \
  -target=aws_lb_target_group.registry_api \
  -target=aws_lb_target_group.registry_mlflow \
  -target=aws_lb.auth \
  -target=aws_lb.registry \
  -target=aws_lb_listener.auth_http \
  -target=aws_lb_listener.auth_https \
  -target=aws_lb_listener.registry_http \
  -target=aws_lb_listener.registry_https \
  -target=aws_lb_listener_rule.auth_api_v1 \
  -target=aws_lb_listener_rule.auth_health \
  -target=aws_lb_listener_rule.dedicated_registry_mlflow \
  -target=aws_lb_listener_rule.dedicated_registry_api_mlflow \
  -target=aws_lb_listener_rule.dedicated_registry_api

# Ask for confirmation
echo ""
echo "=================================================="
echo "Review the plan above. Deploy these resources?"
echo "Type 'yes' to continue, anything else to abort:"
read -r response

if [[ "$response" != "yes" ]]; then
    echo "Deployment cancelled"
    exit 0
fi

# Apply the plan
echo ""
echo "Deploying ALBs..."
terraform apply dedicated-albs.tfplan

# Get the ALB DNS names
echo ""
echo "=================================================="
echo "Deployment Complete!"
echo "=================================================="
echo ""
echo "ALB DNS Names:"
echo "-------------"
AUTH_DNS=$(terraform output -raw auth_alb_dns 2>/dev/null || echo "Not found")
REGISTRY_DNS=$(terraform output -raw registry_alb_dns 2>/dev/null || echo "Not found")

echo "Auth ALB:     $AUTH_DNS"
echo "Registry ALB: $REGISTRY_DNS"

# Test the ALBs
echo ""
echo "Testing ALBs (using Host headers)..."
echo "------------------------------------"

if [[ "$AUTH_DNS" != "Not found" ]]; then
    echo -n "Auth health check: "
    if curl -sf -H "Host: auth.hokus.ai" "https://${AUTH_DNS}/health" -k -o /dev/null; then
        echo "✓ SUCCESS"
    else
        echo "✗ FAILED"
    fi
fi

if [[ "$REGISTRY_DNS" != "Not found" ]]; then
    echo -n "Registry health check: "
    if curl -sf -H "Host: registry.hokus.ai" "https://${REGISTRY_DNS}/health" -k -o /dev/null; then
        echo "✓ SUCCESS"
    else
        echo "✗ FAILED"
    fi
fi

# Next steps
echo ""
echo "=================================================="
echo "Next Steps:"
echo "=================================================="
echo ""
echo "1. Update Namecheap DNS records:"
echo "   - auth.hokus.ai    → CNAME to $AUTH_DNS"
echo "   - registry.hokus.ai → CNAME to $REGISTRY_DNS"
echo ""
echo "2. See NAMECHEAP_DNS_UPDATE_GUIDE.md for detailed instructions"
echo ""
echo "3. After DNS propagates, run:"
echo "   export HOKUSAI_API_KEY='your-api-key'"
echo "   python test_dedicated_albs.py"
echo ""
echo "=================================================="