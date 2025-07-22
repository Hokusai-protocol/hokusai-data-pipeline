# Implementation Tasks: Configure Artifact Storage

## 1. [x] Investigate Current Infrastructure
   a. [x] Review existing Terraform configuration for MLflow deployment
   b. [x] Check if S3 bucket already exists for artifacts
   c. [x] Document current proxy routing configuration
   d. [x] Identify MLflow server deployment configuration

## 2. [x] Configure S3 Bucket for Artifacts
   a. [x] Create new S3 bucket or identify existing one for MLflow artifacts
   b. [x] Write Terraform configuration for S3 bucket with proper naming
   c. [x] Configure bucket policies for MLflow server access
   d. [x] Set up lifecycle rules for artifact retention
   e. [x] Enable versioning and encryption on bucket

## 3. [x] Update IAM Policies
   a. [x] Create IAM role for MLflow server with S3 access
   b. [x] Write policy document allowing read/write to artifact bucket
   c. [x] Update ECS task role to include S3 permissions
   d. [x] Test IAM permissions with AWS CLI

## 4. [x] Modify MLflow Server Configuration
   a. [x] Locate MLflow server startup script or configuration
   b. [x] Add `--default-artifact-root s3://hokusai-mlflow-artifacts` parameter
   c. [x] Configure AWS credentials for MLflow server
   d. [x] Update environment variables for S3 access
   e. [x] Create health check for artifact storage

## 5. [x] Update Proxy Routing (Dependent on Infrastructure)
   a. [x] Review current nginx/proxy configuration
   b. [x] Add location block for `/api/2.0/mlflow-artifacts/*`
   c. [x] Configure proper header forwarding for authentication
   d. [x] Test proxy configuration syntax
   e. [x] Document new routing rules

## 6. [x] Fix service_id Validation
   a. [x] Search codebase for "ml-platform" references
   b. [x] Update validation to accept "platform" service_id
   c. [x] Add migration logic for backward compatibility
   d. [x] Update any hardcoded service_id checks

## 7. [x] Implement Error Handling
   a. [x] Add try-catch blocks for artifact upload operations
   b. [x] Implement exponential backoff for S3 retries
   c. [x] Create custom exception classes for artifact errors
   d. [x] Add detailed logging for debugging
   e. [x] Create error response formatting

## 8. [x] Write Integration Tests (Dependent on Error Handling)
   a. [x] Create test for full model registration with artifacts
   b. [x] Write test for artifact upload to S3
   c. [x] Test authentication flow for artifact endpoints
   d. [x] Add test for error scenarios (S3 down, auth failure)
   e. [x] Create fixture data for model artifacts

## 9. [x] Update Documentation (Dependent on Testing)
   a. [x] Document S3 bucket configuration in README
   b. [x] Create troubleshooting guide for artifact errors
   c. [x] Update API documentation with artifact endpoints
   d. [x] Add example code for model registration with artifacts
   e. [x] Document required AWS permissions

## 10. [ ] Deploy Infrastructure Changes
   a. [ ] Review and approve Terraform changes
   b. [ ] Plan Terraform deployment
   c. [ ] Apply S3 and IAM changes
   d. [ ] Update MLflow server with new configuration
   e. [ ] Deploy updated proxy configuration
   f. [ ] Verify all services are healthy

## 11. [ ] Verify Deployment (Dependent on Deployment)
   a. [ ] Run test_real_registration.py with real API key
   b. [ ] Check S3 bucket for uploaded artifacts
   c. [ ] Monitor CloudWatch logs for errors
   d. [ ] Test artifact download functionality
   e. [ ] Document any issues found