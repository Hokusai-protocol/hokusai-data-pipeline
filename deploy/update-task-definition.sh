#!/bin/bash

# Script to update ECS task definitions with Redis configuration

set -e

REGION="us-east-1"
CLUSTER="hokusai-development"
API_SERVICE="hokusai-api-development"
MLFLOW_SERVICE="hokusai-mlflow-development"

echo "🚀 Deploying Redis Queue Integration to ECS"
echo "=========================================="

# Get current task definition for API service
echo "📋 Fetching current API task definition..."
CURRENT_TASK_DEF=$(aws ecs describe-task-definition \
    --task-definition hokusai-api-development \
    --region $REGION)

# Extract the task definition and add Redis environment variables
echo "✏️  Adding Redis configuration to API service..."
NEW_TASK_DEF=$(echo $CURRENT_TASK_DEF | jq '.taskDefinition | 
    del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy) |
    .containerDefinitions[0].environment += [
        {
            "name": "REDIS_HOST",
            "value": "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com"
        },
        {
            "name": "REDIS_PORT",
            "value": "6379"
        }
    ] |
    if (.containerDefinitions[0].secrets | type) == "array" then
        .containerDefinitions[0].secrets += [
            {
                "name": "REDIS_AUTH_TOKEN",
                "valueFrom": "arn:aws:secretsmanager:us-east-1:932100697590:secret:hokusai/redis/development/auth-token"
            }
        ]
    else
        .containerDefinitions[0].secrets = [
            {
                "name": "REDIS_AUTH_TOKEN",
                "valueFrom": "arn:aws:secretsmanager:us-east-1:932100697590:secret:hokusai/redis/development/auth-token"
            }
        ]
    end')

# Save the new task definition
echo "$NEW_TASK_DEF" > api-task-definition.json

# Register the new task definition
echo "📝 Registering new API task definition..."
API_TASK_ARN=$(aws ecs register-task-definition \
    --cli-input-json file://api-task-definition.json \
    --region $REGION \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

echo "✅ New API task definition registered: $API_TASK_ARN"

# Update the API service
echo "🔄 Updating API service with new task definition..."
aws ecs update-service \
    --cluster $CLUSTER \
    --service $API_SERVICE \
    --task-definition $API_TASK_ARN \
    --force-new-deployment \
    --region $REGION \
    --output json > /dev/null

echo "✅ API service update initiated"

# Do the same for MLflow service
echo ""
echo "📋 Fetching current MLflow task definition..."
CURRENT_MLFLOW_DEF=$(aws ecs describe-task-definition \
    --task-definition hokusai-mlflow-development \
    --region $REGION)

# Add Redis configuration to MLflow service
echo "✏️  Adding Redis configuration to MLflow service..."
NEW_MLFLOW_DEF=$(echo $CURRENT_MLFLOW_DEF | jq '.taskDefinition | 
    del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy) |
    .containerDefinitions[0].environment += [
        {
            "name": "REDIS_HOST",
            "value": "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com"
        },
        {
            "name": "REDIS_PORT",
            "value": "6379"
        }
    ] |
    if (.containerDefinitions[0].secrets | type) == "array" then
        .containerDefinitions[0].secrets += [
            {
                "name": "REDIS_AUTH_TOKEN",
                "valueFrom": "arn:aws:secretsmanager:us-east-1:932100697590:secret:hokusai/redis/development/auth-token"
            }
        ]
    else
        .containerDefinitions[0].secrets = [
            {
                "name": "REDIS_AUTH_TOKEN",
                "valueFrom": "arn:aws:secretsmanager:us-east-1:932100697590:secret:hokusai/redis/development/auth-token"
            }
        ]
    end')

# Save the new MLflow task definition
echo "$NEW_MLFLOW_DEF" > mlflow-task-definition.json

# Register the new MLflow task definition
echo "📝 Registering new MLflow task definition..."
MLFLOW_TASK_ARN=$(aws ecs register-task-definition \
    --cli-input-json file://mlflow-task-definition.json \
    --region $REGION \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

echo "✅ New MLflow task definition registered: $MLFLOW_TASK_ARN"

# Update the MLflow service
echo "🔄 Updating MLflow service with new task definition..."
aws ecs update-service \
    --cluster $CLUSTER \
    --service $MLFLOW_SERVICE \
    --task-definition $MLFLOW_TASK_ARN \
    --force-new-deployment \
    --region $REGION \
    --output json > /dev/null

echo "✅ MLflow service update initiated"

echo ""
echo "🎯 Deployment Status:"
echo "===================="
echo "✅ API service: Updating with Redis configuration"
echo "✅ MLflow service: Updating with Redis configuration"
echo ""
echo "📊 Monitor deployment progress:"
echo "  aws ecs describe-services --cluster $CLUSTER --services $API_SERVICE --region $REGION"
echo "  aws ecs describe-services --cluster $CLUSTER --services $MLFLOW_SERVICE --region $REGION"
echo ""
echo "📋 Check logs:"
echo "  aws logs tail /ecs/hokusai-api-development --follow"
echo "  aws logs tail /ecs/hokusai-mlflow-development --follow"