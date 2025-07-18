# Product Requirements Document: Test Model Registration

## Objectives

Verify and ensure that third-party model registration through the Hokusai platform Auth service is fully functional by running comprehensive tests using the `test_real_registration.py` script. This includes confirming that recent Auth service changes have resolved authentication issues preventing successful model registration.

## Personas

**Third-party Developer**: External developer attempting to register machine learning models with the Hokusai platform using API keys for authentication.

**Platform Administrator**: Hokusai team member responsible for verifying platform functionality and ensuring third-party integrations work correctly.

## Success Criteria

1. The `test_real_registration.py` script executes successfully with a valid API key
2. Authentication passes without 403/401 errors
3. MLflow proxy endpoint accepts Bearer token authentication
4. Model training and logging completes successfully
5. Model registration to MLflow succeeds
6. Registered model can be retrieved and verified
7. All diagnostic outputs show green checkmarks (✓) indicating success

## Tasks

### 1. Environment Setup
- Obtain a valid live API key from the user
- Set up the HOKUSAI_API_KEY environment variable
- Verify Python dependencies are installed (mlflow, sklearn, pandas, numpy)

### 2. Execute Primary Test Script
- Run `python test_real_registration.py` with the provided API key
- Monitor output for authentication success indicators
- Document any errors or failures encountered

### 3. Run Additional Verification Scripts
- Execute `python verify_api_proxy.py` for quick health check
- Execute `python test_bearer_auth.py` for bearer token verification
- Execute `python test_auth_service.py` for direct auth service testing
- Document results from each verification script

### 4. Diagnose Issues (if any)
- If authentication fails, identify specific error codes (401, 403, 404)
- Check proxy endpoint connectivity
- Verify MLflow backend configuration
- Test fallback options (SDK registration, direct MLflow access)

### 5. Document Results
- Create a comprehensive test report with all findings
- Include successful output examples
- Document any remaining issues or workarounds needed
- Provide recommendations for any discovered problems

### 6. Verify Expected Outputs
Confirm the test produces the expected success indicators:
- API Key validation (✓ API Key: hk_live_ch...cOWL)
- Proxy endpoint confirmation (✓ Using proxy endpoint)
- MLflow client connection (✓ MLflow client connected! Found X experiments)
- Model training completion (✓ Model trained with accuracy: X.XXX)
- Model logging success (✓ Model logged! Run ID: XXXXX)
- Model registration success (✓ Model registered!)
- Final success message (✅ SUCCESS: Third-party model registration completed!)