# Infrastructure Issues Summary - Hokusai Data Pipeline

## Executive Summary
While the critical syntax error preventing API service startup has been fixed and deployed, significant infrastructure issues remain that prevent full endpoint accessibility. The API service is now running stable in ECS, but routing and health check configurations need attention.

## Current Status

### ✅ What's Fixed
- **API Service Startup**: Fixed syntax error in `src/services/model_registry.py` that was causing service crashes
- **ECS Deployment**: Service is running stable (hokusai-api-development:115 with hotfix image)
- **Partial Connectivity**: Some endpoints now return 404 instead of timing out

### ❌ What's Still Broken

#### 1. Registry Endpoints (registry.hokus.ai)
**Status**: Complete timeout on all paths
- `/health` - Timeout (5s)
- `/api/mlflow` - Timeout (5s)
- `/api/mlflow/health` - Timeout (5s)
- `/api/mlflow/version` - Timeout (5s)
- `/api/2.0/mlflow/registered-models/list` - Timeout (5s)

**Impact**: MLflow registry completely inaccessible

#### 2. MLflow Direct Access (mlflow.hokus.ai)
**Status**: Connection timeout/error
**Impact**: Cannot access MLflow UI directly

#### 3. API Endpoints (api.hokus.ai)
**Status**: Returns 404 for all paths (but at least responding)
- `/health` - 404 Not Found
- `/api/v1/health` - 504 Gateway Timeout
- Root path `/` - 404 Not Found

**Impact**: API accessible but no valid routes configured

#### 4. Platform Endpoint (platform.hokus.ai)
**Status**: Returns 404 (improved from timeout)
**Impact**: Platform UI not accessible

## Infrastructure Components Requiring Review

### 1. Application Load Balancers (ALBs)
```
hokusai-main-development (api.hokus.ai)
- Listeners: Port 443 returns fixed-response, Port 80 redirects
- No routing rules to backend services

hokusai-registry-development (registry.hokus.ai)
- All requests timing out
- Likely missing healthy targets or routing rules
```

### 2. Target Groups
```
hokusai-reg-api-development
- Health check path: /health/alb
- Status: Targets showing as unhealthy
- IP 10.0.1.76 marked unhealthy despite service running

hokusai-api-tg-development
- Similar health check failures
```

### 3. ECS Service Health Checks
```
Service: hokusai-api-development
- Task running successfully (no crashes)
- Application logs show "Started server process"
- But failing ALB health checks
- Health check endpoint mismatch (/health/alb vs actual endpoints)
```

### 4. Internal Connectivity Issues
```
MLflow Connection:
- API service cannot reach MLflow at 10.0.3.219:5000
- Continuous timeout errors in logs
- May be security group or network ACL issue
```

## Logs Evidence

### Service Running Successfully
```
2025-08-20T13:44:17.848000+00:00 INFO: Started server process [1]
```

### But MLflow Connectivity Failing
```
WARNING: Connection to 10.0.3.219 timed out. (connect timeout=120)
/api/2.0/mlflow/experiments/get-by-name?experiment_name=default
```

## Recommended Actions for Infrastructure Team

### Immediate (P0)
1. **Fix ALB Routing Rules**
   - Configure proper listener rules for api.hokus.ai
   - Add path-based routing to correct target groups
   - Fix registry.hokus.ai ALB configuration

2. **Update Health Check Paths**
   - Align target group health checks with actual application endpoints
   - Current: `/health/alb`
   - Consider: `/health` or `/api/health`

3. **Verify Target Group Registration**
   - Ensure ECS tasks are properly registered to target groups
   - Check why healthy tasks show as unhealthy in target groups

### Short-term (P1)
4. **Fix Internal Networking**
   - Resolve MLflow connectivity (10.0.3.219:5000 timeout)
   - Check security groups between services
   - Verify service discovery configuration

5. **DNS/Certificate Validation**
   - Verify mlflow.hokus.ai DNS exists and points to correct resource
   - Check SSL certificate coverage for all domains

### Configuration Review Needed
6. **Service Discovery**
   - MLflow service should be accessible at mlflow.hokusai-development.local
   - Currently hardcoded to IP addresses indicating discovery issues

7. **Environment Variables**
   - MLFLOW_TRACKING_URI points to non-accessible address
   - May need update to use service discovery or correct IP

## Test Commands for Verification

```bash
# Check endpoint accessibility
for url in registry.hokus.ai api.hokus.ai mlflow.hokus.ai platform.hokus.ai; do
  echo "Testing https://$url"
  curl -I --max-time 5 https://$url
done

# Check ECS service health
aws ecs describe-services --cluster hokusai-development \
  --services hokusai-api-development hokusai-mlflow-development \
  --query 'services[*].[serviceName,runningCount,desiredCount]'

# Check target group health
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-reg-api-development/aab4ed4b619b04c0
```

## Summary
The application code issue has been resolved, and the API service is running stable. However, the infrastructure layer (ALBs, routing, health checks, and internal networking) requires configuration updates to restore full endpoint accessibility. The registry.hokus.ai timeout issues are particularly critical as they block all MLflow operations.

---
*Report Generated: 2025-08-20*
*Issue: Linear Bug - "Endpoints inaccessible"*
*Fixed: Application startup (syntax error)*
*Remaining: Infrastructure routing and configuration*