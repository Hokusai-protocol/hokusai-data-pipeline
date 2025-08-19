# Bug Investigation: Model Registration Still Failing

## Bug Summary

**Issue**: Complete MLflow platform inaccessibility preventing all model registration, tracking, and serving operations
**Severity**: CRITICAL
**Affected Users**: All data science teams, ML engineers, and downstream services relying on model deployment
**Business Impact**: Complete blockage of ML model deployment pipeline, preventing LSCOR model (93.3% accuracy) and other models from being deployed to production

## Reproduction Steps

**Environment Required**:
- API Key: `hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN`
- Python 3.11+ with hokusai-ml-platform package
- Access to registry.hokus.ai endpoints

**Steps to Reproduce**:
1. Set HOKUSAI_API_KEY environment variable
2. Attempt to access https://registry.hokus.ai/ (returns 404)
3. Try MLflow API endpoints at https://registry.hokus.ai/api/mlflow/* (all return 404)
4. Attempt model registration using hokusai-ml-platform SDK (fails with authentication/404 errors)

**Success Rate**: 100% reproduction - all attempts fail consistently
**Variations**: Failures occur across all endpoints, authentication methods, and API paths

## Affected Components

**Services**:
- MLflow service (hokusai-mlflow-development)
- API service (hokusai-api-development) 
- Model registry backend
- Authentication proxy layer

**Infrastructure**:
- ALB routing rules (hokusai-main-development, hokusai-registry-development)
- ECS services and task definitions
- Service discovery (mlflow.hokusai-development.local)
- DNS configuration for registry.hokus.ai

**Database**:
- PostgreSQL RDS instance (hokusai-mlflow-development)
- MLflow tables (experiments, runs, models, model_versions)

**API Endpoints**:
- /api/mlflow/* (proxy endpoints)
- /api/2.0/mlflow/* (MLflow tracking API)
- /health (health check endpoints)

## Initial Observations

**Error Messages**:
- `INTERNAL_ERROR: Response: {'detail': 'Not Found'}` - 404 on all registry.hokus.ai paths
- `API key required` - Authentication rejection despite valid API key
- `Failed to create MLflow client after 3 attempts`

**Recent Changes** (from git history):
- Infrastructure migration to centralized hokusai-infrastructure repo
- Multiple attempted fixes for database authentication
- Redis queue integration
- ALB routing configuration changes

**Similar Past Issues**:
- Multiple completed Linear tickets for service connectivity problems
- Previous database authentication issues (now marked as Done)
- Redis connection problems (marked as Done)

## Data Analysis Required

**Logs to Examine**:
- CloudWatch logs: `/ecs/hokusai-mlflow-development`
- CloudWatch logs: `/ecs/hokusai-api-development`
- ALB access logs for registry.hokus.ai
- ECS task startup logs

**Infrastructure Checks**:
- ALB listener rules and target group health
- Security group configurations
- Route 53 DNS records for registry.hokus.ai
- ECS service health and task status

**Application Configuration**:
- Environment variables in ECS task definitions
- MLflow server configuration
- API proxy configuration for /api/mlflow routes

## Investigation Strategy

**Priority Order**:
1. Verify infrastructure basics (DNS, ALB routing, target groups)
2. Check ECS service health and container logs
3. Test internal service connectivity
4. Validate authentication flow
5. Review recent configuration changes

**Key Questions**:
- Is registry.hokus.ai DNS resolving correctly?
- Are ALB listener rules properly configured for MLflow paths?
- Is the MLflow service actually running and healthy?
- Is the API proxy service correctly routing to MLflow?
- Are there any security group or network ACL blocks?

**Success Criteria**:
- Identify exact point of failure in request flow
- Determine if issue is infrastructure, application, or configuration
- Find root cause preventing 404 resolution

## Risk Assessment

**Current Impact**: 
- CRITICAL - Complete service outage
- No model deployment capability
- Development teams blocked

**Escalation Potential**:
- High - affects entire ML platform
- Could delay product launches dependent on ML models

**Security Implications**:
- API keys potentially exposed in logs during debugging
- Need to ensure authentication isn't bypassed during fixes

**Data Integrity**:
- Low risk - read operations failing, no data corruption
- Existing models in S3/database unaffected

## Timeline

**First Reported**: August 18, 2025
**Last Confirmation**: August 19, 2025 (13:57 UTC)
**Pattern**: Constant failure, not intermittent
**Correlation**: Issues began after infrastructure migration to centralized repo
**Previous Fix Attempts**: Multiple Linear tickets marked "Done" but issue persists