#!/bin/bash
# Quick fix to ensure the improved proxy is deployed

set -e

echo "=== Quick Fix Deployment ==="

# Build and push a fresh image with explicit tag
echo "Building fresh image..."
docker build -f Dockerfile.api -t hokusai-api:proxy-fix-final --platform linux/amd64 . || exit 1

# Tag and push
ECR_REPO="932100697590.dkr.ecr.us-east-1.amazonaws.com/hokusai-api"
docker tag hokusai-api:proxy-fix-final ${ECR_REPO}:proxy-fix-final

echo "Logging into ECR..."
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ${ECR_REPO}

echo "Pushing image..."
docker push ${ECR_REPO}:proxy-fix-final

# Create a new task definition with the fresh image
echo "Creating new task definition..."
aws ecs describe-task-definition \
    --task-definition hokusai-api-development:43 \
    --region us-east-1 \
    --query 'taskDefinition' | \
    jq --arg image "${ECR_REPO}:proxy-fix-final" \
    '.containerDefinitions[0].image = $image | 
     del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy)' > task-def-final.json

# Register new task definition
NEW_TASK_DEF=$(aws ecs register-task-definition \
    --cli-input-json file://task-def-final.json \
    --region us-east-1 \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

echo "New task definition: $NEW_TASK_DEF"

# Update service
echo "Updating service..."
aws ecs update-service \
    --cluster hokusai-development \
    --service hokusai-api \
    --task-definition $NEW_TASK_DEF \
    --desired-count 2 \
    --force-new-deployment \
    --region us-east-1 \
    --output json > /dev/null

echo "Deployment initiated. Waiting for stabilization..."
sleep 30

# Check status
aws ecs describe-services \
    --cluster hokusai-development \
    --services hokusai-api \
    --region us-east-1 \
    --query 'services[0].[runningCount,desiredCount,deployments[0].status]' \
    --output text

echo
echo "Testing in 60 seconds..."
sleep 60

# Test
echo "Testing endpoints..."
curl -s https://registry.hokus.ai/api/mlflow/health/mlflow | jq . || echo "Failed"

# Cleanup
rm -f task-def-final.json