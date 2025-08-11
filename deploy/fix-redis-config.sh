#!/bin/bash

set -e

REGION="us-east-1"
CLUSTER="hokusai-development"
API_SERVICE="hokusai-api-development"

echo "🔧 Fixing Redis Configuration in ECS Task Definition"
echo "===================================================="

# Get current task definition
echo "📋 Fetching current task definition..."
aws ecs describe-task-definition \
    --task-definition hokusai-api-development \
    --region $REGION > current-task-def.json

# Update to use environment variables instead of SSM parameters for Redis host/port
echo "✏️  Updating Redis configuration..."
jq '.taskDefinition | 
    del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy) |
    # Remove Redis configs from secrets
    .containerDefinitions[0].secrets = [.containerDefinitions[0].secrets[] | select(.name | IN("DB_PASSWORD", "REDIS_AUTH_TOKEN"))] |
    # Add Redis host and port as environment variables
    .containerDefinitions[0].environment = (
        [.containerDefinitions[0].environment[] | select(.name | IN("REDIS_HOST", "REDIS_PORT") | not)] +
        [
            {
                "name": "REDIS_HOST",
                "value": "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com"
            },
            {
                "name": "REDIS_PORT", 
                "value": "6379"
            }
        ]
    )' current-task-def.json > fixed-task-def.json

echo "📝 Task definition updated. Registering..."

# Register the fixed task definition
NEW_TASK_ARN=$(aws ecs register-task-definition \
    --cli-input-json file://fixed-task-def.json \
    --region $REGION \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

echo "✅ New task definition registered: $NEW_TASK_ARN"

# Update the service
echo "🔄 Updating ECS service..."
aws ecs update-service \
    --cluster $CLUSTER \
    --service $API_SERVICE \
    --task-definition $NEW_TASK_ARN \
    --force-new-deployment \
    --region $REGION \
    --output json > /dev/null

echo "✅ Service update initiated"

echo ""
echo "📊 Monitoring deployment..."
echo "Check status with:"
echo "  aws ecs describe-services --cluster $CLUSTER --services $API_SERVICE --region $REGION"
echo ""
echo "Watch logs with:"
echo "  aws logs tail /ecs/hokusai-api-development --follow"