# Product Requirements Document: Test Model Registration

## Objective
Verify that the recent fixes to the Hokusai API proxy successfully resolve third-party model registration issues by conducting comprehensive end-to-end testing with a live API key.

## Background
We recently deployed fixes to address authentication issues that prevented third-party model registration. The fixes, outlined in FIXES_APPLIED.md, include:
- Corrected auth middleware to send API key in Authorization header
- Updated MLflow server URL to production endpoint
- Added path translation for MLflow's non-standard ajax-api format

Now we need to verify these fixes work in production with real API credentials.

## User Personas
1. **Third-party Developers**: Need confirmation that model registration works with Bearer token authentication
2. **Platform Team**: Require verification that deployed fixes resolve all authentication issues
3. **QA Engineers**: Need comprehensive test results to validate the deployment

## Success Criteria
1. Successfully authenticate with live API key via Bearer token
2. Complete end-to-end model registration through Hokusai proxy
3. Verify model appears in MLflow registry
4. Confirm no 403/401 authentication errors occur
5. Document any remaining issues or edge cases
6. Provide clear pass/fail status for production deployment

## Technical Requirements

### Test Execution Plan
1. Obtain live API key from user for testing
2. Run test_real_registration.py with production credentials
3. Execute additional verification scripts if needed
4. Document all test results and outputs
5. Identify any remaining issues or failures

### Test Coverage
- **Authentication**: Verify API key acceptance by auth service
- **MLflow Proxy**: Test connectivity through proxy endpoint
- **Model Registration**: Attempt full end-to-end registration
- **Error Handling**: Capture and analyze any failures
- **Performance**: Note response times and latency

### Verification Scripts
- Primary: `test_real_registration.py` - Comprehensive registration test
- Quick health check: `verify_api_proxy.py`
- Bearer token test: `test_bearer_auth.py`
- Direct auth test: `test_auth_service.py`

### Expected Outputs
Successful execution should produce:
- API key validation confirmation
- MLflow client connection success
- Model training and logging completion
- Model registration with name and version
- Final success message with no errors

## Dependencies
- Live API key from user
- Access to production environment
- Python environment with required packages
- Network access to Hokusai services

## Deliverables
1. Complete test execution report
2. Pass/fail status for each test component
3. Documentation of any issues found
4. Recommendations for fixes if failures occur
5. Confirmation that third-party registration works