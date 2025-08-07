# 404 Error Troubleshooting Guide

This guide helps diagnose and resolve common 404 "Not Found" errors encountered when using the Hokusai MLOps platform.

## Overview

404 errors can occur at different layers of the Hokusai platform. This guide provides systematic troubleshooting steps to identify and resolve the root cause.

## Common 404 Error Scenarios

### 1. MLflow Model Registration 404 Errors

**Symptoms:**
- Model registration fails with 404 during artifact upload
- Error message: "The requested resource was not found"
- MLflow client returns 404 when logging models

**Root Causes & Solutions:**

#### A. Incorrect MLflow Server URL Configuration

**Problem**: API is routing to external MLflow instead of internal service.

**Check:**
```bash
# Verify MLflow server configuration
curl https://registry.hokus.ai/mlflow/health/mlflow

# Should show internal URL like: http://mlflow.hokusai-development.local:5000
```

**Solution**: Ensure environment variables are set correctly:
```bash
MLFLOW_SERVER_URL=http://mlflow.hokusai-development.local:5000
MLFLOW_TRACKING_URI=http://mlflow.hokusai-development.local:5000
```

#### B. Path Translation Issues

**Problem**: MLflow API paths are not properly translated between internal/external formats.

**Symptoms:**
- External MLflow URLs receive requests with `/api/2.0/` paths
- Internal MLflow URLs receive requests with `/ajax-api/2.0/` paths

**Debug:**
```bash
# Enable proxy debug logging
export MLFLOW_PROXY_DEBUG=true

# Check proxy logs for path translation
aws logs tail /aws/ecs/hokusai-api --follow | grep "path translation"
```

**Solution**: The system automatically handles this, but verify:
- External MLflow (registry.hokus.ai): Uses `ajax-api/2.0` paths
- Internal MLflow (*.local): Uses `api/2.0` paths

#### C. Artifact Storage Not Configured

**Problem**: MLflow artifact serving is disabled or misconfigured.

**Check:**
```bash
# Verify artifact serving status
curl https://registry.hokus.ai/mlflow/health/mlflow/detailed | jq '.tests[] | select(.endpoint == "artifacts_api")'
```

**Solution**: Ensure artifact serving is enabled:
```bash
MLFLOW_SERVE_ARTIFACTS=true
```

### 2. API Endpoint 404 Errors

**Symptoms:**
- API endpoints return 404 when they should exist
- Swagger/OpenAPI docs show different paths than what's accessible

**Root Causes & Solutions:**

#### A. Incorrect API Base Path

**Problem**: Using wrong base URL or missing `/api` prefix.

**Wrong:**
```bash
curl https://registry.hokus.ai/models/  # Missing /api prefix
```

**Correct:**
```bash
curl -H "Authorization: Bearer your_key" \
  https://registry.hokus.ai/api/models/
```

#### B. Missing Authentication

**Problem**: Endpoints require authentication but none provided.

**Check:**
```bash
# This will return 401, not 404
curl https://registry.hokus.ai/api/models/

# This should work
curl -H "Authorization: Bearer hk_live_your_key" \
  https://registry.hokus.ai/api/models/
```

**Solution**: Always include authentication for protected endpoints.

#### C. Route Configuration Issues

**Problem**: FastAPI router configuration is incorrect.

**Debug Steps:**
```bash
# Check available routes
curl https://registry.hokus.ai/openapi.json | jq '.paths | keys'

# Verify specific endpoint exists
curl -I -H "Authorization: Bearer your_key" \
  https://registry.hokus.ai/api/models/
```

### 3. Health Check 404 Errors

**Symptoms:**
- Health check endpoints return 404
- Load balancer health checks fail

**Root Causes & Solutions:**

#### A. Incorrect Health Check Path

**Problem**: Using wrong health check endpoint path.

**Available Health Check Endpoints:**
```bash
# Basic health (no auth required)
GET /health
GET /ready
GET /live
GET /version

# MLflow health checks
GET /mlflow/health/mlflow
GET /api/health/mlflow
GET /api/health/mlflow/detailed
```

#### B. Service Not Running

**Problem**: The API service is not running or has crashed.

