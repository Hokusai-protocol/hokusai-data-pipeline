#!/bin/bash
# Force deployment with improved proxy module

set -e

echo "=== Force Deployment of Proxy Fix ==="

# Step 1: Stop the current deployment
echo "Stopping current deployment..."
aws ecs update-service \
    --cluster hokusai-development \
    --service hokusai-api \
    --desired-count 0 \
    --region us-east-1

echo "Waiting for tasks to stop..."
sleep 30

# Step 2: Force new deployment with updated task definition
echo "Starting new deployment with task definition 43..."
aws ecs update-service \
    --cluster hokusai-development \
    --service hokusai-api \
    --task-definition hokusai-api-development:43 \
    --desired-count 2 \
    --force-new-deployment \
    --region us-east-1

echo "Deployment initiated. Monitoring status..."

# Step 3: Watch the deployment
for i in {1..20}; do
    echo -n "Checking deployment status (attempt $i/20)... "
    RUNNING=$(aws ecs describe-services \
        --cluster hokusai-development \
        --services hokusai-api \
        --region us-east-1 \
        --query 'services[0].runningCount' \
        --output text)
    echo "Running: $RUNNING"
    
    if [ "$RUNNING" -eq "2" ]; then
        echo "Deployment successful!"
        break
    fi
    
    sleep 15
done

# Check final status
echo
echo "Final deployment status:"
aws ecs describe-services \
    --cluster hokusai-development \
    --services hokusai-api \
    --region us-east-1 \
    --query 'services[0].deployments[*].[taskDefinition,desiredCount,runningCount,status]' \
    --output table

# Test the endpoints
echo
echo "Testing endpoints..."
curl -s -w "\n/health: %{http_code}\n" -o /dev/null https://registry.hokus.ai/health
curl -s -w "\n/api/mlflow/health/mlflow: %{http_code}\n" -o /dev/null https://registry.hokus.ai/api/mlflow/health/mlflow