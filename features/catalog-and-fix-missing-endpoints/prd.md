# Product Requirements Document: Catalog and Fix Missing Endpoints

## Objectives

1. Resolve 404 errors for API endpoints (/models, /docs) that should be functional
2. Ensure all documented API endpoints are properly registered and accessible
3. Fix authentication middleware conflicts preventing endpoint access
4. Standardize import paths and module registration
5. Create comprehensive endpoint documentation

## User Personas

### API Consumers
- Third-party developers integrating with Hokusai
- Need reliable access to model registration endpoints
- Require clear API documentation through /docs endpoint

### Internal Developers
- Need consistent endpoint naming and routing
- Require proper authentication bypass for documentation
- Need clear understanding of available endpoints

### DevOps Team
- Need health check endpoints functioning properly
- Require monitoring endpoints for service status
- Need consistent logging for debugging

## Success Criteria

1. **/docs endpoint returns 200** - FastAPI documentation is accessible
2. **/models endpoints function correctly** - Model registration and listing work
3. **Authentication endpoints available** - If auth router should be included
4. **No double-prefix issues** - Routes resolve to expected paths
5. **Import conflicts resolved** - All modules properly registered
6. **Comprehensive endpoint catalog** - Complete list of all available endpoints

## Implementation Tasks

### Fix Import and Registration Issues
- Resolve authentication module conflicts between src/middleware/auth.py and src/api/middleware/auth.py
- Update __init__.py files to properly export all route modules
- Fix main.py imports to use consistent paths
- Remove duplicate router mounting for MLflow proxy

### Fix Models Endpoint Double Prefix
- Review models.py router definitions
- Either remove prefix from route decorators or from router mounting
- Ensure /models returns model list, not /models/models
- Test all model-related endpoints

### Enable Documentation Access
- Verify /docs and /redoc endpoints are accessible
- Check authentication middleware bypass list
- Ensure production settings don't block documentation
- Add /openapi.json to bypass if needed

### Catalog All Endpoints
- Create comprehensive list of all available endpoints
- Document expected request/response for each
- Identify any endpoints that should exist but don't
- Remove references to non-existent endpoints

### Testing and Validation
- Create test script to verify all endpoints
- Test with and without authentication
- Verify correct HTTP status codes
- Ensure proper error messages for invalid requests

## Technical Requirements

### Endpoint Standards
- Use consistent URL patterns (/api/v1/* for versioned APIs)
- Follow RESTful conventions for resource endpoints
- Ensure proper HTTP method usage (GET for reads, POST for creates)

### Authentication Requirements
- Documentation endpoints must be accessible without authentication
- Health check endpoints should bypass authentication
- API endpoints require valid API key
- Clear error messages for authentication failures

### Error Handling
- Return 404 only for truly non-existent endpoints
- Use 401 for authentication failures
- Use 403 for authorization failures
- Include helpful error messages in responses

## Constraints

- Maintain backward compatibility for existing working endpoints
- Don't break current MLflow proxy functionality
- Preserve existing authentication flow for protected endpoints
- Keep health check endpoints lightweight and fast