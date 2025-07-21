# Product Requirements Document: Test Model Registration

## Objectives

1. Verify that third-party model registration is working correctly with the recent fixes applied to the authentication system
2. Execute comprehensive testing with a valid API key to confirm all endpoints are functional
3. Diagnose and document any remaining issues preventing successful model registration
4. Ensure the model registration workflow functions end-to-end for external users

## Personas

- **Third-Party Developer**: External developer attempting to register ML models with Hokusai platform using API keys
- **Platform Engineer**: Responsible for maintaining and fixing the authentication and registration infrastructure
- **QA Engineer**: Verifying that fixes work as expected and documenting test results

## Success Criteria

1. **Authentication Success**: API key is validated successfully across all required services
2. **MLflow Connectivity**: Client can connect to MLflow through the proxy endpoint without errors
3. **Model Registration**: Complete model training, logging, and registration workflow executes successfully
4. **Comprehensive Testing**: All test scripts pass with valid API key:
   - test_real_registration.py
   - verify_api_proxy.py
   - test_bearer_auth.py
   - test_auth_service.py
5. **Documentation**: Clear report on current status and any remaining issues

## Tasks

### 1. Environment Setup and API Key Validation
- Obtain valid API key from user for testing
- Set HOKUSAI_API_KEY environment variable
- Verify API key format matches expected pattern (hk_live_*)

### 2. Execute Primary Registration Test
- Run test_real_registration.py with provided API key
- Capture detailed output including all HTTP requests/responses
- Document specific error messages and failure points

### 3. Run Diagnostic Test Suite
- Execute verify_api_proxy.py to check proxy health
- Run test_bearer_auth.py to verify Bearer token authentication
- Execute test_auth_service.py to test direct auth service validation
- Run investigate_mlflow.py for comprehensive endpoint testing

### 4. Analyze Test Results
- Compare results against expected success outputs
- Identify specific failure points in the authentication flow
- Determine if failures are due to:
  - Invalid/expired API key
  - Service configuration issues
  - Deployment problems
  - Code bugs

### 5. Implement Fixes (if needed)
- If API key is valid but tests fail, identify root cause
- Implement necessary code fixes
- Update configuration if deployment issues found
- Ensure fixes don't break existing functionality

### 6. Verify Fix Effectiveness
- Re-run all test scripts after implementing fixes
- Confirm all tests pass with green checkmarks
- Verify model appears in MLflow registry

### 7. Update Documentation
- Document test results in structured format
- Update FINAL_TEST_REPORT.md with current status
- Create clear instructions for third-party developers
- Document any workarounds needed

## Technical Requirements

- Python environment with hokusai-ml-platform package installed
- Valid Hokusai API key with model registration permissions
- Access to production endpoints:
  - https://api.hokus.ai/mlflow/
  - https://auth.hokus.ai/validate
  - https://registry.hokus.ai/mlflow/

## Expected Outcomes

Upon successful completion:
- Third-party developers can register models using standard MLflow client
- Authentication works seamlessly with Bearer tokens
- All test scripts show passing results
- Clear documentation exists for the registration process
- Any remaining issues are clearly identified with remediation plans