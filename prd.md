# Product Requirements Document: Fix Deployment Health Check Failures

## Objective

Resolve ECS task health check failures that are preventing successful deployments and causing service instability. Multiple tasks are failing with "Task failed container health checks" errors, blocking the deployment pipeline and requiring manual intervention.

## Current State

The Hokusai platform is experiencing deployment failures due to:

1. ECS tasks consistently failing container health checks during deployment
2. Mixed running/desired task counts indicating incomplete rollouts
3. Deployments stuck in IN_PROGRESS state indefinitely
4. Health check endpoints potentially misconfigured or not responding correctly

Current health check configuration:
- API service expects `/health` endpoint returning HTTP 200
- MLflow service expects `/mlflow` endpoint returning HTTP 200 or 308
- Both services have 60-second start period before health checks begin

## Target State

Achieve reliable, zero-downtime deployments by:

1. Ensuring all ECS tasks pass health checks consistently
2. Implementing comprehensive health check endpoints that accurately reflect service readiness
3. Optimizing health check timing parameters for service startup requirements
4. Providing clear diagnostics when health check failures occur

## User Personas

1. **DevOps Engineers**: Need reliable deployment pipeline with clear failure diagnostics
2. **Backend Developers**: Require stable deployment process to ship features quickly  
3. **Platform Users**: Expect zero downtime and consistent service availability

## Success Criteria

1. 100% of ECS tasks pass health checks during deployment
2. Deployments complete successfully within 10 minutes without manual intervention
3. Health check endpoints provide accurate service readiness status
4. CloudWatch logs clearly indicate health check failure reasons
5. Zero downtime achieved during rolling deployments

## Tasks

### 1. Audit Current Health Check Implementation
- Verify `/health` endpoint exists and implementation in API service
- Verify `/mlflow` endpoint exists and implementation in MLflow service
- Review CloudWatch logs for specific health check failure messages
- Test health check endpoints locally to ensure correct responses

### 2. Implement Robust Health Check Endpoints
- Create comprehensive health checks that verify:
  - Application startup completion
  - Database connectivity (with timeout)
  - Critical dependencies availability
  - Memory and resource availability
- Return detailed JSON response with component status
- Implement graceful degradation for non-critical components

### 3. Optimize Health Check Timing Parameters
- Analyze actual service startup times from CloudWatch logs
- Increase start period if services need more initialization time
- Adjust interval and timeout for network latency
- Configure appropriate retry counts

### 4. Add Health Check Diagnostics and Monitoring
- Implement detailed logging for health check requests/responses
- Add structured logging with correlation IDs
- Create CloudWatch metrics for health check success rates
- Set up alarms for repeated health check failures

### 5. Fix Container Health Check Commands
- Update container definitions with correct health check commands
- Ensure curl is available in container images
- Validate health check URLs match actual endpoints
- Test commands within running containers

### 6. Implement Graceful Shutdown
- Add SIGTERM handlers to services
- Implement connection draining
- Ensure in-flight requests complete before shutdown
- Configure appropriate deregistration delay

### 7. Create Testing and Validation Process
- Build local testing environment for health checks
- Create integration tests for deployment process
- Implement smoke tests post-deployment
- Document rollback procedures

## Technical Constraints

1. Must maintain backward compatibility with existing monitoring
2. Cannot increase container startup time beyond 5 minutes
3. Must work within ECS Fargate limitations
4. Should not require infrastructure changes

## Dependencies

1. Container images must include health check tools (curl)
2. Services must have proper IAM permissions for AWS resources
3. Database must be accessible from ECS tasks
4. Load balancers must be properly configured

## Risk Mitigation

1. Test all changes in development environment first
2. Implement changes incrementally with validation
3. Maintain ability to quickly rollback
4. Monitor deployment metrics during rollout
5. Have on-call engineer available during first production deployment