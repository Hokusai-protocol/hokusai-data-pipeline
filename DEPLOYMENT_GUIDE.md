# Hokusai API Proxy - Deployment Guide

## Overview

The Hokusai API proxy with Bearer token authentication is **already implemented** in the codebase. This guide explains how to verify the deployment and ensure it's working correctly.

## Pre-Deployment Checklist

### 1. Verify Code is Deployed

The following components must be deployed:
- `src/middleware/auth.py` - Authentication middleware
- `src/api/routes/mlflow_proxy.py` - MLflow proxy router
- `src/api/main.py` - Main FastAPI application

### 2. Environment Variables

Ensure these are set in the deployment environment:

```bash
# MLflow server configuration
MLFLOW_SERVER_URL=http://mlflow-server:5000

# Authentication service
HOKUSAI_AUTH_SERVICE_URL=https://auth.hokus.ai

# Redis cache (optional but recommended)
REDIS_URL=redis://redis:6379/0
```

### 3. Infrastructure Requirements

Verify AWS ALB routing rules:
- `/api/*` → API target group (port 8001)
- API service must be healthy in the target group

## Deployment Steps

### 1. Deploy the API Service

```bash
# If using Docker
docker compose up -d api

# If using ECS/Kubernetes
# Deploy the API service with the latest image
```

### 2. Verify Health Checks

```bash
# Check API service health
curl https://registry.hokus.ai/health

# Check MLflow proxy health
curl https://registry.hokus.ai/api/mlflow/health/mlflow
```

### 3. Test Bearer Token Authentication

```bash
# Test with a valid API key
curl -H "Authorization: Bearer YOUR_API_KEY" \
     https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search
```

Expected response: 200 OK with experiment list

### 4. Test MLflow Client Integration

```python
import mlflow
import os

# Configure MLflow client
os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/api/mlflow"
os.environ["MLFLOW_TRACKING_TOKEN"] = "YOUR_API_KEY"

# Test connection
client = mlflow.tracking.MlflowClient()
experiments = client.search_experiments()
print(f"Success! Found {len(experiments)} experiments")
```

## Verification Script

Run the verification script to ensure everything is working:

```bash
# Set your API key
export HOKUSAI_API_KEY=hk_live_your_key_here

# Run verification
python verify_api_proxy.py
```

## Monitoring

### 1. CloudWatch Logs

Monitor these log streams:
- `/aws/ecs/api-service` - API service logs
- Look for authentication success/failure messages

### 2. Metrics to Watch

- API response time (should be < 500ms)
- Authentication cache hit rate (should be > 80%)
- MLflow proxy success rate (should be > 99%)

## Troubleshooting

### Issue: 404 Not Found on /api/mlflow

**Cause**: API service not deployed or not routing correctly

**Solution**:
1. Check ALB target group health
2. Verify API service is running
3. Check ALB routing rules

### Issue: 401 Unauthorized

**Cause**: Invalid API key or auth service unavailable

**Solution**:
1. Verify API key is valid
2. Check auth service connectivity
3. Check Redis cache connectivity

### Issue: 502 Bad Gateway

**Cause**: MLflow backend not accessible

**Solution**:
1. Check MLFLOW_SERVER_URL configuration
2. Verify MLflow service is running
3. Check network connectivity between services

### Issue: 403 from MLflow

**Cause**: MLflow received authentication headers (shouldn't happen)

**Solution**:
1. Verify proxy is stripping auth headers
2. Check middleware ordering in main.py
3. Review proxy code for header stripping

## Rollback Plan

If issues arise:

1. **Immediate**: Direct users to use direct MLflow access
2. **Short-term**: Roll back to previous API version
3. **Investigation**: Check logs and metrics to identify issue

## Success Criteria

The deployment is successful when:

1. ✅ Health checks pass
2. ✅ Bearer token authentication works
3. ✅ MLflow client can connect and list experiments
4. ✅ No increase in error rates
5. ✅ Response times remain stable

## Communication

Once deployed:

1. Update status page
2. Notify users via email/Slack
3. Update documentation with confirmed endpoint
4. Monitor for 24 hours for issues

## Long-term Improvements

After successful deployment:

1. Add automated deployment tests
2. Implement canary deployments
3. Add more detailed metrics
4. Create runbooks for common issues