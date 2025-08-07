# API Migration Guide

This guide helps you migrate from previous versions of the Hokusai API to the current stable version with all recent fixes and improvements.

## Overview

The Hokusai API has undergone significant improvements to fix routing issues, enhance authentication, and improve reliability. This guide covers the changes and provides step-by-step migration instructions.

## What Changed

### 🔧 Major Fixes Applied

#### 1. MLflow Proxy Routing (FIXED)
- **Problem**: Model registration and artifact uploads were failing with 404 errors
- **Root Cause**: External URL routing instead of internal service discovery
- **Solution**: Implemented AWS Cloud Map service discovery with proper path translation

#### 2. Database Authentication (ENHANCED)
- **Problem**: PostgreSQL connection failures during deployments
- **Solution**: Added retry logic, fallback database support, and improved error handling

#### 3. Service Discovery (NEW)
- **Added**: AWS Cloud Map for internal service-to-service communication
- **Benefit**: Reliable internal routing without external dependencies

#### 4. Authentication System (IMPROVED)
- **Added**: External authentication service with API key management
- **Features**: Rate limiting, IP restrictions, scoped access, usage tracking

#### 5. Health Check System (ENHANCED)
- **Added**: Circuit breaker patterns for MLflow connectivity
- **Features**: Detailed diagnostics, automatic recovery, comprehensive monitoring

## Breaking Changes

### ⚠️ Authentication Now Required

**What Changed:**
All API endpoints (except health checks) now require authentication.

**Before (Deprecated):**
```bash
# This no longer works
curl https://registry.hokus.ai/api/models/
```

**After (Required):**
```bash
# Authentication required
curl -H "Authorization: Bearer hk_live_your_api_key_here" \
  https://registry.hokus.ai/api/models/
```

**Migration Steps:**
1. Obtain API key from Hokusai dashboard
2. Update all API calls to include authentication header
3. Set environment variable: `export HOKUSAI_API_KEY="your_key"`

### 🔄 MLflow Endpoint Structure

**What Changed:**
MLflow endpoints now use consistent `/mlflow/*` prefix with improved routing.

**Before:**
```bash
# Old inconsistent paths
GET /api/mlflow/experiments
POST /mlflow/api/2.0/mlflow/runs/create
```

**After:**
```bash
# Consistent structure
GET /mlflow/api/2.0/mlflow/experiments/search
POST /mlflow/api/2.0/mlflow/runs/create
```

**Migration Steps:**
1. Update all MLflow API calls to use `/mlflow/*` prefix
2. Use standard MLflow 2.0 API paths
3. Include authentication in all requests

### 📍 Base URL Standardization

**What Changed:**
All API endpoints now use consistent base URL structure.

**Standard Base URLs:**
- **Production**: `https://registry.hokus.ai`
- **API Endpoints**: `https://registry.hokus.ai/api/*`
- **MLflow Proxy**: `https://registry.hokus.ai/mlflow/*`
- **Health Checks**: `https://registry.hokus.ai/health`

## Migration Checklist

### ✅ For Python SDK Users

**Before:**
```python
# Old SDK usage
import hokusai
registry = hokusai.ModelRegistry(tracking_uri="https://registry.hokus.ai/mlflow")
```

**After:**
```python
# New SDK with authentication
from hokusai import setup, ModelRegistry

# Setup authentication
setup(api_key="hk_live_your_api_key_here")

# Registry automatically uses authenticated connections
registry = ModelRegistry("https://registry.hokus.ai/mlflow")
```

**Migration Steps:**
1. Update to latest SDK version: `pip install -U hokusai-ml-platform`
2. Add authentication setup call
3. Update MLflow URI if hardcoded
4. Test model registration and retrieval

### ✅ For MLflow Direct Users

**Before:**
```python
import mlflow

# Old configuration
mlflow.set_tracking_uri("https://registry.hokus.ai/mlflow")
```

**After:**
```python
import mlflow
import os

# New configuration with authentication
os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/mlflow"
os.environ["MLFLOW_TRACKING_TOKEN"] = "hk_live_your_api_key_here"

# MLflow operations now work reliably
with mlflow.start_run():
    mlflow.log_metric("accuracy", 0.95)
```

**Migration Steps:**
1. Set `MLFLOW_TRACKING_TOKEN` environment variable
2. Update tracking URI format if needed
3. Test model logging and artifact upload
4. Verify model registration works

### ✅ For REST API Users

