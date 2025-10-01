# Fix Tasks: API ID 21 Connection 405 Error

## Overview

**Recommended Solution**: Remove endpoint-specific authentication and rely on middleware-based auth (Option 2 from root-cause.md)

**Priority**: High - Blocking third-party integration

**Estimated Time**: 4-6 hours (including testing)

---

## 1. Immediate Fix (Priority: Critical)

### 1.1 Remove Duplicate Authentication from Endpoint

- [ ] **Remove manual auth check from `predict()` endpoint**
  - a. [ ] Open `src/api/endpoints/model_serving.py`
  - b. [ ] Remove `authorization: Optional[str] = Header(None)` parameter (line 379)
  - c. [ ] Add `auth: dict[str, Any] = Depends(require_auth)` parameter instead
  - d. [ ] Remove lines 385-395 (manual authorization check)
  - e. [ ] Add `from src.middleware.auth import require_auth` to imports
  - f. [ ] Update logging to use `auth['user_id']` instead of API key prefix

### 1.2 Update Other Endpoints in Same Router

- [ ] **Apply same auth pattern to `get_model_info()` endpoint**
  - a. [ ] Line 354-374: Replace manual auth with `Depends(require_auth)`
  - b. [ ] Remove authorization parameter
  - c. [ ] Remove manual Bearer token check

- [ ] **Apply same auth pattern to `check_model_health()` endpoint**
  - a. [ ] Line 426-448: Replace manual auth with `Depends(require_auth)`
  - b. [ ] Remove authorization parameter
  - c. [ ] Remove manual Bearer token check

### 1.3 Update Logging

- [ ] **Enhance logging for debugging**
  - a. [ ] Add user_id to prediction request logs
  - b. [ ] Log API key ID for tracking
  - c. [ ] Add request ID for tracing
  - d. [ ] Log model_id and endpoint being accessed

### 1.4 Configuration Verification

- [ ] **Verify auth service configuration**
  - a. [ ] Check `HOKUSAI_AUTH_SERVICE_URL` environment variable
  - b. [ ] Verify auth service is reachable from ECS tasks
  - c. [ ] Test auth service `/api/v1/keys/validate` endpoint
  - d. [ ] Verify Redis cache is working for auth caching

---

## 2. Testing Tasks (Priority: Critical)

### 2.1 Unit Tests - Write First (TDD)

- [ ] **Create test file `tests/unit/test_model_serving_auth.py`**
  - a. [ ] Test valid API key authentication
  - b. [ ] Test invalid API key rejection
  - c. [ ] Test missing API key rejection
  - d. [ ] Test expired API key handling
  - e. [ ] Test API key with insufficient scopes

### 2.2 Integration Tests

- [ ] **Create test file `tests/integration/test_model_21_prediction_api.py`**
  - a. [ ] Test full prediction flow with valid auth
  - b. [ ] Test prediction with actual Model 21
  - c. [ ] Test error handling when model not found
  - d. [ ] Test error handling when HuggingFace unavailable
  - e. [ ] Test caching behavior

### 2.3 Auth Middleware Tests

- [ ] **Add tests for middleware auth integration**
  - a. [ ] Test that middleware validates API keys
  - b. [ ] Test that request.state is populated correctly
  - c. [ ] Test that excluded paths bypass auth
  - d. [ ] Test that model serving endpoints require auth

### 2.4 Manual Testing Checklist

- [ ] **Test against actual deployment**
  - a. [ ] curl test with valid API key
  - b. [ ] curl test with invalid API key
  - c. [ ] curl test with missing Authorization header
  - d. [ ] curl test with malformed Authorization header
  - e. [ ] Test with third-party's actual API key

---

## 3. Validation Tasks (Priority: High)

### 3.1 Original Bug Reproduction

- [ ] **Reproduce original 405 error**
  - a. [ ] Use same request as third-party client
  - b. [ ] Verify we can reproduce the 405 error
  - c. [ ] Document exact steps to reproduce

### 3.2 Fix Validation

- [ ] **Verify fix resolves the issue**
  - a. [ ] Deploy fix to development environment
  - b. [ ] Retry third-party request pattern
  - c. [ ] Verify 200 response with valid predictions
  - d. [ ] Verify appropriate error responses for invalid requests

### 3.3 Regression Testing

- [ ] **Test other model serving endpoints**
  - a. [ ] Test `/api/v1/models/21/info` still works
  - b. [ ] Test `/api/v1/models/21/health` still works
  - c. [ ] Test any other models if they exist

