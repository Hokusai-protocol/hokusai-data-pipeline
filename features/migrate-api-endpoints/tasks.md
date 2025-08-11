# API Endpoint Migration Tasks

## 1. [ ] Analysis and Planning
   a. [ ] Compare current routes in src/api/routes/* with docs/API_ENDPOINT_REFERENCE.md
   b. [ ] Document all discrepancies between implementation and documentation
   c. [ ] Identify deprecated endpoints that need backward compatibility
   d. [ ] Create migration checklist for each route module
   e. [ ] Review authentication requirements for each endpoint group

## 2. [ ] Core Endpoint Migration (Dependent on Analysis)
   a. [ ] Update model management routes in src/api/routes/models.py
   b. [ ] Verify DSPy pipeline routes in src/api/routes/dspy.py match /api/v1/dspy/* pattern
   c. [ ] Ensure contributor analytics endpoints follow documented structure
   d. [ ] Add any missing model comparison and evaluation endpoints
   e. [ ] Implement batch operations endpoint if not present

## 3. [ ] Health Check Standardization
   a. [ ] Consolidate health endpoints in src/api/routes/health.py
   b. [ ] Ensure /health, /ready, /live, /version, /metrics are all present
   c. [ ] Standardize response formats per documentation
   d. [ ] Remove authentication requirements from health endpoints
   e. [ ] Add comprehensive service status endpoint at /health/status

## 4. [ ] Authentication Updates (Dependent on Health Check Standardization)
   a. [ ] Update AUTH_EXCLUDED_PATHS in src/middleware/auth.py
   b. [ ] Verify all documented public endpoints are excluded from auth
   c. [ ] Ensure DSPy health endpoint (/api/v1/dspy/health) is public
   d. [ ] Test authentication bypass for documentation endpoints
   e. [ ] Validate API key extraction from all supported methods

## 5. [ ] MLflow Integration
   a. [ ] Fix MLflow health check routes to match documented paths
   b. [ ] Ensure both /mlflow/* and /api/mlflow/* patterns work
   c. [ ] Verify artifact endpoints handle path translation correctly
   d. [ ] Test MLflow proxy with standard MLflow Python client
   e. [ ] Validate circuit breaker integration for MLflow connectivity

## 6. [ ] Testing Updates (Dependent on Core Endpoint Migration)
   a. [ ] Update endpoint URLs in tests/integration/services/test_api_endpoints.py
   b. [ ] Fix paths in tests/test_api_routes.py
   c. [ ] Update MLflow proxy tests with new routing
   d. [ ] Verify authentication tests cover all protected endpoints
   e. [ ] Add tests for backward compatibility if applicable

## 7. [ ] Write and implement tests
   a. [ ] Unit tests for route definitions
   b. [ ] Integration tests for authentication flow
   c. [ ] End-to-end tests for model registration
   d. [ ] Performance tests for MLflow proxy
   e. [ ] Error handling tests for invalid routes

## 8. [ ] Documentation Updates
   a. [ ] Verify OpenAPI schema generation reflects actual routes
   b. [ ] Update inline code documentation and docstrings
   c. [ ] Ensure Swagger UI at /docs shows correct endpoints
   d. [ ] Update ReDoc documentation at /redoc
   e. [ ] Add migration notes to README.md if breaking changes