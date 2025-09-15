# Fix Tasks: Problems Registering Model

## Priority: CRITICAL - Blocking Core Platform Functionality

## 1. Immediate Fix

### Authorization Implementation
1. [ ] Create scope checking utility function in `src/middleware/auth.py`
   a. [ ] Add `check_scope_for_operation()` method
   b. [ ] Map MLflow write endpoints to required scopes
   c. [ ] Return bool indicating authorization status

2. [ ] Modify `APIKeyAuthMiddleware.dispatch()` to check scopes
   a. [ ] Detect if request is for MLflow write operation
   b. [ ] Check if user has `model:write` or `mlflow:write` scope
   c. [ ] Return 403 with clear error message if unauthorized
   d. [ ] Add audit logging for authorization decisions

3. [ ] Create permission decorator for route-level authorization
   a. [ ] Implement `@require_scope("model:write")` decorator
   b. [ ] Apply to MLflow proxy write endpoints
   c. [ ] Ensure decorator works with async routes

## 2. Testing Tasks

### Unit Tests (Write First - TDD)
4. [ ] Write failing tests for authorization checks
   a. [ ] Test read-only key attempting model registration (should fail)
   b. [ ] Test write-enabled key attempting model registration (should pass)
   c. [ ] Test various MLflow write endpoints with different scopes
   d. [ ] Test scope validation edge cases (empty scopes, null scopes)

5. [ ] Write middleware unit tests
   a. [ ] Test scope extraction from auth service response
   b. [ ] Test scope checking logic for different operations
   c. [ ] Test error responses for unauthorized requests
   d. [ ] Test caching behavior with different scopes

### Integration Tests
6. [ ] Create end-to-end authorization tests
   a. [ ] Test complete flow: API key → auth service → scope check → MLflow
   b. [ ] Test with real auth service (or mock)
   c. [ ] Test MLflow operations with different permission levels
   d. [ ] Test rate limiting doesn't interfere with authorization

## 3. Validation Tasks

7. [ ] Validate fix against original bug report
   a. [ ] Test with API key `hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN`
   b. [ ] Verify read operations still work
   c. [ ] Verify write operations return proper 403 with explanation
   d. [ ] Test with properly scoped key to ensure writes work

8. [ ] Regression testing
   a. [ ] Ensure existing authenticated operations still work
   b. [ ] Verify performance impact is minimal (<5ms added latency)
   c. [ ] Test backward compatibility with existing API keys
   d. [ ] Validate caching still functions correctly

## 4. Code Quality Tasks

9. [ ] Refactor for maintainability
   a. [ ] Extract scope definitions to configuration file
   b. [ ] Create enum for standard scopes
   c. [ ] Add type hints for all new functions
   d. [ ] Ensure consistent error response format

10. [ ] Improve error handling
    a. [ ] Add specific error codes for different authorization failures
    b. [ ] Include required scope in error message
    c. [ ] Provide helpful suggestions in error responses
    d. [ ] Ensure error messages don't leak sensitive information

## 5. Monitoring & Observability

11. [ ] Add comprehensive logging
    a. [ ] Log all authorization decisions (granted/denied)
    b. [ ] Include user_id, key_id, requested_scope, operation
    c. [ ] Add CloudWatch metric for authorization failures
    d. [ ] Track authorization latency

12. [ ] Create monitoring dashboard
    a. [ ] Authorization success/failure rates by endpoint
    b. [ ] Most common unauthorized operations
    c. [ ] Alert on spike in 403 errors
    d. [ ] Track scope usage patterns

## 6. Documentation Tasks

13. [ ] Update API documentation
    a. [ ] Document required scopes for each endpoint
    b. [ ] Add authorization section to API guide
    c. [ ] Update error response documentation
    d. [ ] Add examples of proper API key usage

14. [ ] Create troubleshooting guide
    a. [ ] Common authorization errors and solutions
    b. [ ] How to check API key scopes
    c. [ ] How to request additional permissions
    d. [ ] FAQ for model registration issues

## 7. Prevention Tasks

15. [ ] Implement development safeguards
    a. [ ] Add pre-commit hook to check for authorization on new endpoints
    b. [ ] Create unit test template for authorization testing
    c. [ ] Add authorization checklist to PR template
    d. [ ] Document authorization patterns in developer guide

16. [ ] Improve API key generation
    a. [ ] Add clear scope selection in key creation UI/CLI
    b. [ ] Warn when creating keys without write permissions
    c. [ ] Provide scope recommendations based on use case
    d. [ ] Add scope validation in key creation endpoint

## 8. Rollback Plan

17. [ ] Prepare safe rollback strategy
    a. [ ] Add feature flag for authorization checking
    b. [ ] Document how to disable authorization temporarily
    c. [ ] Create script to grant write permissions to affected keys
    d. [ ] Prepare communication template for users if rollback needed

## Dependencies and Order

**Phase 1 (Immediate):**
- Tasks 4-5 (Write failing tests first)
- Tasks 1-3 (Implement fix)
- Task 7 (Validate fix)

**Phase 2 (Before Deploy):**
- Task 6 (Integration tests)
- Task 8 (Regression testing)
- Tasks 11-12 (Monitoring)
- Task 17 (Rollback plan)

**Phase 3 (Post-Deploy):**
- Tasks 9-10 (Code quality)
- Tasks 13-14 (Documentation)
- Tasks 15-16 (Prevention)

## Success Criteria

- [ ] Read-only API keys receive clear 403 errors on write attempts
- [ ] Write-enabled API keys can successfully register models
- [ ] No regression in existing functionality
- [ ] Authorization adds <5ms latency
- [ ] All tests pass
- [ ] Documentation updated
- [ ] Monitoring in place