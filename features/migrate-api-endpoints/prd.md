# Product Requirements Document: API Endpoint Migration

## Objectives

Migrate API endpoints to align with the documented endpoint structure defined in `docs/API_ENDPOINT_REFERENCE.md` and `docs/AUTHENTICATION_GUIDE.md`. Ensure all routes are properly standardized, tested, and maintain backward compatibility where necessary.

## Personas

**Data Scientists**: Use the API to register models, track experiments, and manage ML workflows through MLflow integration
**Platform Engineers**: Deploy and maintain the API service, monitor health, and configure routing
**Third-party Developers**: Integrate with Hokusai API using documented endpoints and authentication

## Success Criteria

1. All API endpoints match documented structure in API_ENDPOINT_REFERENCE.md
2. Authentication middleware properly enforces access control per AUTHENTICATION_GUIDE.md  
3. MLflow proxy routes work seamlessly with standard MLflow clients
4. Health check endpoints are accessible without authentication
5. All existing tests pass with updated endpoint paths
6. No breaking changes for existing API consumers (backward compatibility maintained)
7. API documentation (OpenAPI/Swagger) reflects actual implementation

## Tasks

### Phase 1: Analysis and Planning
Conduct comprehensive audit of current vs. documented endpoints to identify exact migration requirements. Review all route definitions, path prefixes, and authentication rules.

### Phase 2: Core Endpoint Migration
Update main route definitions in FastAPI routers to match documented structure. Focus on models, DSPy, and MLflow proxy endpoints while maintaining existing functionality.

### Phase 3: Health Check Standardization  
Consolidate and standardize health check endpoints across different route modules. Ensure consistent response formats and proper exclusion from authentication.

### Phase 4: Authentication Updates
Verify authentication middleware correctly identifies protected vs. public endpoints. Update authentication bypass rules to match documented requirements.

### Phase 5: MLflow Integration
Ensure MLflow proxy routes handle both `/mlflow/*` and `/api/mlflow/*` patterns correctly. Verify artifact upload/download endpoints work with proper path translation.

### Phase 6: Testing Updates
Update all test files with new endpoint paths. Ensure integration tests cover authentication, rate limiting, and error handling for migrated endpoints.

### Phase 7: Documentation and Deployment
Update OpenAPI schema generation to reflect actual routes. Verify Swagger/ReDoc documentation displays correct endpoint information. Prepare deployment configuration updates if needed.

## Technical Requirements

**Framework**: FastAPI with async support
**Authentication**: API key validation via external auth service with caching
**Routing**: RESTful patterns with proper HTTP methods and status codes
**Backward Compatibility**: Support deprecated paths with deprecation warnings
**Testing**: Comprehensive unit and integration test coverage
**Documentation**: Auto-generated OpenAPI/Swagger documentation