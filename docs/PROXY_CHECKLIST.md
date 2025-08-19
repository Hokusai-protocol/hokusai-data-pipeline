# Proxy Modification Checklist

## Overview
This checklist MUST be followed when modifying any proxy functionality in the Hokusai data pipeline. Proxy functions are critical for maintaining authentication across service boundaries.

## Pre-Implementation Review

### 1. Identify Affected Services
- [ ] List all upstream services this proxy will communicate with
- [ ] Document the authentication method for each service (Bearer token, API key, etc.)
- [ ] Identify service discovery names vs external URLs
- [ ] Check if services require specific headers beyond Authorization

### 2. Document Current Auth Flow
- [ ] Map the current authentication flow from client → proxy → upstream service
- [ ] Identify all headers currently being forwarded
- [ ] Note any header transformations being performed
- [ ] Document any service-specific auth requirements

### 3. Required Headers Inventory
- [ ] `Authorization`: Bearer token (REQUIRED - never strip this)
- [ ] `X-User-ID`: User identifier for audit logging
- [ ] `X-Request-ID`: Request tracing identifier
- [ ] `X-Tenant-ID`: Multi-tenancy identifier (if applicable)
- [ ] `Content-Type`: Request content type
- [ ] Custom headers required by specific services

## Implementation Guidelines

### 4. Code Implementation
- [ ] Preserve ALL incoming headers by default: `headers = dict(request.headers)`
- [ ] Never create empty header dictionaries: ~~`headers = {}`~~
- [ ] Forward Authorization header explicitly if modifying headers
- [ ] Maintain header case sensitivity where required
- [ ] Handle both internal (service discovery) and external (ALB) routes

### 5. Error Handling
- [ ] Handle 401 Unauthorized responses appropriately
- [ ] Preserve error context when auth fails
- [ ] Log auth failures with sufficient detail (without logging tokens)
- [ ] Return meaningful error messages to clients

### 6. MLflow-Specific Considerations
- [ ] Ensure MLflow tracking URI includes auth headers
- [ ] Forward headers for model registry operations
- [ ] Maintain auth for artifact storage operations
- [ ] Test experiment tracking with authentication

## Testing Requirements

### 7. Unit Tests
- [ ] Test proxy forwards all required headers
- [ ] Test proxy handles missing auth headers appropriately
- [ ] Test proxy preserves custom headers
- [ ] Test error scenarios (401, 403, expired tokens)

### 8. Integration Tests
- [ ] Test with valid auth tokens
- [ ] Test with expired tokens
- [ ] Test with invalid tokens
- [ ] Test service-to-service authentication
- [ ] Verify MLflow registry operations work
- [ ] Check model serving endpoints maintain auth
- [ ] Test with both internal and external service URLs

### 9. Manual Testing
```bash
# Test proxy with auth header
curl -H "Authorization: Bearer $TOKEN" \
     -H "X-User-ID: test-user" \
     http://localhost:8001/api/v1/models

# Test MLflow through proxy
export MLFLOW_TRACKING_TOKEN=$TOKEN
python -c "import mlflow; mlflow.set_tracking_uri('http://localhost:8001/mlflow'); mlflow.list_experiments()"

# Test direct MLflow connection
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:5000/api/2.0/mlflow/experiments/list
```

## Post-Implementation Verification

### 10. Code Review Checklist
- [ ] No hardcoded credentials or tokens
- [ ] Headers are forwarded, not reconstructed
- [ ] Logging doesn't expose sensitive auth data
- [ ] Error messages don't leak auth details

### 11. Documentation Updates
- [ ] Update API documentation if endpoints changed
- [ ] Document any new auth requirements
- [ ] Update service communication diagrams
- [ ] Add examples of proper usage

### 12. Deployment Validation
- [ ] Test in development environment first
- [ ] Verify CloudWatch logs show successful auth
- [ ] Check service health endpoints
- [ ] Monitor for increased 401/403 errors
- [ ] Validate with staging environment before production

## Common Pitfalls to Avoid

### ❌ DON'T DO THIS:
```python
# Creating new headers from scratch
headers = {
    'Content-Type': 'application/json'
    # Missing Authorization!
}

# Selectively forwarding headers
headers = {
    'Content-Type': request.headers.get('Content-Type')
    # Missing other critical headers!
}

# Stripping auth headers
del headers['Authorization']  # NEVER do this!
```

### ✅ DO THIS INSTEAD:
```python
# Forward all headers by default
headers = dict(request.headers)

# If you must modify headers, preserve auth
headers = dict(request.headers)
headers['X-Custom-Header'] = 'value'  # Add without removing

# For internal service calls
headers = get_auth_headers()  # Utility function that includes auth
headers.update(dict(request.headers))  # Merge with incoming
```

## Quick Validation Script

Run this script after making proxy changes:
```bash
./scripts/validate_auth_flow.sh
```

This will:
1. Check if auth headers are preserved
2. Test MLflow connectivity
3. Validate service-to-service communication
4. Run auth-specific integration tests

## Emergency Rollback

If auth breaks in production:
1. Check recent deployments: `aws ecs list-services --cluster hokusai-development`
2. Rollback ECS service: `./scripts/rollback_service.sh hokusai-api-development`
3. Verify auth restored: `./scripts/test_health_endpoints.py`
4. Investigate root cause using CloudWatch logs

## References

- [AUTH_ARCHITECTURE.md](./AUTH_ARCHITECTURE.md) - Complete auth flow documentation
- [ONBOARDING.md](./ONBOARDING.md) - New developer auth guide
- `tests/auth/test_auth_flow.py` - Auth flow test suite
- `src/api/auth_utils.py` - Auth utility functions