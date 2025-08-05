#!/bin/bash

# Update ECS Services to Use Centralized Target Groups
# This script updates the existing ECS services to point to the centralized infrastructure target groups

set -e

echo "=== Updating ECS Services to Use Centralized Target Groups ==="
echo

# Target Group ARNs from centralized infrastructure
API_TG_ARN="arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81"
MLFLOW_TG_ARN="arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-mlflow-tg-development/9518cac0d6af96bb"

echo "Current service configuration:"
aws ecs describe-services --cluster hokusai-development --services hokusai-api hokusai-mlflow \
  --query 'services[*].[serviceName,loadBalancers[0].targetGroupArn]' --output table

echo
echo "This script will update the services to use these centralized target groups:"
echo "- API Service: $API_TG_ARN"
echo "- MLflow Service: $MLFLOW_TG_ARN"
echo
echo "WARNING: This will cause a brief service interruption during the update."
echo "Do you want to continue? (yes/no)"
read -r response

if [ "$response" != "yes" ]; then
    echo "Update cancelled."
    exit 0
fi

# Get the current task definitions
echo
echo "Getting current task definitions..."
API_TASK_DEF=$(aws ecs describe-services --cluster hokusai-development --services hokusai-api \
  --query 'services[0].taskDefinition' --output text)
MLFLOW_TASK_DEF=$(aws ecs describe-services --cluster hokusai-development --services hokusai-mlflow \
  --query 'services[0].taskDefinition' --output text)

echo "Current task definitions:"
echo "- API: $API_TASK_DEF"
echo "- MLflow: $MLFLOW_TASK_DEF"

# Update API service
echo
echo "Updating API service..."
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-api \
  --load-balancers targetGroupArn=$API_TG_ARN,containerName=hokusai-api,containerPort=8001 \
  --force-new-deployment

# Update MLflow service  
echo
echo "Updating MLflow service..."
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-mlflow \
  --load-balancers targetGroupArn=$MLFLOW_TG_ARN,containerName=hokusai-mlflow,containerPort=5000 \
  --force-new-deployment

echo
echo "=== Services Updated ==="
echo
echo "The services are now being updated to use the centralized target groups."
echo "This process may take a few minutes."
echo
echo "To monitor the deployment:"
echo "aws ecs describe-services --cluster hokusai-development --services hokusai-api hokusai-mlflow \\"
echo "  --query 'services[*].[serviceName,deployments[0].status,deployments[0].desiredCount,deployments[0].runningCount]' --output table"
echo
echo "Once the deployment is complete, verify target group health:"
echo "aws elbv2 describe-target-health --target-group-arn $API_TG_ARN"
echo "aws elbv2 describe-target-health --target-group-arn $MLFLOW_TG_ARN"
echo
echo "Next steps:"
echo "1. Wait for services to stabilize (5-10 minutes)"
echo "2. Verify target groups show healthy targets"
echo "3. Contact infrastructure team to enable listener rules"
echo "4. Test the endpoints through the centralized ALBs"