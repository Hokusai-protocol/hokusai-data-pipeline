#!/bin/bash

# Deploy ECS Services Script
# This script helps deploy the ECS services using the centralized infrastructure

set -e

echo "=== Data Pipeline ECS Services Deployment ==="
echo

# Check if we're in the right directory
if [ ! -f "main.tf" ]; then
    echo "Error: Please run this script from the infrastructure/terraform directory"
    exit 1
fi

# Step 1: Initialize Terraform
echo "Step 1: Initializing Terraform..."
terraform init -backend-config="bucket=hokusai-data-pipeline-tfstate" \
               -backend-config="key=terraform.tfstate" \
               -backend-config="region=us-east-1"

# Step 2: Create a plan
echo
echo "Step 2: Creating deployment plan..."
terraform plan -out=deploy.tfplan

# Step 3: Review the plan
echo
echo "Step 3: Please review the plan above. Do you want to proceed with deployment? (yes/no)"
read -r response

if [ "$response" != "yes" ]; then
    echo "Deployment cancelled."
    exit 0
fi

# Step 4: Apply the configuration
echo
echo "Step 4: Applying configuration..."
terraform apply deploy.tfplan

# Step 5: Get the outputs
echo
echo "Step 5: Deployment complete! Getting service information..."
echo

# Get ECS service status
echo "ECS Services Status:"
aws ecs describe-services \
    --cluster hokusai-development \
    --services hokusai-api hokusai-mlflow \
    --query 'services[*].[serviceName,status,desiredCount,runningCount]' \
    --output table

echo
echo "Target Group ARNs for centralized infrastructure:"
echo "- API Target Group: arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81"
echo "- MLflow Target Group: arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-mlflow-tg-development/9518cac0d6af96bb"

echo
echo "=== Next Steps ==="
echo "1. Share these target group ARNs with the infrastructure team"
echo "2. Request them to enable the listener rules in environments/data-pipeline-ecs-alb-integration.tf"
echo "3. Once listener rules are enabled, test the endpoints:"
echo "   - API: https://hokusai-dp-development-465790699.us-east-1.elb.amazonaws.com/api/health"
echo "   - MLflow: https://hokusai-dp-development-465790699.us-east-1.elb.amazonaws.com/mlflow"