### 3.4 Performance Validation

- [ ] **Verify no performance degradation**
  - a. [ ] Measure auth middleware overhead
  - b. [ ] Compare response times before/after
  - c. [ ] Test Redis caching is working
  - d. [ ] Verify auth service timeout handling

### 3.5 Staging Environment Validation

- [ ] **Full end-to-end test in staging**
  - a. [ ] Deploy to staging environment
  - b. [ ] Test with staging API keys
  - c. [ ] Verify logs are clean
  - d. [ ] Check CloudWatch metrics
  - e. [ ] Get stakeholder approval

---

## 4. Code Quality Tasks (Priority: Medium)

### 4.1 Code Organization

- [ ] **Standardize authentication pattern**
  - a. [ ] Review all API endpoints for consistent auth usage
  - b. [ ] Create auth helper utilities if needed
  - c. [ ] Document standard auth pattern in CONTRIBUTING.md

### 4.2 Error Messages

- [ ] **Improve error message clarity**
  - a. [ ] Return descriptive 401 errors
  - b. [ ] Include hints for fixing auth issues
  - c. [ ] Add error codes for categorization
  - d. [ ] Document all possible error responses

### 4.3 Type Safety

- [ ] **Enhance type annotations**
  - a. [ ] Ensure all auth functions have proper types
  - b. [ ] Add Pydantic models for auth responses
  - c. [ ] Use mypy to verify type correctness

### 4.4 Code Comments

- [ ] **Add explanatory comments**
  - a. [ ] Document why middleware auth is used
  - b. [ ] Explain auth flow in module docstring
  - c. [ ] Add comments for complex auth logic

---

## 5. Monitoring & Observability (Priority: High)

### 5.1 Logging Enhancements

- [ ] **Add structured logging**
  - a. [ ] Log all prediction requests with user context
  - b. [ ] Log auth failures with reason codes
  - c. [ ] Log API key usage for billing/tracking
  - d. [ ] Add correlation IDs for request tracing

### 5.2 CloudWatch Alarms

- [ ] **Create alarms for auth failures**
  - a. [ ] Alarm for auth service unavailable
  - b. [ ] Alarm for high rate of 401 errors
  - c. [ ] Alarm for high rate of 403 errors
  - d. [ ] Alarm for auth service timeout

### 5.3 Metrics

- [ ] **Add custom metrics**
  - a. [ ] Track prediction requests per model
  - b. [ ] Track auth success/failure rates
  - c. [ ] Track API key usage by key_id
  - d. [ ] Track model serving latency

### 5.4 Health Checks

- [ ] **Add comprehensive health checks**
  - a. [ ] Add auth service connectivity check
  - b. [ ] Add HuggingFace connectivity check
  - c. [ ] Add model availability check
  - d. [ ] Add Redis cache health check

### 5.5 Dashboard

- [ ] **Create CloudWatch dashboard**
  - a. [ ] Panel for API request volume
  - b. [ ] Panel for auth success/failure rates
  - c. [ ] Panel for error rates by type
  - d. [ ] Panel for p50/p95/p99 latency

---

## 6. Documentation Tasks (Priority: Medium)

### 6.1 API Documentation

- [ ] **Update MODEL_21_VERIFICATION_REPORT.md**
  - a. [ ] Document auth requirements clearly
  - b. [ ] Add troubleshooting section
  - c. [ ] Include example error responses
  - d. [ ] Document rate limits and quotas

### 6.2 Internal Documentation

- [ ] **Create troubleshooting guide**
  - a. [ ] Document common auth errors
  - b. [ ] Add debugging steps
  - c. [ ] Include log analysis examples
  - d. [ ] Document escalation path

### 6.3 Code Documentation

- [ ] **Update inline documentation**
  - a. [ ] Add docstrings to auth functions
  - b. [ ] Document auth middleware configuration
  - c. [ ] Explain excluded paths logic
  - d. [ ] Document security considerations

### 6.4 Architecture Documentation

- [ ] **Update architecture docs**
  - a. [ ] Document auth flow diagram
  - b. [ ] Explain middleware pattern
  - c. [ ] Document service dependencies
  - d. [ ] Add sequence diagrams for auth

### 6.5 External Documentation

- [ ] **Update docs.hokus.ai**
  - a. [ ] Add API authentication guide
  - b. [ ] Document all endpoints
  - c. [ ] Provide working code examples
  - d. [ ] Add Postman collection

---

## 7. Prevention Tasks (Priority: Medium)

### 7.1 Code Standards

