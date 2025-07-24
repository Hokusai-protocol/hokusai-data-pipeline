# Deployment Health Check Troubleshooting Guide

## Overview

This guide helps diagnose and resolve health check failures during ECS deployments.

## Common Health Check Issues

### 1. Task Failed Container Health Checks

**Symptoms:**
- ECS tasks show "Task failed container health checks" as stop reason
- Deployments stuck in IN_PROGRESS state
- Mixed running/desired task counts

**Common Causes:**
- Service not ready when health checks begin
- Health check endpoint returns incorrect status
- Insufficient start period for service initialization
- Database or external service connectivity issues

**Resolution Steps:**

1. **Check CloudWatch Logs:**
```bash
# View recent API logs
aws logs tail /aws/ecs/hokusai-api-development --follow

# View recent MLflow logs  
aws logs tail /aws/ecs/hokusai-mlflow-development --follow
```

2. **Verify Health Check Endpoints Locally:**
```bash
# Test API health
curl http://localhost:8001/health

# Test MLflow health
curl http://localhost:5000/mlflow
```

3. **Check Task Stop Reasons:**
```bash
# List stopped tasks
aws ecs list-tasks --cluster hokusai-development \
  --service-name hokusai-api --desired-status STOPPED

# Get stop reason
aws ecs describe-tasks --cluster hokusai-development \
  --tasks <task-arn>
```

### 2. Database Connection Timeouts

**Symptoms:**
- Health checks fail with PostgreSQL connection errors
- "connect_timeout" errors in logs

**Resolution:**
- Verify RDS security group allows connections from ECS tasks
- Check database credentials in environment variables
- Ensure RDS instance is running and accessible

### 3. MLflow Service Not Ready

**Symptoms:**
- MLflow health check returns 404
- "Connection refused" errors

**Resolution:**
- Verify MLflow is configured with correct static prefix
- Check MLflow startup logs for errors
- Ensure artifact storage (S3) is accessible

## Health Check Configuration

### Current Settings

**Container Health Checks:**
- Start Period: 90 seconds
- Interval: 30 seconds  
- Timeout: 10 seconds
- Retries: 3

**ALB Health Checks:**
- Interval: 30 seconds
- Timeout: 10 seconds
- Healthy Threshold: 2
- Unhealthy Threshold: 3

### Testing Health Checks Locally

1. **Using Docker Compose:**
```bash
# Start services with health check monitoring
docker-compose -f docker-compose.health-test.yml up

# In another terminal, run health check tests
python scripts/test_health_checks.py
```

2. **Manual Testing:**
```bash
# Test API endpoints
curl -v http://localhost:8001/health
curl -v http://localhost:8001/ready
curl -v http://localhost:8001/live

# Test with detailed output
curl http://localhost:8001/health?detailed=true | jq
```

## Monitoring Health Checks

### CloudWatch Metrics

Key metrics to monitor:
- `HealthCheckStatus` - ALB health check results
- `TargetResponseTime` - Response time for health checks
- `UnHealthyHostCount` - Number of unhealthy targets

### Creating Alarms

```bash
# Alarm for unhealthy targets
aws cloudwatch put-metric-alarm \
  --alarm-name "hokusai-api-unhealthy-targets" \
  --alarm-description "Alert when API has unhealthy targets" \
  --metric-name UnHealthyHostCount \
  --namespace AWS/ApplicationELB \
  --statistic Average \
  --period 300 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2
```

## Deployment Best Practices

1. **Pre-deployment Checks:**
   - Test health endpoints locally
   - Verify all dependencies are accessible
   - Check container has sufficient resources

2. **During Deployment:**
   - Monitor CloudWatch logs in real-time
   - Watch ECS service events
   - Track health check metrics

3. **Post-deployment:**
   - Verify all endpoints respond correctly
   - Check for any error patterns in logs
   - Monitor performance metrics

## Emergency Procedures

### Quick Rollback

```bash
# Rollback to previous task definition
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-api \
  --task-definition hokusai-api-development:31
```

### Force Service Update

```bash
# Force new deployment
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-api \
  --force-new-deployment
```

### Stop Unhealthy Tasks

```bash
# Stop specific task
aws ecs stop-task \
  --cluster hokusai-development \
  --task <task-arn>
```

## Health Check Endpoint Specifications

### GET /health
- **Purpose:** Overall service health
- **Expected Response:** 200 OK
- **Response Body:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "services": {
    "mlflow": "healthy",
    "redis": "healthy", 
    "postgres": "healthy"
  },
  "timestamp": "2024-01-20T10:30:00Z"
}
```

### GET /ready
- **Purpose:** Service readiness for traffic
- **Expected Response:** 200 OK (ready) or 503 Service Unavailable (not ready)

### GET /live
- **Purpose:** Service liveness check
- **Expected Response:** 200 OK

## Debugging Commands

```bash
# Check ECS service status
aws ecs describe-services \
  --cluster hokusai-development \
  --services hokusai-api

# View task definition
aws ecs describe-task-definition \
  --task-definition hokusai-api-development

# Check target health
aws elbv2 describe-target-health \
  --target-group-arn <target-group-arn>

# View deployment configuration
aws ecs describe-services \
  --cluster hokusai-development \
  --services hokusai-api \
  --query 'services[0].deploymentConfiguration'
```