# Tasks: Fix Database Authentication

## 1. [ ] Remove Hardcoded Database Password
   a. [ ] Update src/api/utils/config.py to remove hardcoded "postgres" password
   b. [ ] Make database_password field required from environment variables
   c. [ ] Add validation to ensure password is not using default value

## 2. [ ] Implement AWS Secrets Manager Integration
   a. [ ] Add boto3 dependency to requirements.txt if not present
   b. [ ] Create secrets manager client in config.py
   c. [ ] Implement fallback to fetch password from Secrets Manager if env var is missing
   d. [ ] Add proper error handling for Secrets Manager access

## 3. [ ] Fix Environment Variable Handling
   a. [ ] Verify ECS task definition includes DATABASE_PASSWORD from Secrets Manager
   b. [ ] Update effective_database_password property to require password
   c. [ ] Add logging to track credential source without exposing values
   d. [ ] Ensure both DB_PASSWORD and DATABASE_PASSWORD are supported

## 4. [ ] Validate Health Check Implementation
   a. [ ] Review src/api/routes/health.py database connection code
   b. [ ] Ensure health check uses settings.postgres_uri consistently
   c. [ ] Verify no hardcoded credentials in health check
   d. [ ] Test health check with correct credentials

## 5. [ ] Update Deployment Configuration (Dependent on Tasks 1-3)
   a. [ ] Check infrastructure/terraform/ecs-task-update.tf for proper secret injection
   b. [ ] Verify APP_SECRETS_ARN is correctly referenced
   c. [ ] Ensure DATABASE_PASSWORD is mapped from Secrets Manager
   d. [ ] Update task definition version if needed

## 6. [ ] Create Database Connection Test Script
   a. [ ] Write standalone Python script to test database connectivity
   b. [ ] Test with environment variables
   c. [ ] Test with AWS Secrets Manager integration
   d. [ ] Include connection diagnostics and error reporting

## 7. [ ] Write and Implement Tests (Dependent on Tasks 1-4)
   a. [ ] Unit tests for configuration with mocked environment variables
   b. [ ] Unit tests for Secrets Manager integration
   c. [ ] Integration test for database connection
   d. [ ] Health check endpoint tests
   e. [ ] End-to-end test with proper credentials

## 8. [ ] Add Error Handling and Logging
   a. [ ] Add startup validation for required credentials
   b. [ ] Implement clear error messages for missing credentials
   c. [ ] Add audit logging for credential source
   d. [ ] Ensure passwords are never logged

## 9. [ ] Documentation Updates (Dependent on all tasks)
   a. [ ] Update README.md with environment variable requirements
   b. [ ] Document AWS Secrets Manager setup process
   c. [ ] Add troubleshooting guide for authentication issues
   d. [ ] Create deployment checklist for credentials