**Before:**
```bash
# Old API calls without authentication
curl https://registry.hokus.ai/api/models/
curl https://registry.hokus.ai/mlflow/experiments
```

**After:**
```bash
# New API calls with authentication and correct paths
export HOKUSAI_API_KEY="hk_live_your_api_key_here"

curl -H "Authorization: Bearer $HOKUSAI_API_KEY" \
  https://registry.hokus.ai/api/models/

curl -H "Authorization: Bearer $HOKUSAI_API_KEY" \
  https://registry.hokus.ai/mlflow/api/2.0/mlflow/experiments/search
```

**Migration Steps:**
1. Obtain API key from Hokusai platform
2. Add authentication headers to all requests
3. Update endpoint URLs to use correct structure
4. Update error handling for new response codes

### ✅ For Infrastructure/DevOps

**Health Check Updates:**
```yaml
# Docker Compose / Kubernetes health checks
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
  interval: 30s
  timeout: 10s
  retries: 3
```

**Environment Variable Updates:**
```bash
# New required environment variables
HOKUSAI_API_KEY=hk_live_your_key_here
MLFLOW_SERVER_URL=http://mlflow.hokusai-development.local:5000
MLFLOW_TRACKING_URI=http://mlflow.hokusai-development.local:5000
```

## Detailed Migration Steps

### Step 1: Update Authentication

#### For SDK Users:
```python
# Install latest SDK
pip install -U git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform

# Update code
from hokusai import setup
setup(api_key="hk_live_your_api_key_here")
```

#### For Direct API Users:
```bash
# Get API key from Hokusai dashboard
export HOKUSAI_API_KEY="hk_live_your_api_key_here"

# Test authentication
curl -H "Authorization: Bearer $HOKUSAI_API_KEY" \
  https://registry.hokus.ai/health
```

### Step 2: Update Endpoint URLs

**Model Management:**
```bash
# Before
GET /models/list

# After  
GET /api/models/
```

**MLflow Operations:**
```bash
# Before
POST /api/mlflow/runs

# After
POST /mlflow/api/2.0/mlflow/runs/create
```

**Health Checks:**
```bash
# Before
GET /api/health

# After (no change, but no auth required)
GET /health
```

### Step 3: Update Error Handling

**New Error Response Format:**
```json
{
  "detail": "Error message",
  "error_code": "RESOURCE_NOT_FOUND",
  "timestamp": "2025-01-07T10:30:00Z"
}
```

**Update Error Handling Code:**
```python
# Before
try:
    response = requests.get(url)
    if response.status_code == 404:
        print("Not found")
except:
    print("Error occurred")

# After
try:
    response = requests.get(url, headers={"Authorization": f"Bearer {api_key}"})
    if response.status_code == 401:
        print("Authentication required")
    elif response.status_code == 404:
        print("Resource not found")
    elif response.status_code == 429:
        print("Rate limit exceeded")
except requests.RequestException as e:
    print(f"Request failed: {e}")
```

### Step 4: Test Migration

**Validation Script:**
```python
#!/usr/bin/env python3
"""Migration validation script"""

import os
import requests
from hokusai import setup, ModelRegistry

def test_sdk_migration():
    """Test SDK migration"""
    try:
        setup(api_key=os.getenv("HOKUSAI_API_KEY"))
        registry = ModelRegistry()
        models = registry.list_models()
        print("✅ SDK migration successful")
        return True
    except Exception as e:
        print(f"❌ SDK migration failed: {e}")
        return False

def test_api_migration():
    """Test direct API migration"""
    try:
        headers = {"Authorization": f"Bearer {os.getenv('HOKUSAI_API_KEY')}"}
        response = requests.get("https://registry.hokus.ai/api/models/", headers=headers)
        if response.status_code == 200:
            print("✅ API migration successful")
            return True
        else:
            print(f"❌ API migration failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ API migration failed: {e}")
        return False

def test_mlflow_migration():
    """Test MLflow migration"""
    try:
        import mlflow
        os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/mlflow"
        os.environ["MLFLOW_TRACKING_TOKEN"] = os.getenv("HOKUSAI_API_KEY")
        
        client = mlflow.tracking.MlflowClient()
        experiments = client.search_experiments()
        print("✅ MLflow migration successful")
        return True
    except Exception as e:
        print(f"❌ MLflow migration failed: {e}")
        return False

if __name__ == "__main__":
    if not os.getenv("HOKUSAI_API_KEY"):
        print("❌ HOKUSAI_API_KEY environment variable required")
        exit(1)
    
    sdk_ok = test_sdk_migration()
    api_ok = test_api_migration()  
    mlflow_ok = test_mlflow_migration()
    
    if all([sdk_ok, api_ok, mlflow_ok]):
        print("\n🎉 All migrations successful!")
    else:
        print("\n⚠️ Some migrations need attention")
        exit(1)
```

