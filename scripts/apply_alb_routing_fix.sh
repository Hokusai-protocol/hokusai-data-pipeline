#!/bin/bash

# Script to apply ALB routing fixes for PR #60 enhancements
# This updates the ALB routing rules to properly handle /mlflow/* and /api/health/* paths

set -e

echo "=== ALB Routing Fix Deployment Script ==="
echo "This script will update the ALB routing rules to fix conflicts"
echo

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check AWS CLI
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo -e "${RED}Error: AWS CLI not configured. Please run 'aws configure'${NC}"
    exit 1
fi

# Get current directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
TERRAFORM_DIR="$PROJECT_ROOT/infrastructure/terraform"

# Check if terraform directory exists
if [ ! -d "$TERRAFORM_DIR" ]; then
    echo -e "${RED}Error: Terraform directory not found at $TERRAFORM_DIR${NC}"
    exit 1
fi

cd "$TERRAFORM_DIR"

echo -e "${YELLOW}Step 1: Backing up current terraform state${NC}"
if [ -f terraform.tfstate ]; then
    cp terraform.tfstate terraform.tfstate.backup.$(date +%Y%m%d-%H%M%S)
    echo -e "${GREEN}✓ State backed up${NC}"
fi

echo -e "\n${YELLOW}Step 2: Commenting out conflicting rule in main.tf${NC}"
# Create a backup of main.tf
cp main.tf main.tf.backup

# Comment out the broad /api* rule (priority 100)
sed -i.bak '
/resource "aws_lb_listener_rule" "api" {/,/^}$/ {
    s/^/# /
}
' main.tf

echo -e "${GREEN}✓ Conflicting rule commented out${NC}"

echo -e "\n${YELLOW}Step 3: Planning terraform changes${NC}"
terraform init
terraform plan -out=alb-routing-fix.plan

echo -e "\n${YELLOW}Review the plan above. Do you want to apply these changes? (yes/no)${NC}"
read -r response

if [[ "$response" != "yes" ]]; then
    echo "Aborting. Restoring original main.tf"
    mv main.tf.backup main.tf
    rm -f main.tf.bak
    exit 0
fi

echo -e "\n${YELLOW}Step 4: Applying terraform changes${NC}"
terraform apply alb-routing-fix.plan

echo -e "\n${GREEN}✓ ALB routing rules updated successfully!${NC}"

echo -e "\n${YELLOW}Step 5: Verifying the changes${NC}"

# Get the ALB DNS name
ALB_DNS=$(terraform output -raw alb_dns_name 2>/dev/null || echo "")

if [ -z "$ALB_DNS" ]; then
    echo -e "${YELLOW}Warning: Could not get ALB DNS name from terraform output${NC}"
    ALB_DNS="registry.hokus.ai"
fi

echo "Testing endpoints on $ALB_DNS..."

# Function to test endpoint
test_endpoint() {
    local path=$1
    local expected_status=$2
    local description=$3
    
    echo -n "  Testing $path - $description: "
    
    status=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: registry.hokus.ai" "http://$ALB_DNS$path")
    
    if [ "$status" = "$expected_status" ]; then
        echo -e "${GREEN}✓ Got $status as expected${NC}"
        return 0
    else
        echo -e "${RED}✗ Got $status, expected $expected_status${NC}"
        return 1
    fi
}

# Test the routing
echo
test_endpoint "/api/mlflow/api/2.0/mlflow/experiments/search" "401" "MLflow proxy (should require auth)"
test_endpoint "/mlflow" "200" "Direct MLflow access"
test_endpoint "/api/health/mlflow" "404" "Health endpoint (not implemented yet)"
test_endpoint "/api/v1/models" "401" "Regular API endpoint"

echo -e "\n${GREEN}Deployment complete!${NC}"
echo
echo "Next steps:"
echo "1. Update the health check endpoints in the code to use /api/health/mlflow"
echo "2. Test model registration with the verify_model_registration.py script"
echo "3. Update monitoring to use the new health check endpoints"
echo
echo "To rollback if needed:"
echo "  cd $TERRAFORM_DIR"
echo "  mv main.tf.backup main.tf"
echo "  terraform apply"