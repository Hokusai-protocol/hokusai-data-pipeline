# Model Registration Test Report

**Date**: 2025-08-05  
**Tester**: Hokusai Data Pipeline Team  
**API Key Used**: hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL (existing key - may be invalid post-migration)
**Admin Token**: 88IngITCxCtEszifFTh24gPG9hv2owe9 (provided but auth service unavailable)

## Executive Summary

Model registration testing was conducted following the infrastructure migration to a centralized repository. The testing revealed significant infrastructure issues that prevent model registration functionality. The auth service itself is experiencing 502 Bad Gateway errors, preventing creation of new API keys.

### Overall Status: ❌ FAILED
- **Infrastructure Health Score**: 45.5% (5/11 checks passed) - Improved from 27.3%
- **Authentication Success Rate**: 5.0% (1/20 tests passed) - Decreased from 15.0%
- **Model Registration Success**: 25.0% (1/4 stages passed) - Improved from 0%
- **Test Suite Success Rate**: 22.2% (2/9 test scripts passed) - Same as before

## Critical Issues for Infrastructure Team

### 1. Auth Service 502 Bad Gateway - CRITICAL
**Impact**: Cannot create new API keys or authenticate  
**Affected Endpoints**: All endpoints at `https://auth.hokus.ai`
- `/health` - Returns 502 Bad Gateway
- `/api/v1/keys` - Returns 502 Bad Gateway

**Root Cause**: The auth service appears to be misconfigured or not properly deployed after migration

**Recommendation**: 
1. Check auth service ECS task logs
2. Verify ALB target group health checks for auth service
3. Ensure auth service container is starting properly

### 2. MLflow Proxy Routes Missing - CRITICAL
**Impact**: All MLflow operations fail with 404  
**Affected Endpoints**: All `/api/mlflow/*` endpoints
- `/api/mlflow/api/2.0/mlflow/experiments/search` - 404
- `/api/mlflow/api/2.0/mlflow/runs/create` - 404
- `/api/mlflow/api/2.0/mlflow/model-versions/create` - 404

**Root Cause**: ALB listener rules not configured for MLflow proxy paths

**Recommendation**: 
1. Add ALB listener rules for `/api/mlflow/*` → MLflow service
2. Verify MLflow service is running on correct port
3. Update target group configuration

### 3. Service Deployment Status - IMPROVED
**Impact**: Services now show as running but not functioning correctly  
**Service Status**:
- `hokusai-auth-development` - ✅ Running (1/1 tasks) but returning 502
- `hokusai-api-development` - ✅ Running (1/1 tasks) but routes missing
- `hokusai-mlflow-development` - ✅ Running (1/1 tasks) but not accessible

**Recommendation**: Services are deployed but misconfigured. Check:
1. Container health checks
2. ALB routing configuration
3. Security group rules

## Test Results Summary

### Infrastructure Health Check
- ALB endpoints: 0/5 healthy (all returning errors)
- ECS services: 3/3 running (improved from 1/3)
- MLflow service: 2/3 checks passed (404s considered "healthy" for missing routes)
- Overall health score: 45.5%

### Authentication Testing
- Bearer token auth: Failed (404 errors)
- X-API-Key auth: Failed (404 errors)
- Auth service integration: Failed (502 errors)
- Only rate limiting test passed (no rate limits triggered)

### Model Registration Flow
- Stage 1: ✅ Local model creation (works)
- Stage 2: ❌ MLflow experiment creation (404)
- Stage 3: ❌ Model run logging (404)
- Stage 4: ❌ Model registration (404)

### Endpoint Availability
- Available endpoints: 6 (returning 401 authentication errors)
- Unavailable endpoints: 5 (returning 404 not found)
- Key finding: Direct API endpoints exist but MLflow proxy routes missing

## Comparison with Previous Test (2025-07-30)

| Metric | Previous | Current | Change |
|--------|----------|---------|--------|
| Infrastructure Health | 27.3% | 45.5% | +18.2% |
| Auth Success Rate | 15.0% | 5.0% | -10.0% |
| Model Registration | 0% | 25.0% | +25.0% |
| ECS Services Running | 1/3 | 3/3 | +2 |

### Improvements
- All ECS services now deployed and running
- Local model creation working
- Some direct API endpoints accessible

### Regressions
- Auth service now returning 502 (was 503)
- Cannot create new API keys
- Authentication success rate decreased

## Infrastructure Configuration Issues

### ALB Listener Rules Missing
The following routes need to be added to the ALB:
```terraform
# MLflow proxy routes
resource "aws_lb_listener_rule" "mlflow_proxy" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 100
  
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.mlflow.arn
  }
  
  condition {
    path_pattern {
      values = ["/api/mlflow/*"]
    }
  }
}
```

### Auth Service Configuration
The auth service needs:
1. Proper health check configuration
2. Environment variables for database connection
3. Redis connection for caching
4. Correct port mapping (8000)

## Recommendations for Infrastructure Team

### Immediate Actions (Priority 1)
1. **Fix Auth Service 502 Error**
   - Check ECS task logs: `aws ecs describe-tasks --cluster hokusai-development --tasks <task-arn>`
   - Verify environment variables are set
   - Check database connectivity

2. **Configure ALB Routing for MLflow**
   - Add listener rules for `/api/mlflow/*`
   - Verify target group health checks
   - Test with curl after configuration

3. **Verify Security Groups**
   - Ensure ALB can reach ECS tasks
   - Check ingress rules for port 8000
   - Verify inter-service communication

### Follow-up Actions (Priority 2)
1. Update health check paths if needed
2. Configure proper logging for debugging
3. Set up monitoring alerts
4. Document the final configuration

## Testing Command Reference

For infrastructure team to verify fixes:
```bash
# Test auth service
curl -v https://auth.hokus.ai/health

# Test API service
curl -H "X-API-Key: <key>" https://registry.hokus.ai/api/health

# Test MLflow proxy
curl -H "X-API-Key: <key>" https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search

# Check ECS services
aws ecs list-services --cluster hokusai-development
aws ecs describe-services --cluster hokusai-development --services hokusai-auth-development hokusai-api-development hokusai-mlflow-development
```

## Next Steps

1. Infrastructure team fixes auth service 502 error
2. Infrastructure team adds MLflow ALB routing rules
3. Re-run test suite after fixes applied
4. Create new API key once auth service is working
5. Validate full model registration workflow

## Appendix: Test Execution Details

- Test execution timestamp: 2025-08-05T09:27:17
- Test framework: Python-based comprehensive test suite
- Total execution time: ~38 seconds
- Detailed logs: See `test_execution_summary.json` and individual test reports