## Feature Additions

### 🆕 New Endpoints Added

#### DSPy Pipeline Execution
```bash
# Execute DSPy programs
POST /api/v1/dspy/execute
POST /api/v1/dspy/execute/batch
GET /api/v1/dspy/programs
```

#### Enhanced Health Checks
```bash
# Detailed health diagnostics
GET /health?detailed=true
GET /mlflow/health/mlflow/detailed
GET /api/health/mlflow/connectivity
```

#### Model Analytics
```bash
# Contributor impact analysis
GET /api/models/contributors/{address}/impact
```

### 🔧 Enhanced Features

#### Circuit Breaker for MLflow
- Automatic failure detection and recovery
- Graceful degradation during outages
- Manual reset capability

#### Rate Limiting
- Per-API-key rate limits
- Different limits for different endpoint categories
- Rate limit headers in responses

#### Request Tracing
- Request IDs for debugging
- Comprehensive logging
- User context tracking

## Rollback Plan

If you need to rollback due to migration issues:

### 1. Temporary Workarounds

**For Authentication Issues:**
```bash
# If new auth fails, contact support immediately
# No self-service rollback available for authentication
```

**For SDK Issues:**
```bash
# Pin to previous SDK version temporarily
pip install hokusai-ml-platform==previous_version
```

### 2. Emergency Contacts

If migration fails:
1. Check the troubleshooting guides first
2. Contact support with:
   - Exact error messages
   - Steps you've tried
   - Your API key ID (not the key itself)
   - Request IDs if available

## Timeline and Support

### Migration Timeline
- **Immediate**: New authentication system is active
- **90 days**: Legacy endpoint support (if any) will be deprecated
- **Ongoing**: Continuous improvements and monitoring

### Support During Migration
- **Documentation**: Complete guides available in `/docs`
- **Health Monitoring**: 24/7 monitoring of all endpoints
- **Quick Response**: Support team alerted to migration issues

## Common Migration Issues

### Issue 1: "API key required" Error
**Cause**: Missing or incorrect authentication
**Solution**: Verify API key format and include in requests
```bash
# Check key format
echo $HOKUSAI_API_KEY | grep -E '^hk_(live|test|dev)_[a-z0-9]{32}$'
```

### Issue 2: MLflow Connection Errors
**Cause**: Cached configuration or wrong URI
**Solution**: Clear MLflow cache and update configuration
```python
import mlflow
mlflow.tracking.set_tracking_uri("https://registry.hokus.ai/mlflow")
```

### Issue 3: 404 Errors on Previously Working Endpoints
**Cause**: Endpoint path changes
**Solution**: Check [404 Troubleshooting Guide](./404_TROUBLESHOOTING_GUIDE.md)

### Issue 4: Rate Limit Exceeded
**Cause**: New rate limiting system
**Solution**: Implement exponential backoff or request limit increase

## Success Metrics

After migration, you should see:
- ✅ Model registration working without 404 errors
- ✅ MLflow artifact uploads completing successfully
- ✅ Faster response times due to internal routing
- ✅ Better error messages and debugging information
- ✅ Monitoring and alerting working properly

## Next Steps

After successful migration:

1. **Monitor Usage**: Check your API key usage dashboard
2. **Optimize Rate Limits**: Adjust limits based on actual usage
3. **Implement Best Practices**: Follow [Authentication Guide](./AUTHENTICATION_GUIDE.md)
4. **Stay Updated**: Subscribe to updates for future improvements
5. **Provide Feedback**: Report any issues or suggestions

## Additional Resources

- [API Endpoint Reference](./API_ENDPOINT_REFERENCE.md) - Complete endpoint documentation
- [Authentication Guide](./AUTHENTICATION_GUIDE.md) - Authentication setup and best practices  
- [404 Troubleshooting Guide](./404_TROUBLESHOOTING_GUIDE.md) - Common error resolution
- [Deployment Troubleshooting](./deployment-troubleshooting.md) - Infrastructure issues
- [MLflow Proxy Fix](./PROXY_ROUTING_FIX.md) - Technical details of MLflow fixes