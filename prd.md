# Product Requirements Document: Update Proxy Routing

## Objective

Fix the API proxy routing configuration to enable successful model registration by properly routing MLflow artifact storage requests. The current routing setup causes 404 errors when attempting to upload model artifacts, preventing third-party model registration from completing successfully.

## Current State

The Hokusai platform has successfully deployed MLflow with artifact storage support (`--serve-artifacts` flag), but model registration fails because:

1. The API proxy at `registry.hokus.ai` incorrectly routes artifact requests to external URLs instead of the internal MLflow service
2. MLflow artifact endpoints (`/api/2.0/mlflow-artifacts/*`) return 404 errors
3. The MLFLOW_SERVER_URL environment variable in the proxy points to `https://registry.hokus.ai/mlflow` instead of the internal MLflow service

## Target State

Enable end-to-end model registration by:

1. Configuring the API proxy to correctly route artifact requests to the internal MLflow service
2. Ensuring all MLflow API endpoints (experiments, models, and artifacts) work correctly
3. Maintaining backward compatibility with existing API paths
4. Supporting standard MLflow client configuration

## User Personas

1. **Data Scientists**: Need to register models using standard MLflow Python client without custom configuration
2. **Third-Party Developers**: Require reliable API endpoints for programmatic model registration
3. **Platform Engineers**: Need clear routing configuration that's maintainable and debuggable

## Success Criteria

1. Model registration completes successfully using `test_real_registration.py`
2. All MLflow endpoints respond correctly:
   - Experiments API: `/api/2.0/mlflow/experiments/*`
   - Models API: `/api/2.0/mlflow/model-versions/*`
   - Artifacts API: `/api/2.0/mlflow-artifacts/*`
3. Standard MLflow client configuration works without modifications
4. Existing `/mlflow/*` paths continue to work for backward compatibility
5. No authentication errors or routing conflicts

## Tasks

### 1. Update MLflow Server URL Configuration
- Modify the MLFLOW_SERVER_URL environment variable to point to the internal MLflow service
- Use ECS service discovery or internal DNS instead of external URLs
- Ensure the proxy can reach MLflow service internally within the VPC

### 2. Fix Artifact Request Routing
- Update the proxy_request function to handle artifact endpoints correctly
- Ensure artifact requests are routed to the MLflow service, not external URLs
- Maintain proper path translation for ajax-api endpoints

### 3. Implement Service Discovery
- Configure ECS service discovery for the MLflow service
- Update API service to use internal service names
- Remove hardcoded external URLs from environment variables

### 4. Update ALB Routing Rules
- Ensure `/api/mlflow/*` requests are properly forwarded to the API service
- Verify no conflicts with existing `/api*` rules
- Maintain auth service routing functionality

### 5. Add Comprehensive Logging
- Log all routing decisions in the proxy
- Include request paths, translated paths, and target URLs
- Add metrics for successful vs failed proxied requests

### 6. Create Health Check Endpoints
- Add endpoint to verify MLflow service connectivity
- Include checks for all three API types (experiments, models, artifacts)
- Return detailed status information for debugging

### 7. Update Documentation
- Document the internal routing architecture
- Provide troubleshooting guide for common routing issues
- Include examples of successful model registration

## Technical Constraints

1. Must maintain backward compatibility with existing API paths
2. Cannot modify MLflow client code (paths are hardcoded)
3. Must work within AWS ECS networking constraints
4. Should not expose internal service URLs externally

## Dependencies

1. MLflow container must be running with `--serve-artifacts` flag (already deployed)
2. S3 bucket for artifact storage must be accessible (already configured)
3. IAM roles must have proper permissions (already configured)
4. Auth service must be operational for API key validation

## Risk Mitigation

1. Test all changes in development environment first
2. Implement gradual rollout with monitoring
3. Maintain rollback plan if issues arise
4. Ensure comprehensive logging for debugging production issues