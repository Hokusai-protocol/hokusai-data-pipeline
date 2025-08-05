# Product Requirements Document: Fix API Connectivity Issues

## Objectives

Restore full functionality to the Hokusai data pipeline API connectivity, enabling successful model registration through MLflow integration. This involves fixing critical infrastructure routing issues, internal service communication failures, and authentication problems that are currently blocking production workflows.

## Personas

- **Data Scientists**: Need to register and deploy ML models through the Hokusai platform
- **Third-party Developers**: Require reliable API access for model registration using API keys
- **DevOps Engineers**: Need to maintain and monitor the infrastructure health
- **Platform Users**: Expect seamless model deployment and management capabilities

## Success Criteria

1. MLflow proxy endpoints return successful responses (200/201) instead of 404/502 errors
2. Internal service-to-service communication works between API and MLflow services
3. API key authentication successfully validates platform keys
4. Model registration workflow completes end-to-end without errors
5. Infrastructure health score improves from 54.5% to >90%
6. All integration tests pass with the platform API key

## Technical Requirements

### ALB Routing Configuration
- Modify ALB listener rules to route `/api/mlflow/*` requests to the API service target group
- Remove direct routing from ALB to MLflow service for proxy endpoints
- Ensure health check paths are correctly configured for both services
- Maintain separate routing for direct MLflow access where needed

### Service Discovery Setup
- Implement ECS service discovery for internal service communication
- Configure Cloud Map namespace for service DNS resolution
- Enable API service to resolve MLflow service hostname dynamically
- Set up proper networking for container-to-container communication

### Authentication Fixes
- Update authentication middleware to properly validate platform API keys
- Fix the auth service integration to return user context correctly
- Ensure API key headers are properly forwarded to auth service
- Implement proper error handling for authentication failures

### Network Security
- Review and update security group rules for inter-service communication
- Ensure port 5000 is accessible between API and MLflow services
- Validate that health check ports are properly configured
- Implement least-privilege access controls

## Implementation Tasks

### Infrastructure Changes
- Update `infrastructure/terraform/alb-listener-rules.tf` with correct routing rules
- Configure service discovery in `infrastructure/terraform/service-discovery.tf`
- Modify security groups in `infrastructure/terraform/main.tf`
- Update target group configurations for proper health checks

### Application Code Updates
- Fix MLflow proxy configuration in `src/api/routes/mlflow_proxy_improved.py`
- Update environment variables in `src/api/utils/config.py`
- Implement retry logic for internal service calls
- Add comprehensive error logging for debugging

### Testing and Validation
- Run `test_model_registration_complete.py` with platform API key
- Validate all endpoints using `scripts/test_mlflow_connection.py`
- Verify health checks with `scripts/test_health_endpoints.py`
- Execute integration test suite for full validation

## Dependencies

- Access to AWS infrastructure for ALB and ECS configuration
- Valid platform API key for testing (hk_live_NVWOYDfNfTJyFzUDkQDBk2LLA4pB5qza)
- Coordination with infrastructure team for terraform changes
- MLflow service must be running with artifact storage configured

## Risk Mitigation

- Create rollback plan for ALB configuration changes
- Test changes in development environment first
- Monitor service health metrics during deployment
- Implement gradual rollout with canary deployments
- Maintain backup of current working configuration

## Monitoring and Alerts

- Set up CloudWatch alarms for 502 error rates
- Monitor ECS task health and restart counts
- Track API response times and latency
- Alert on authentication failure spikes
- Dashboard for infrastructure health score visualization