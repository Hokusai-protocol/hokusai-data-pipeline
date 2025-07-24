# MLflow Proxy Routing Fix Documentation

## Overview

This document describes the implementation of fixes for MLflow proxy routing issues that were preventing model registration. The primary issue was that the API proxy was routing artifact requests to external URLs instead of the internal MLflow service, causing 404 errors.

## Problem Summary

1. **External URL Routing**: The MLFLOW_SERVER_URL was set to `https://registry.hokus.ai/mlflow`, causing the proxy to route requests externally
2. **Missing Service Discovery**: No internal service discovery was configured for service-to-service communication
3. **Artifact Endpoint Failures**: Model artifact uploads failed with 404 errors because requests were not reaching the MLflow service

## Solution Implementation

### 1. Service Discovery Configuration

Added AWS Cloud Map service discovery to enable internal DNS resolution:

```hcl
# infrastructure/terraform/service-discovery.tf
resource "aws_service_discovery_private_dns_namespace" "internal" {
  name = "${var.project_name}-${var.environment}.local"
  vpc  = module.vpc.vpc_id
}

resource "aws_service_discovery_service" "mlflow" {
  name = "mlflow"
  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.internal.id
    dns_records {
      ttl  = 10
      type = "A"
    }
  }
}
```

This creates an internal DNS name: `mlflow.hokusai-development.local`

### 2. Environment Variable Updates

Updated the API service to use internal MLflow URL:

```hcl
# infrastructure/terraform/api-env-updates.tf
environment = [
  {
    name  = "MLFLOW_SERVER_URL"
    value = "http://mlflow.${var.project_name}-${var.environment}.local:5000"
  },
  {
    name  = "MLFLOW_TRACKING_URI"
    value = "http://mlflow.${var.project_name}-${var.environment}.local:5000"
  }
]
```

### 3. Improved Proxy Implementation

Created `mlflow_proxy_improved.py` with:

- **Better path translation** - Handles internal vs external MLflow differences
- **Enhanced logging** - Detailed request/response logging for debugging
- **Robust error handling** - Clear error messages for troubleshooting
- **Health check endpoints** - Comprehensive health monitoring

Key improvements:
```python
# Intelligent path translation
if path.startswith("api/2.0/mlflow/"):
    if "registry.hokus.ai" in mlflow_base_url:
        # External MLflow uses ajax-api
        path = path.replace("api/2.0/mlflow/", "ajax-api/2.0/mlflow/")
    else:
        # Internal MLflow uses standard api path
        logger.info(f"Using standard API path for internal MLflow: {path}")

# Detailed logging
logger.info(f"Proxying request: {request.method} {original_path} -> {target_url}")
```

### 4. Health Check Endpoints

Added comprehensive health checks:

- `/mlflow/health/mlflow` - Basic health status with individual API checks
- `/mlflow/health/mlflow/detailed` - Detailed diagnostics including response times

## Deployment Process

1. **Apply Terraform Changes**
   ```bash
   cd infrastructure/terraform
   terraform plan -var="environment=development"
   terraform apply
   ```

2. **Deploy Updated API Container**
   ```bash
   # Build and push to ECR
   docker build -t hokusai-api:latest .
   docker tag hokusai-api:latest $ECR_REPO:proxy-routing-fix
   docker push $ECR_REPO:proxy-routing-fix
   ```

3. **Update ECS Service**
   ```bash
   # Use the deployment script
   ./scripts/deploy_proxy_routing_fix.sh
   ```

## Testing

### Verify Routing
```bash
# Check health endpoints
curl https://registry.hokus.ai/mlflow/health/mlflow
curl https://registry.hokus.ai/mlflow/health/mlflow/detailed

# Test model registration
export HOKUSAI_API_KEY="your-api-key"
python test_real_registration.py
```

### Expected Results
- All MLflow API endpoints should return 200 status codes
- Model registration should complete without 404 errors
- Artifacts should upload successfully

## Troubleshooting

### Enable Debug Logging
Set the environment variable:
```bash
MLFLOW_PROXY_DEBUG=true
```

### Check Service Discovery
```bash
# Verify DNS resolution from within VPC
nslookup mlflow.hokusai-development.local
```

### Monitor Logs
```bash
# View API logs
aws logs tail /aws/ecs/hokusai-api --follow

# View MLflow logs  
aws logs tail /aws/ecs/hokusai-mlflow --follow
```

### Common Issues

1. **Connection Refused**
   - Check that MLflow service is running
   - Verify security group allows traffic on port 5000
   - Ensure service discovery is registered

2. **404 Errors Continue**
   - Verify MLFLOW_SERVER_URL is using internal DNS
   - Check that artifact serving is enabled in MLflow
   - Confirm path translation is working correctly

3. **Authentication Errors**
   - Ensure auth headers are being stripped before proxying
   - Verify API key validation is working

## Rollback Procedure

If issues arise, rollback to previous configuration:

1. **Revert Task Definition**
   ```bash
   aws ecs update-service \
     --cluster hokusai-development \
     --service hokusai-api \
     --task-definition <previous-task-def-arn>
   ```

2. **Restore Environment Variables**
   - Set MLFLOW_SERVER_URL back to external URL if needed

3. **Monitor Service Stability**
   - Wait for ECS service to stabilize
   - Verify health checks pass

## Benefits

1. **Proper Internal Routing** - Services communicate directly within VPC
2. **Better Performance** - No external round trips for internal calls
3. **Enhanced Security** - Traffic stays within private network
4. **Improved Debugging** - Comprehensive logging and health checks
5. **Future-Proof** - Service discovery enables easy scaling

## Next Steps

1. Monitor the deployment for 24 hours
2. Run comprehensive integration tests
3. Update documentation for users
4. Consider implementing request retry logic
5. Add CloudWatch alarms for proxy errors