#!/bin/bash

set -e

REGION="us-east-1"
ACCOUNT_ID="932100697590"
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
API_IMAGE="${ECR_REGISTRY}/hokusai/api"
CLUSTER="hokusai-development"
API_SERVICE="hokusai-api-development"

echo "🚀 Deploying Redis Connection Fix"
echo "================================"

# Login to ECR
echo "📦 Logging into ECR..."
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_REGISTRY

# Build the API image
echo "🔨 Building API Docker image..."
docker build -t hokusai-api:latest -f Dockerfile.api .

# Tag for ECR
echo "🏷️  Tagging image for ECR..."
docker tag hokusai-api:latest ${API_IMAGE}:latest
docker tag hokusai-api:latest ${API_IMAGE}:redis-fix

# Push to ECR
echo "⬆️  Pushing to ECR..."
docker push ${API_IMAGE}:latest
docker push ${API_IMAGE}:redis-fix

# Force new deployment
echo "🔄 Updating ECS service..."
aws ecs update-service \
    --cluster $CLUSTER \
    --service $API_SERVICE \
    --force-new-deployment \
    --region $REGION \
    --output json > /dev/null

echo "✅ Deployment initiated!"
echo ""
echo "📊 Monitor deployment:"
echo "  aws ecs describe-services --cluster $CLUSTER --services $API_SERVICE --region $REGION"
echo ""
echo "📋 Watch logs:"
echo "  aws logs tail /ecs/hokusai-api-development --follow"
echo ""
echo "🔍 Test Redis connection:"
echo "  curl https://registry.hokus.ai/health | jq '.services.redis'"