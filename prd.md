# Product Requirements Document: Implement PR #60 Recommended Enhancements

## Objective
Implement the three recommendations identified during the PR #60 deployment verification to improve the MLflow proxy routing functionality and user experience.

## Background
PR #60 successfully fixed MLflow proxy routing for model registration, but during testing we identified three areas for improvement:
1. Documentation needs updating to reflect the working endpoints
2. ALB routing configuration prevents `/mlflow/*` paths from working
3. Health check endpoints return 404 due to routing issues

## Personas
- **Third-party developers**: Need clear documentation on how to integrate with Hokusai's MLflow endpoint
- **DevOps engineers**: Need working health check endpoints for monitoring
- **Internal developers**: Need consistent routing patterns across all endpoints

## Success Criteria
- Third-party developers can easily find and use the correct MLflow tracking URI
- `/mlflow/*` paths work alongside `/api/mlflow/*` paths
- Health check endpoints return proper status codes and information
- All changes are backward compatible with existing integrations

## Scope

### In Scope
1. Update documentation to specify `https://registry.hokus.ai/api/mlflow` as the MLflow tracking URI
2. Fix ALB routing rules to properly route `/mlflow/*` requests
3. Deploy health check endpoints to accessible paths

### Out of Scope
- Changes to authentication mechanisms
- Modifications to the core proxy logic
- Updates to non-MLflow related endpoints

## Tasks

### 1. Update Documentation
- Update README.md with MLflow integration instructions
- Create a dedicated MLflow integration guide in the documentation
- Update API documentation to reflect correct endpoints
- Add examples for common MLflow operations

### 2. Fix ALB Routing
- Analyze current ALB routing rules and priorities
- Update terraform configuration to fix routing conflicts
- Ensure `/mlflow/*` routes to MLflow service correctly
- Test both `/mlflow/*` and `/api/mlflow/*` paths work

### 3. Deploy Health Check Endpoints
- Move health check endpoints to working paths (e.g., `/api/health/mlflow`)
- Ensure health checks work through ALB routing
- Add comprehensive health check information
- Update monitoring configurations to use new endpoints

## Technical Considerations
- Maintain backward compatibility for existing `/api/mlflow/*` integrations
- Ensure terraform changes can be safely applied without downtime
- Test all changes in development before production deployment
- Consider ALB rule priorities to avoid routing conflicts

## Rollout Plan
1. Implement and test documentation changes (no deployment needed)
2. Test ALB routing changes in development environment
3. Deploy health check endpoint changes
4. Apply ALB routing fixes during maintenance window
5. Verify all endpoints work correctly
6. Update monitoring systems to use new health check endpoints