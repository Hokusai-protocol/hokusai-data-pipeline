# API Connectivity Fix Summary

## Problem Statement
The Hokusai data pipeline API is experiencing connectivity issues preventing model registration:
- 502 Bad Gateway errors when API tries to reach MLflow internally
- 404 errors on MLflow proxy endpoints
- Authentication failures with valid API keys
- Service-to-service communication failures

## Root Causes Identified
1. **Missing Service Discovery**: ECS services lack service discovery registration
2. **Incorrect Service URLs**: API hardcoded to use IP addresses instead of DNS names
3. **Authentication Service ID Mismatch**: Using "ml-platform" instead of "platform"
4. **ALB Routing Configuration**: Routes correctly configured but services can't communicate internally

## Fixes Implemented

### 1. Service Discovery Configuration ✅
**File**: `infrastructure/terraform/service-discovery.tf`
- Created private DNS namespace: `hokusai-development.local`
- Registered MLflow service for DNS resolution
- Registered API service for DNS resolution
- Services now accessible via internal DNS names

### 2. ECS Service Updates ✅
**File**: `infrastructure/terraform/ecs-service-discovery-patch.tf`
- Added service_registries blocks to ECS services
- MLflow accessible at: `mlflow.hokusai-development.local:5000`
- API accessible at: `api.hokusai-development.local:8001`

### 3. API Configuration Updates ✅
**File**: `src/api/utils/config.py`
- Updated MLflow tracking URI to use service discovery DNS
- Changed from hardcoded IP to: `http://mlflow.hokusai-development.local:5000`

### 4. Environment Variables ✅
**File**: `infrastructure/terraform/api-env-config.tf`
- Added MLFLOW_SERVER_URL environment variable
- Configured proper service discovery DNS names
- Enabled debug logging for troubleshooting

### 5. Authentication Middleware Fix ✅
**File**: `src/middleware/auth_fixed.py`
- Fixed service_id from "ml-platform" to "platform"
- Correctly sends API key in Authorization header
- Proper error handling for auth service responses

### 6. ALB Routing Rules ✅
**File**: `infrastructure/terraform/dedicated-albs.tf`
- `/api/mlflow/*` correctly routes to API service (line 273-290)
- API service then proxies to MLflow internally
- Separate target groups for API and MLflow services

## Deployment Instructions

### Step 1: Apply Infrastructure Changes
```bash
cd infrastructure/terraform

# Initialize terraform
terraform init

# Plan changes
terraform plan -out=tfplan

# Review the planned changes, especially:
# - Service discovery namespace creation
# - ECS service updates with service_registries
# - Security group rules

# Apply changes
terraform apply tfplan
```

### Step 2: Update ECS Task Definitions
```bash
# Update API task definition with new environment variables
aws ecs register-task-definition --cli-input-json file://api-task-def.json

# Update MLflow task definition if needed
aws ecs register-task-definition --cli-input-json file://mlflow-task-def.json
```

### Step 3: Deploy Updated Services
```bash
# Force new deployment of API service with updated config
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-api \
  --force-new-deployment

# Force new deployment of MLflow service
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-mlflow \
  --force-new-deployment

# Wait for services to stabilize
aws ecs wait services-stable \
  --cluster hokusai-development \
  --services hokusai-api hokusai-mlflow
```

### Step 4: Verify Service Discovery
```bash
# Check service discovery registrations
aws servicediscovery list-services \
  --filters Name=NAMESPACE_ID,Values=<namespace-id>

# Verify DNS resolution (from within VPC)
nslookup mlflow.hokusai-development.local
nslookup api.hokusai-development.local
```

### Step 5: Test Connectivity
```bash
# Set the platform API key
export HOKUSAI_API_KEY="hk_live_NVWOYDfNfTJyFzUDkQDBk2LLA4pB5qza"

# Run the connectivity test script
python test_api_connectivity_fixes.py

# Or test individual endpoints
curl -H "Authorization: Bearer $HOKUSAI_API_KEY" \
  https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search
```

## Validation Checklist

- [ ] Service discovery namespace created
- [ ] ECS services registered with service discovery
- [ ] API can resolve mlflow.hokusai-development.local
- [ ] MLflow health checks passing
- [ ] API health checks passing
- [ ] Authentication with platform API key succeeds
- [ ] MLflow experiments API returns 200
- [ ] Model registration API returns 200/201
- [ ] No more 502 Bad Gateway errors
- [ ] No more 404 Not Found on proxy endpoints

## Monitoring

### CloudWatch Metrics to Monitor
- ECS service health: `HealthyHostCount`
- ALB target health: `TargetResponseTime`
- Error rates: `HTTPCode_Target_5XX_Count`
- Service discovery: `DiscoveryInstanceHealth`

### Log Groups to Check
- `/aws/ecs/hokusai-api`
- `/aws/ecs/hokusai-mlflow`
- `/aws/ecs/hokusai-auth`

### Alarms to Set
```bash
# Create alarm for 502 errors
aws cloudwatch put-metric-alarm \
  --alarm-name "hokusai-api-502-errors" \
  --alarm-description "Alert on high 502 error rate" \
  --metric-name HTTPCode_Target_5XX_Count \
  --namespace AWS/ApplicationELB \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2
```

## Rollback Plan

If issues arise after deployment:

1. **Revert ECS Services**:
```bash
# Roll back to previous task definition
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-api \
  --task-definition hokusai-api:previous-revision
```

2. **Remove Service Discovery** (if needed):
```bash
terraform destroy -target=aws_service_discovery_service.mlflow
terraform destroy -target=aws_service_discovery_service.api
```

3. **Restore Previous Configuration**:
- Revert `src/api/utils/config.py` to use previous MLflow URL
- Revert `src/middleware/auth_fixed.py` if auth issues persist

## Success Metrics

After successful deployment:
- ✅ Infrastructure health score: >90% (from 54.5%)
- ✅ Model registration success rate: 100%
- ✅ API response time: <500ms for proxy requests
- ✅ Zero 502 errors in 24-hour period
- ✅ Successful third-party integrations

## Contact

For issues or questions:
- Infrastructure Team: For terraform and AWS changes
- Data Pipeline Team: For API and MLflow configuration
- Auth Team: For authentication service issues