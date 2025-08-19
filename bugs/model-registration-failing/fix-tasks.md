# Fix Tasks: Model Registration Failure

## Priority 1: CRITICAL - Immediate Fix

### 1. Fix Syntax Error and Deploy
- [ ] Verify syntax error is fixed in current codebase
  - [ ] Check src/services/model_registry.py line 26
  - [ ] Ensure proper parameter definition without syntax errors
  - [ ] Verify no other syntax errors in the file
- [ ] Build new Docker image for API service
  - [ ] Run `docker build -t hokusai-api:fix-syntax -f Dockerfile.api .`
  - [ ] Test container starts locally: `docker run --rm hokusai-api:fix-syntax python -c "from src.api.main import app"`
  - [ ] Verify no import errors during startup
- [ ] Push image to ECR
  - [ ] Tag image with commit hash: `1cdcfc3`
  - [ ] Push to ECR repository: `932100697590.dkr.ecr.us-east-1.amazonaws.com/hokusai-api`
- [ ] Deploy to ECS
  - [ ] Update ECS service to use new image
  - [ ] Monitor deployment rollout
  - [ ] Verify tasks reach healthy state

## Priority 1: CRITICAL - Testing Tasks

### 2. Pre-deployment Testing
- [ ] Add syntax validation test
  - [ ] Create test_syntax.py to validate all Python files compile
  - [ ] Run as part of CI pipeline before building Docker image
- [ ] Test model registration flow locally
  - [ ] Start API service locally
  - [ ] Verify /api/mlflow/* endpoints respond
  - [ ] Test with actual MLflow connection

### 3. Post-deployment Validation
- [ ] Verify API service health
  - [ ] Check ECS service shows 1/1 running tasks
  - [ ] Confirm no restart loops in CloudWatch logs
  - [ ] Validate target group shows healthy targets
- [ ] Test all critical endpoints
  - [ ] `curl https://registry.hokus.ai/health` returns 200
  - [ ] `curl https://registry.hokus.ai/api/mlflow/health` returns 200
  - [ ] `curl https://registry.hokus.ai/api/2.0/mlflow/experiments/list` returns valid response
- [ ] Validate model registration
  - [ ] Use test script with API key `hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN`
  - [ ] Register a test model
  - [ ] Verify model appears in MLflow UI

## Priority 2: HIGH - Prevention & Monitoring

### 4. CI/CD Pipeline Improvements
- [ ] Add pre-build validation
  - [ ] Python syntax check: `python -m py_compile src/**/*.py`
  - [ ] Import validation: `python -c "from src.api.main import app"`
  - [ ] Type checking with mypy if configured
- [ ] Add smoke tests to Dockerfile
  - [ ] Add RUN statement to test imports during build
  - [ ] Fail build if application cannot start
- [ ] Implement deployment validation
  - [ ] Add health check wait after deployment
  - [ ] Auto-rollback if health checks fail

### 5. Monitoring Enhancements
- [ ] Create CloudWatch alarms
  - [ ] ECS service task count < desired count
  - [ ] Container restart rate > threshold
  - [ ] API endpoint latency > 5 seconds
  - [ ] 5xx error rate > 1%
- [ ] Add startup validation logging
  - [ ] Log successful module imports
  - [ ] Log configuration loading
  - [ ] Log service discovery results
- [ ] Create service status dashboard
  - [ ] ECS task health visualization
  - [ ] API response time graphs
  - [ ] Error rate tracking

## Priority 3: MEDIUM - Code Quality

### 6. Code Improvements
- [ ] Refactor model_registry.py configuration
  - [ ] Move hardcoded IPs to environment variables
  - [ ] Implement proper service discovery fallback
  - [ ] Add configuration validation on startup
- [ ] Improve error handling
  - [ ] Add try-catch around MLflow client initialization
  - [ ] Provide meaningful error messages
  - [ ] Implement graceful degradation
- [ ] Add configuration documentation
  - [ ] Document all environment variables
  - [ ] Explain service discovery mechanism
  - [ ] Provide troubleshooting guide

### 7. Testing Infrastructure
- [ ] Add comprehensive unit tests
  - [ ] Test model_registry initialization
  - [ ] Test configuration loading
  - [ ] Test error scenarios
- [ ] Add integration tests
  - [ ] Test full model registration flow
  - [ ] Test API proxy functionality
  - [ ] Test authentication flow
- [ ] Add load tests
  - [ ] Verify service handles concurrent requests
  - [ ] Test circuit breaker behavior
  - [ ] Validate timeout configurations

## Priority 4: LOW - Documentation

### 8. Documentation Updates
- [ ] Update troubleshooting guide
  - [ ] Add "API service won't start" section
  - [ ] Document common syntax error patterns
  - [ ] Provide debugging commands
- [ ] Update deployment documentation
  - [ ] Add pre-deployment checklist
  - [ ] Document rollback procedure
  - [ ] Include validation steps
- [ ] Create incident postmortem
  - [ ] Document timeline of failure
  - [ ] List contributing factors
  - [ ] Define action items

## Dependencies & Sequence

1. **Immediate**: Tasks 1-3 must be done in sequence (fix → deploy → validate)
2. **Parallel**: Tasks 4-5 can be done in parallel after fix is deployed
3. **Follow-up**: Tasks 6-8 can be done after service is stable

## Rollback Plan

If deployment fails or causes new issues:
1. [ ] Revert ECS task definition to previous version (revision 108)
2. [ ] Monitor service health
3. [ ] Investigate new issues before retry
4. [ ] Consider manual fixes in running container as temporary measure

## Success Criteria

- [ ] API service running with 0 restarts in 30 minutes
- [ ] All /api/mlflow/* endpoints return 200/201 status codes
- [ ] Model registration test succeeds with test model
- [ ] No syntax errors in CloudWatch logs
- [ ] ALB target group shows all targets healthy