# Product Requirements Document: Configure Artifact Storage

## Objectives

Enable successful model registration by configuring MLflow artifact storage to resolve the 404 errors occurring during model file uploads. This will unblock third-party developers attempting to register models with the Hokusai platform.

## Personas

- **Third-party developers**: External developers integrating their models with Hokusai who need to upload model artifacts
- **Platform engineers**: Internal team responsible for maintaining the MLflow infrastructure
- **DevOps engineers**: Team managing AWS infrastructure and proxy configurations

## Success Criteria

1. Model registration completes successfully without 404 errors on artifact upload
2. Artifact storage endpoints (`/api/2.0/mlflow-artifacts/*`) are properly routed through the proxy
3. Uploaded model artifacts are stored persistently in S3
4. Authentication works correctly for artifact uploads
5. Documentation is updated with the new configuration

## Tasks

### Infrastructure Configuration

1. Configure S3 bucket for MLflow artifact storage
   - Create or identify existing S3 bucket for model artifacts
   - Set appropriate IAM policies for read/write access
   - Configure bucket lifecycle policies if needed

2. Update MLflow server configuration
   - Add `--default-artifact-root s3://bucket-name` to MLflow server startup
   - Ensure MLflow server has necessary AWS credentials
   - Verify artifact storage is properly initialized

3. Update proxy routing configuration
   - Add routes for `/api/2.0/mlflow-artifacts/*` endpoints
   - Ensure proxy forwards artifact requests to MLflow server
   - Maintain authentication headers during forwarding

### Application Updates

4. Update service_id validation
   - Change validation to accept "platform" instead of "ml-platform"
   - Update any hardcoded service_id references in the codebase
   - Ensure backward compatibility if needed

5. Implement artifact storage error handling
   - Add proper error messages for artifact upload failures
   - Implement retry logic for transient S3 errors
   - Add logging for debugging artifact storage issues

### Testing and Verification

6. Create integration tests
   - Test full model registration flow including artifact upload
   - Verify artifacts are stored in S3
   - Test authentication flow for artifact endpoints

7. Update documentation
   - Document S3 bucket configuration requirements
   - Add troubleshooting guide for artifact storage issues
   - Update API documentation with artifact endpoints

### Deployment

8. Deploy infrastructure changes
   - Apply Terraform changes for S3 and IAM configurations
   - Update MLflow server deployment with new configuration
   - Deploy updated proxy configuration

9. Verify deployment
   - Run test_real_registration.py script to verify full flow
   - Monitor logs for any artifact storage errors
   - Confirm S3 bucket contains uploaded artifacts