**Check:**
```bash
# Verify ECS service is running
aws ecs describe-services \
  --cluster hokusai-development \
  --services hokusai-api

# Check task status
aws ecs list-tasks --cluster hokusai-development \
  --service-name hokusai-api
```

### 4. DSPy Endpoint 404 Errors

**Symptoms:**
- DSPy endpoints return 404
- Pipeline execution fails with "endpoint not found"

**Root Causes & Solutions:**

#### A. Incorrect Endpoint Path

**Problem**: Using wrong DSPy endpoint structure.

**Correct DSPy Endpoints:**
```bash
# Execution endpoints
POST /api/v1/dspy/execute
POST /api/v1/dspy/execute/batch

# Management endpoints
GET /api/v1/dspy/programs
GET /api/v1/dspy/stats
POST /api/v1/dspy/cache/clear

# Health check (no auth)
GET /api/v1/dspy/health
```

#### B. Router Not Included

**Problem**: DSPy router is not properly included in main application.

**Check in main.py:**
```python
app.include_router(dspy.router, tags=["dspy"])
```

## Systematic Troubleshooting Process

### Step 1: Identify the Layer

Determine where the 404 is occurring:

```bash
# Test basic connectivity
curl -I https://registry.hokus.ai/

# Test health endpoint (should work without auth)
curl https://registry.hokus.ai/health

# Test with authentication
curl -H "Authorization: Bearer your_key" \
  https://registry.hokus.ai/api/models/
```

### Step 2: Check Service Status

```bash
# Check ECS service health
aws ecs describe-services --cluster hokusai-development --services hokusai-api

# Check ALB target health
aws elbv2 describe-target-health --target-group-arn arn:aws:elasticloadbalancing:...

# Check CloudWatch logs
aws logs tail /aws/ecs/hokusai-api --follow
```

### Step 3: Verify Configuration

```bash
# Check environment variables in ECS task definition
aws ecs describe-task-definition --task-definition hokusai-api-development

# Verify DNS resolution (from within VPC)
nslookup mlflow.hokusai-development.local
```

### Step 4: Test Path Resolution

```bash
# Enable debug logging
export MLFLOW_PROXY_DEBUG=true

# Test different path formats
curl -v -H "Authorization: Bearer your_key" \
  https://registry.hokus.ai/mlflow/api/2.0/mlflow/experiments/search

# Check logs for path translation messages
aws logs filter-log-events \
  --log-group-name /aws/ecs/hokusai-api \
  --filter-pattern "path translation"
```

## Tools for Debugging 404 Errors

### 1. Health Check Scripts

Create a comprehensive health check script:

```bash
#!/bin/bash
# health_check_404.sh

BASE_URL="https://registry.hokus.ai"
API_KEY="your_api_key_here"

echo "=== Basic Connectivity ==="
curl -I "$BASE_URL/"

echo -e "\n=== Health Endpoints ==="
curl "$BASE_URL/health"
curl "$BASE_URL/ready"
curl "$BASE_URL/live"

echo -e "\n=== API Endpoints ==="
curl -H "Authorization: Bearer $API_KEY" "$BASE_URL/api/models/" | head -5

echo -e "\n=== MLflow Health ==="
curl "$BASE_URL/mlflow/health/mlflow"

echo -e "\n=== DSPy Health ==="
curl "$BASE_URL/api/v1/dspy/health"
```

### 2. Path Validation Script

```python
#!/usr/bin/env python3
# validate_paths.py

import requests
import json

BASE_URL = "https://registry.hokus.ai"
API_KEY = "your_api_key_here"

headers = {"Authorization": f"Bearer {API_KEY}"}

# Test endpoints
endpoints = [
    ("GET", "/health", False),  # No auth
    ("GET", "/api/models/", True),  # Auth required
    ("GET", "/mlflow/health/mlflow", False),  # No auth
    ("GET", "/api/v1/dspy/health", False),  # No auth
]

for method, path, needs_auth in endpoints:
    url = BASE_URL + path
    req_headers = headers if needs_auth else {}
    
    try:
        response = requests.request(method, url, headers=req_headers, timeout=10)
        print(f"{method} {path}: {response.status_code}")
        if response.status_code == 404:
            print(f"  ❌ 404 Error - Path not found")
        elif response.status_code < 400:
            print(f"  ✅ Success")
        else:
            print(f"  ⚠️  HTTP {response.status_code}")
    except Exception as e:
        print(f"{method} {path}: ERROR - {e}")
```

