# Fix Tasks: Endpoints Inaccessible

## Priority 1: Immediate Fix (Get Service Running)

### Task 1: Verify Docker Build Configuration
- [ ] Check Dockerfile.api for missing COPY statements
- [ ] Ensure all src/ directories are included
- [ ] Verify .dockerignore isn't excluding needed files
- [ ] Check if multi-stage build is copying all artifacts

### Task 2: Fix Import Issues
- [ ] Review src/services/__init__.py imports
- [ ] Check if all imported modules exist in repo
- [ ] Verify no circular dependencies
- [ ] Add error handling for optional imports

### Task 3: Update Dependencies
- [ ] Check requirements.txt for missing packages
- [ ] Verify all service dependencies are listed
- [ ] Test dependency installation in clean environment
- [ ] Pin versions to avoid conflicts

### Task 4: Rebuild and Deploy
- [ ] Build new Docker image locally
- [ ] Test container startup locally
- [ ] Push to ECR
- [ ] Update ECS service with new image
- [ ] Monitor deployment and logs

## Priority 2: Testing & Validation

### Task 5: Add Startup Tests
- [ ] Create test_imports.py to validate all imports
- [ ] Add container startup test to CI/CD
- [ ] Implement smoke tests for deployed services
- [ ] Add health check that validates imports

### Task 6: Local Testing
- [ ] Run API service locally with Docker
- [ ] Test all import paths
- [ ] Verify all endpoints respond
- [ ] Check integration with other services

## Priority 3: Monitoring & Prevention

### Task 7: Improve Health Checks
- [ ] Add startup validation to health endpoint
- [ ] Include import checks in health response
- [ ] Set appropriate health check intervals
- [ ] Configure ALB health check timeouts

### Task 8: Add Monitoring
- [ ] Create CloudWatch alarm for startup failures
- [ ] Add metrics for service restarts
- [ ] Implement log aggregation for errors
- [ ] Set up alerts for import errors

### Task 9: Documentation Updates
- [ ] Document Docker build process
- [ ] Create troubleshooting guide
- [ ] Update deployment procedures
- [ ] Add rollback instructions

## Implementation Order

1. **Quick Fix Path** (30 minutes):
   - Check Dockerfile.api
   - Identify missing files/dependencies
   - Rebuild and redeploy

2. **Validation Path** (1 hour):
   - Test locally
   - Verify fix works
   - Deploy to development

3. **Prevention Path** (2 hours):
   - Add tests
   - Improve monitoring
   - Update documentation

## Specific Code Changes Needed

### 1. Dockerfile.api
```dockerfile
# Ensure all source directories are copied
COPY src/ /app/src/
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
```

### 2. src/services/__init__.py
```python
# Add error handling for imports
try:
    from .model_registry import HokusaiModelRegistry
except ImportError as e:
    print(f"Warning: Could not import HokusaiModelRegistry: {e}")
    HokusaiModelRegistry = None
```

### 3. Health Check Enhancement
```python
# In src/api/routes/health.py
def check_imports():
    """Validate all required imports are available."""
    try:
        import src.services.model_registry
        import src.services.dspy_pipeline_executor
        return True, "All imports successful"
    except ImportError as e:
        return False, f"Import failed: {str(e)}"
```

### 4. CI/CD Test
```yaml
# In .github/workflows/test.yml or similar
- name: Test Docker startup
  run: |
    docker build -f Dockerfile.api -t test-api .
    docker run --rm test-api python -c "from src.api.main import app; print('Import successful')"
```

## Success Criteria

### Immediate Success
- [ ] API service starts without errors
- [ ] Health checks pass
- [ ] All endpoints accessible
- [ ] No import errors in logs

### Long-term Success
- [ ] Zero startup failures in 30 days
- [ ] All tests passing in CI/CD
- [ ] Monitoring alerts working
- [ ] Documentation complete

## Rollback Plan

If fix causes other issues:
1. Revert to previous Docker image tag
2. Update ECS service to use previous version
3. Document failure mode
4. Investigate alternative fix

## Notes

- Current working branch: bugfix/endpoints-inaccessible
- ECS Cluster: hokusai-development
- Service: hokusai-api-development
- Critical path: Fix imports → Rebuild → Deploy → Verify