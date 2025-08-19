# Fix Tasks: Model Registration Failure

## 1. Immediate Fix

1. [ ] Fix auth header forwarding in MLflow proxy
   a. [ ] Remove authorization headers from the `headers_to_remove` list in mlflow_proxy_improved.py
   b. [ ] Keep x-api-key in headers to forward to MLflow
   c. [ ] Ensure Bearer token format is preserved
   d. [ ] Update code comments to reflect correct behavior

2. [ ] Add /api/mlflow route mounting
   a. [ ] Mount proxy router at both `/mlflow` and `/api/mlflow` prefixes in main.py
   b. [ ] Ensure no route conflicts
   c. [ ] Test both route prefixes work correctly

3. [ ] Handle auth header format translation if needed
   a. [ ] Check if MLflow expects different auth format than Hokusai
   b. [ ] Add header transformation logic if required
   c. [ ] Preserve original headers for debugging

## 2. Testing Tasks

4. [ ] Write failing tests first (TDD approach)
   a. [ ] Unit test showing auth headers are currently stripped
   b. [ ] Integration test showing model registration fails
   c. [ ] Test for 404 on /api/mlflow routes
   d. [ ] Run tests to confirm they fail before fix

5. [ ] Write tests for the fix
   a. [ ] Unit test verifying auth headers are forwarded
   b. [ ] Unit test for both /mlflow and /api/mlflow routes
   c. [ ] Integration test for successful model registration
   d. [ ] Test various auth header formats (Bearer, ApiKey, X-API-Key)
   e. [ ] Test query parameter api_key fallback

6. [ ] Edge case testing
   a. [ ] Test with invalid API keys
   b. [ ] Test with missing auth headers
   c. [ ] Test with malformed requests
   d. [ ] Test timeout scenarios
   e. [ ] Test large model uploads

## 3. Validation Tasks

7. [ ] Validate fix against original bug report
   a. [ ] Test with API key: hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN
   b. [ ] Reproduce exact steps from bug report
   c. [ ] Verify all MLflow endpoints work
   d. [ ] Test model registration end-to-end

8. [ ] Regression testing
   a. [ ] Ensure auth middleware still validates properly
   b. [ ] Verify other API endpoints still work
   c. [ ] Check health endpoints remain functional
   d. [ ] Test existing model serving capabilities

9. [ ] Performance validation
   a. [ ] Measure proxy latency impact
   b. [ ] Test with concurrent requests
   c. [ ] Verify no memory leaks
   d. [ ] Check connection pooling works

## 4. Code Quality Tasks

10. [ ] Refactor proxy implementation
    a. [ ] Create configuration for headers to forward/remove
    b. [ ] Add environment variable for auth behavior
    c. [ ] Improve error handling and logging
    d. [ ] Add request/response interceptors for debugging

11. [ ] Improve code documentation
    a. [ ] Document why auth headers must be forwarded
    b. [ ] Add inline comments explaining header handling
    c. [ ] Update function docstrings
    d. [ ] Add architecture decision record (ADR)

## 5. Monitoring & Observability

12. [ ] Add comprehensive logging
    a. [ ] Log when auth headers are forwarded
    b. [ ] Log MLflow response codes
    c. [ ] Add debug mode for header inspection
    d. [ ] Track auth failures vs MLflow failures

13. [ ] Create monitoring alerts
    a. [ ] Alert on high rate of 401/403 errors
    b. [ ] Alert on MLflow connectivity issues
    c. [ ] Monitor proxy latency
    d. [ ] Track successful vs failed registrations

14. [ ] Add metrics collection
    a. [ ] Count requests by endpoint
    b. [ ] Track auth success/failure rates
    c. [ ] Measure MLflow response times
    d. [ ] Monitor model registration success rate

## 6. Documentation Tasks

15. [ ] Update API documentation
    a. [ ] Document correct MLflow tracking URI
    b. [ ] Clarify authentication requirements
    c. [ ] Add troubleshooting section
    d. [ ] Include curl examples

16. [ ] Update integration guides
    a. [ ] Update hokusai-ml-platform README
    b. [ ] Add MLflow client configuration guide
    c. [ ] Document environment variables
    d. [ ] Create migration guide for affected users

## 7. Prevention Tasks

17. [ ] Add automated tests to CI/CD
    a. [ ] Integration test for model registration in CI
    b. [ ] Add auth flow tests to deployment pipeline
    c. [ ] Create smoke tests for production
    d. [ ] Add contract tests between services

18. [ ] Improve development practices
    a. [ ] Add pre-commit hooks for auth-related changes
    b. [ ] Create checklist for proxy modifications
    c. [ ] Document auth architecture clearly
    d. [ ] Add auth flow to onboarding docs

## 8. Rollback Plan

19. [ ] Prepare rollback strategy
    a. [ ] Document current broken state for comparison
    b. [ ] Create feature flag for new auth behavior
    c. [ ] Test rollback procedure locally
    d. [ ] Document rollback commands

20. [ ] Emergency response preparation
    a. [ ] Create hotfix procedure document
    b. [ ] Identify stakeholders to notify
    c. [ ] Prepare communication template
    d. [ ] Test emergency deployment process

## Priority Order

**Critical (Do First)**:
- Tasks 1, 2, 4, 5, 7

**High (Do Second)**:
- Tasks 8, 9, 12, 13

**Medium (Do Third)**:
- Tasks 10, 11, 15, 16

**Low (Nice to Have)**:
- Tasks 6, 14, 17, 18, 19, 20

## Dependencies

- Task 4 must be completed before Task 1 (tests first)
- Task 5 depends on Task 1 completion
- Task 7 depends on Tasks 1 and 2
- Task 8 depends on Task 7 success
- Documentation (15, 16) can be done in parallel with implementation