### 3. MLflow Path Tester

```bash
#!/bin/bash
# test_mlflow_paths.sh

BASE_URL="https://registry.hokus.ai"
API_KEY="your_api_key_here"

echo "=== Testing MLflow Paths ==="

# Test different MLflow endpoint variations
paths=(
    "/mlflow/api/2.0/mlflow/experiments/search"
    "/api/mlflow/api/2.0/mlflow/experiments/search"  # Wrong format
    "/mlflow/ajax-api/2.0/mlflow/experiments/search"  # Wrong for internal
)

for path in "${paths[@]}"; do
    echo "Testing: $path"
    curl -s -w "Status: %{http_code}\n" \
         -H "Authorization: Bearer $API_KEY" \
         "$BASE_URL$path" > /dev/null
done
```

## Preventive Measures

### 1. Regular Health Monitoring

Set up CloudWatch alarms for 404 errors:

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "hokusai-api-404-errors" \
  --alarm-description "Alert on 404 errors" \
  --metric-name 4XXError \
  --namespace AWS/ApplicationELB \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold
```

### 2. Automated Testing

Include 404 prevention in CI/CD:

```yaml
# .github/workflows/api-tests.yml
- name: Test API Endpoints
  run: |
    python scripts/validate_paths.py
    bash scripts/health_check_404.sh
```

### 3. Documentation Updates

Keep endpoint documentation synchronized:

1. Update OpenAPI spec when adding endpoints
2. Verify all documented endpoints are actually available
3. Test examples in documentation regularly

## Recovery Procedures

### For Production Issues

1. **Immediate Assessment:**
```bash
# Check service status
aws ecs describe-services --cluster hokusai-development --services hokusai-api

# Verify ALB health
aws elbv2 describe-target-health --target-group-arn your-target-group-arn
```

2. **Quick Fixes:**
```bash
# Force service restart
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-api \
  --force-new-deployment

# Rollback to previous task definition if needed
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-api \
  --task-definition hokusai-api-development:PREVIOUS_REVISION
```

3. **Monitoring:**
```bash
# Watch deployment progress
aws ecs wait services-stable \
  --cluster hokusai-development \
  --services hokusai-api

# Monitor logs for errors
aws logs tail /aws/ecs/hokusai-api --follow
```

## Common Solutions Summary

| Error Pattern | Common Cause | Quick Fix |
|---------------|--------------|-----------|
| MLflow 404 on model upload | Wrong MLFLOW_SERVER_URL | Set to internal URL: `http://mlflow.hokusai-development.local:5000` |
| API endpoint 404 | Missing `/api` prefix | Use `/api/models/` not `/models/` |
| Health check 404 | Wrong path | Use `/health` not `/api/health` |
| Authentication 404 | Actually 401/403 | Check API key authentication |
| DSPy endpoint 404 | Missing version in path | Use `/api/v1/dspy/` not `/api/dspy/` |
| Artifact upload 404 | Artifact serving disabled | Set `MLFLOW_SERVE_ARTIFACTS=true` |

## When to Escalate

Escalate to the development team when:

1. **Multiple endpoints return 404** - Indicates service-level issue
2. **Health checks fail** - Suggests infrastructure problem  
3. **Recently working endpoints now 404** - Potential deployment issue
4. **All troubleshooting steps fail** - May require code-level investigation

Include in your escalation:
- Exact error messages and response codes
- Steps you've already tried
- Logs from CloudWatch showing the issue
- Timeline of when the issue started

## Additional Resources

- [API Endpoint Reference](./API_ENDPOINT_REFERENCE.md) - Complete endpoint documentation
- [Authentication Guide](./AUTHENTICATION_GUIDE.md) - Authentication requirements
- [Deployment Troubleshooting Guide](./deployment-troubleshooting.md) - Infrastructure issues
- [MLflow Proxy Routing Fix](./PROXY_ROUTING_FIX.md) - MLflow-specific issues