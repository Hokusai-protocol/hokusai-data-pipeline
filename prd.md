# Product Requirements Document: Test Model Registration Again2

## Objective
Complete the deployment of MLflow container with artifact storage support and verify that third-party model registration works end-to-end. This is the final step to resolve persistent model registration issues.

## Background
Testing has confirmed that authentication and MLflow connectivity are working correctly, but model registration fails at the artifact upload stage with 404 errors on `/api/2.0/mlflow-artifacts/` endpoints. The root cause is that the MLflow container in ECS is using an old image without the `--serve-artifacts` flag. While the Dockerfile has been updated in the repository, the container hasn't been rebuilt and deployed.

## Success Criteria
1. MLflow artifact storage endpoints respond successfully (not 404)
2. Third-party model registration completes without errors
3. Verification script `test_model_registration_simple.py` passes all tests
4. Model artifacts are successfully stored and retrievable

## Implementation Tasks

### 1. Deploy MLflow Container
Deploy the updated MLflow container with artifact storage support using the prepared deployment script `deploy_mlflow_container.sh`.

### 2. Verify MLflow Deployment
Confirm the MLflow service is running with artifact storage enabled by:
- Checking container status in ECS
- Testing artifact endpoint availability
- Running `verify_mlflow_deployment.sh`

### 3. Test Model Registration
Execute comprehensive model registration tests with a valid API key:
- Run `test_model_registration_simple.py`
- Verify authentication works correctly
- Confirm artifact upload succeeds
- Ensure model registration completes

### 4. Document Results
Record test outcomes including:
- Any errors encountered
- Performance metrics
- Verification steps completed
- Recommendations for production deployment

## Technical Requirements
- Access to AWS ECS for container deployment
- Valid Hokusai API key for testing
- Python environment with test dependencies
- Network access to registry.hokus.ai

## Dependencies
- MLflow container image with `--serve-artifacts` flag
- S3 bucket for artifact storage (already configured)
- IAM roles with appropriate permissions (already configured)
- Authentication service (already operational)

## Verification Scripts
- `deploy_mlflow_container.sh` - Deploys MLflow with artifact storage
- `verify_mlflow_deployment.sh` - Verifies deployment status
- `test_model_registration_simple.py` - Tests model registration
- `test_real_registration.py` - Comprehensive end-to-end test