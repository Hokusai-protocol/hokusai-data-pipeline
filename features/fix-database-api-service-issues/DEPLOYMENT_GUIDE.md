# Database Fix Deployment Guide

## Overview

This guide covers the deployment of critical database configuration fixes for the Hokusai API service. These fixes address PostgreSQL connection timeouts, health check failures, and service stability issues.

## Changes Implemented

### 1. Database Configuration Fixes
- ✅ Fixed database name mismatch (mlflow → mlflow_db)
- ✅ Added full environment variable support for database configuration
- ✅ Increased connection timeouts from 5 to 10 seconds
- ✅ Made Redis optional since it's not deployed

### 2. MLflow Circuit Breaker Improvements
- ✅ Increased failure threshold from 3 to 5
- ✅ Extended recovery timeout from 30 to 60 seconds
- ✅ Increased max recovery attempts from 3 to 5
- ✅ Added environment variable configuration

### 3. Health Check Enhancements
- ✅ Increased health check timeouts to 10 seconds
- ✅ Made Redis health checks optional
- ✅ Improved graceful degradation logic

## Pre-Deployment Testing

### Local Verification
```bash
# Run the test suite to verify fixes
python test_database_fixes.py

# Expected output:
# ✅ Environment Variables: PASSED
# ✅ Health Check Logic: PASSED  
# ✅ MLflow Configuration: PASSED
# ✅ API Service Import: PASSED
# ⚠️ Database Connection: May fail locally (expected)
```

## Deployment Steps

### 1. Set Environment Variables

Before deploying, ensure these environment variables are configured in ECS:

```bash
# Required - Database Configuration
DATABASE_HOST=hokusai-mlflow-development.cmqduyfpzmbr.us-east-1.rds.amazonaws.com
DATABASE_PORT=5432
DATABASE_USER=postgres
DATABASE_PASSWORD=<secure-password>  # Get from Secrets Manager
DATABASE_NAME=mlflow_db

# Optional - Performance Tuning
MLFLOW_CB_FAILURE_THRESHOLD=5
MLFLOW_CB_RECOVERY_TIMEOUT=60
MLFLOW_CB_MAX_RECOVERY_ATTEMPTS=5
MLFLOW_MAX_RETRIES=3
MLFLOW_BASE_DELAY=2.0

# Optional - Disable Redis if not deployed
REDIS_ENABLED=false
```

### 2. Build and Push Docker Image

```bash
# Build the Docker image
docker build -t hokusai-api:latest .

# Tag for ECR
docker tag hokusai-api:latest <ecr-registry>/hokusai-api:latest

# Push to ECR
docker push <ecr-registry>/hokusai-api:latest
```

### 3. Update ECS Task Definition

Update the task definition with the new image and environment variables:

```json
{
  "family": "hokusai-api",
  "containerDefinitions": [{
    "name": "api",
    "image": "<ecr-registry>/hokusai-api:latest",
    "environment": [
      {"name": "DATABASE_NAME", "value": "mlflow_db"},
      {"name": "DATABASE_HOST", "value": "hokusai-mlflow-development.cmqduyfpzmbr.us-east-1.rds.amazonaws.com"},
      {"name": "REDIS_ENABLED", "value": "false"},
      {"name": "MLFLOW_CB_FAILURE_THRESHOLD", "value": "5"},
      {"name": "MLFLOW_CB_RECOVERY_TIMEOUT", "value": "60"}
    ],
    "secrets": [
      {
        "name": "DATABASE_PASSWORD",
        "valueFrom": "arn:aws:secretsmanager:us-east-1:xxx:secret:hokusai/db-password"
      }
    ]
  }]
}
```

### 4. Deploy to ECS

```bash
# Update the service with new task definition
aws ecs update-service \
  --cluster hokusai-cluster \
  --service hokusai-api \
  --force-new-deployment \
  --task-definition hokusai-api:latest

# Monitor deployment
aws ecs wait services-stable \
  --cluster hokusai-cluster \
  --services hokusai-api
```

## Post-Deployment Verification

### 1. Run Deployment Verification Script

```bash
# Verify the deployment
python verify_deployment.py --url https://registry.hokus.ai --api-key YOUR_API_KEY

# Expected output:
# ✅ Main Health: PASSED
# ✅ Liveness Probe: PASSED
# ✅ Readiness Probe: PASSED
# ✅ Database: PASSED
# ✅ MLflow: PASSED
```

### 2. Check Service Health

```bash
# Check health endpoint directly
curl -X GET https://registry.hokus.ai/health

# Expected response:
{
  "status": "healthy",
  "services": {
    "mlflow": "healthy",
    "postgres": "healthy",
    "redis": "disabled"
  }
}
```

### 3. Monitor CloudWatch Metrics

Check these metrics in CloudWatch:
- ECS Service CPU/Memory utilization
- ALB Target Health
- RDS Connection count
- API Response times

## Troubleshooting

### If Database Connection Still Fails

1. **Verify Security Groups**:
```bash
# Check ECS task security group allows outbound to RDS
aws ec2 describe-security-groups --group-ids sg-xxx

# Check RDS security group allows inbound from ECS
aws ec2 describe-security-groups --group-ids sg-yyy
```

2. **Check Database Credentials**:
```bash
# Verify the password in Secrets Manager
aws secretsmanager get-secret-value --secret-id hokusai/db-password
```

3. **Test Network Connectivity**:
```bash
# SSH into ECS container (if enabled)
# Or use ECS Exec
aws ecs execute-command \
  --cluster hokusai-cluster \
  --task <task-id> \
  --container api \
  --interactive \
  --command "/bin/bash"

# Inside container, test connection
nc -zv hokusai-mlflow-development.cmqduyfpzmbr.us-east-1.rds.amazonaws.com 5432
```

### If Health Checks Still Fail

1. **Check ALB Target Group**:
```bash
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:...
```

2. **Review ECS Task Logs**:
```bash
aws logs tail /ecs/hokusai-api --follow
```

3. **Adjust Health Check Grace Period**:
```bash
# Update service with longer health check grace period
aws ecs update-service \
  --cluster hokusai-cluster \
  --service hokusai-api \
  --health-check-grace-period-seconds 120
```

## Rollback Plan

If issues occur after deployment:

1. **Immediate Rollback**:
```bash
# Revert to previous task definition
aws ecs update-service \
  --cluster hokusai-cluster \
  --service hokusai-api \
  --task-definition hokusai-api:previous-version
```

2. **Restore Previous Configuration**:
- Remove new environment variables
- Revert to previous Docker image
- Reset ALB health check configuration

## Success Criteria

The deployment is successful when:
- ✅ Health endpoint returns "healthy" status consistently
- ✅ No false-positive unhealthy states from ALB
- ✅ PostgreSQL connections succeed with < 1% failure rate
- ✅ MLflow circuit breaker remains CLOSED
- ✅ Service handles requests without 503 errors

## Next Steps

After successful deployment:

1. **Monitor for 24 hours** to ensure stability
2. **Deploy Redis** (optional) for message queue functionality
3. **Update documentation** with new configuration
4. **Create alerts** for database connection failures
5. **Plan infrastructure improvements** (RDS sizing, Multi-AZ)