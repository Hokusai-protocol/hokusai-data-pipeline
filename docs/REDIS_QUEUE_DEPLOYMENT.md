# Redis Queue Integration Deployment Guide

## Overview

This document outlines the deployment configuration required to integrate the hokusai-data-pipeline with the deployed Redis ElastiCache queue.

## Environment Variables Required

The following environment variables must be configured in the ECS task definitions for both `hokusai-api-development` and `hokusai-mlflow-development` services:

### Required Variables

```bash
# Redis ElastiCache Configuration
REDIS_HOST=master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com
REDIS_PORT=6379
```

### Secrets Manager Configuration

The Redis auth token should be retrieved from AWS Secrets Manager:

```bash
# Secret path in AWS Secrets Manager
REDIS_AUTH_TOKEN=<valueFrom:arn:aws:secretsmanager:us-east-1:932100697590:secret:hokusai/redis/development/auth-token-0GWWJx>
```

## ECS Task Definition Updates

### API Service (hokusai-api-development)

Add the following environment variables to the task definition:

```json
{
  "environment": [
    {
      "name": "REDIS_HOST",
      "value": "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com"
    },
    {
      "name": "REDIS_PORT",
      "value": "6379"
    }
  ],
  "secrets": [
    {
      "name": "REDIS_AUTH_TOKEN",
      "valueFrom": "arn:aws:secretsmanager:us-east-1:932100697590:secret:hokusai/redis/development/auth-token-0GWWJx"
    }
  ]
}
```

### Network Configuration

Ensure the ECS services have network connectivity to the Redis ElastiCache cluster:

1. **Security Group Rules**: The ECS task security group must allow outbound connections to port 6379
2. **VPC Configuration**: Services must be in the same VPC as the Redis cluster or have appropriate VPC peering
3. **Subnet Configuration**: Tasks should be deployed in private subnets with NAT gateway access

## Terraform Configuration (hokusai-infrastructure)

If using Terraform for deployment, add the following to the ECS service configuration:

```hcl
# In the API service task definition
environment = [
  {
    name  = "REDIS_HOST"
    value = "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com"
  },
  {
    name  = "REDIS_PORT"
    value = "6379"
  }
]

secrets = [
  {
    name      = "REDIS_AUTH_TOKEN"
    valueFrom = aws_secretsmanager_secret.redis_auth_token.arn
  }
]
```

## Verification Steps

After deployment, verify the Redis integration:

### 1. Health Check Verification

```bash
# Check API health endpoint
curl https://api.hokus.ai/health

# Expected response should include:
{
  "services": {
    "redis": "healthy",
    "message_queue": "healthy"
  }
}
```

### 2. CloudWatch Logs Verification

Check ECS task logs for successful Redis connection:

```bash
aws logs tail /ecs/hokusai-api-development --follow | grep -i redis

# Should see:
# "Using authenticated Redis connection to master.hokusai-redis-development..."
# "Connected to Redis at redis://..."
```

### 3. Message Queue Test

Register a test model and verify message publication:

```python
# Use the test script
python tests/integration/test_redis_queue_integration.py
```

### 4. Redis Queue Monitoring

Monitor queue depth using Redis CLI:

```bash
# Connect to Redis (requires auth token)
redis-cli -h master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com -p 6379 -a $REDIS_AUTH_TOKEN

# Check queue length
LLEN hokusai:model_ready_queue
```

## Rollback Plan

If issues occur after deployment:

1. **Remove Redis environment variables** from ECS task definition
2. **Redeploy services** without Redis configuration
3. **Services will fall back** to local queue implementation

## Security Considerations

1. **Auth Token Management**: Never commit auth tokens to version control
2. **Network Isolation**: Ensure Redis is only accessible from within VPC
3. **Encryption**: ElastiCache encryption at rest and in transit should be enabled
4. **Access Control**: Use IAM roles to control access to Secrets Manager

## Monitoring and Alerts

Configure CloudWatch alarms for:

1. **Queue Depth**: Alert if queue depth exceeds 1000 messages
2. **Connection Failures**: Alert on Redis connection errors
3. **Message Processing Lag**: Alert if messages are not being consumed
4. **Dead Letter Queue**: Alert if messages are moving to DLQ

## Support

For issues or questions:
- Check CloudWatch logs for error messages
- Review Redis connection status in health endpoint
- Verify network connectivity and security groups
- Ensure Secrets Manager permissions are correctly configured