- [ ] **Establish auth patterns**
  - a. [ ] Document standard auth approach
  - b. [ ] Create code templates for new endpoints
  - c. [ ] Add to code review checklist
  - d. [ ] Update team wiki

### 7.2 Testing Standards

- [ ] **Require auth tests**
  - a. [ ] Add auth test template
  - b. [ ] Require tests for all new endpoints
  - c. [ ] Add to CI/CD pipeline
  - d. [ ] Gate deployments on test passage

### 7.3 Monitoring Standards

- [ ] **Standardize observability**
  - a. [ ] Require logging for all endpoints
  - b. [ ] Require metrics for auth operations
  - c. [ ] Require health checks for dependencies
  - d. [ ] Create observability checklist

### 7.4 Pre-commit Checks

- [ ] **Add automated checks**
  - a. [ ] Lint for consistent auth patterns
  - b. [ ] Check for missing auth requirements
  - c. [ ] Verify all endpoints have tests
  - d. [ ] Run type checking with mypy

### 7.5 Knowledge Sharing

- [ ] **Team education**
  - a. [ ] Schedule postmortem review
  - b. [ ] Document lessons learned
  - c. [ ] Present findings to team
  - d. [ ] Update onboarding materials

---

## 8. Rollback Plan (Priority: Critical)

### 8.1 Rollback Preparation

- [ ] **Document rollback procedure**
  - a. [ ] Identify rollback commit hash
  - b. [ ] Document ECS rollback command
  - c. [ ] Create rollback script
  - d. [ ] Test rollback in staging

### 8.2 Feature Flags (Optional)

- [ ] **Consider feature flag for auth changes**
  - a. [ ] Implement feature flag if needed
  - b. [ ] Test with flag on/off
  - c. [ ] Document flag usage
  - d. [ ] Plan flag removal timeline

### 8.3 Monitoring Rollback

- [ ] **Monitor post-deployment**
  - a. [ ] Watch CloudWatch logs for errors
  - b. [ ] Monitor auth success rates
  - c. [ ] Check for new 40x errors
  - d. [ ] Verify third-party can connect

### 8.4 Rollback Triggers

- [ ] **Define rollback conditions**
  - a. [ ] Auth failure rate > 5%
  - b. [ ] New 500 errors appearing
  - c. [ ] Third-party reports issues
  - d. [ ] Performance degradation > 20%

---

## Implementation Order

### Phase 1: Critical Path (Day 1)
1. Fix implementation (Tasks 1.1-1.4)
2. Unit tests (Task 2.1)
3. Basic validation (Task 3.1-3.2)
4. Deploy to staging (Task 3.5)

### Phase 2: Testing & Validation (Day 2)
5. Integration tests (Task 2.2-2.3)
6. Full validation suite (Task 3.3-3.4)
7. Manual testing (Task 2.4)
8. Monitor staging (Task 8.3)

### Phase 3: Monitoring & Docs (Day 3)
9. Monitoring setup (Tasks 5.1-5.5)
10. Documentation updates (Tasks 6.1-6.5)
11. Prevention measures (Tasks 7.1-7.5)

### Phase 4: Production Deployment (Day 4)
12. Production deployment with careful monitoring
13. Rollback plan ready (Task 8)
14. Stakeholder communication
15. Close Linear ticket

---

## Success Criteria

- [ ] Third-party can successfully call `/api/v1/models/21/predict`
- [ ] All tests pass (unit, integration, manual)
- [ ] No regression in existing functionality
- [ ] CloudWatch logs show successful auth and predictions
- [ ] Auth service integration working correctly
- [ ] Performance within acceptable limits
- [ ] Documentation updated
- [ ] Stakeholder approval received

---

## Risk Mitigation

### Risk 1: Auth Service Integration Issues
- **Mitigation**: Test auth service thoroughly in staging
- **Fallback**: Keep endpoint-specific auth as backup (feature flag)

### Risk 2: Breaking Other Endpoints
- **Mitigation**: Comprehensive regression testing
- **Fallback**: Quick rollback procedure ready

### Risk 3: Performance Degradation
- **Mitigation**: Load test before production
- **Fallback**: Redis caching optimization

### Risk 4: Third-Party Still Can't Connect
- **Mitigation**: Test with their exact API key in staging
- **Fallback**: Work with third-party to debug their client

---

## Notes

- Coordinate with third-party for testing in staging
- Schedule deployment during low-traffic window
- Have oncall engineer ready for monitoring
- Prepare communication for stakeholders
- Update Linear ticket with progress

