# Implementation Tasks: Update Proxy Routing

## 1. Configure ECS Service Discovery for MLflow
- [x] Review current ECS service configuration
   a. [x] Check if service discovery is already enabled
   b. [x] Identify the MLflow service name and namespace
   c. [x] Document the internal DNS name for MLflow service
- [x] Update Terraform configuration to enable service discovery if not present
   a. [x] Add AWS Cloud Map namespace configuration
   b. [x] Configure service discovery for MLflow service
   c. [x] Set up proper DNS records

## 2. Update Environment Variables
- [x] Modify API service environment configuration
   a. [x] Change MLFLOW_SERVER_URL from external URL to internal service discovery URL
   b. [x] Add fallback configuration for local development
   c. [x] Ensure environment variables are properly propagated
- [x] Update ECS task definition
   a. [x] Modify environment variables in task definition
   b. [x] Deploy updated task definition
   c. [x] Verify new environment variables are active

## 3. Fix Proxy Routing Logic
- [x] Update mlflow_proxy.py to handle internal routing
   a. [x] Modify proxy_request function to use internal MLflow URL
   b. [x] Fix artifact endpoint routing to prevent external redirects
   c. [x] Ensure proper path translation for all endpoint types
- [x] Add robust error handling
   a. [x] Handle connection errors to internal service
   b. [x] Provide meaningful error messages for debugging
   c. [x] Add retry logic for transient failures

## 4. Enhance Logging and Monitoring
- [x] Add comprehensive logging to proxy
   a. [x] Log incoming request paths
   b. [x] Log translated paths and target URLs
   c. [x] Log response status codes and errors
- [x] Add metrics collection
   a. [x] Track successful vs failed proxy requests
   b. [x] Monitor response times for each endpoint type
   c. [ ] Set up CloudWatch metrics

## 5. Create Health Check Endpoints
- [x] Implement MLflow connectivity health check
   a. [x] Add endpoint to test experiments API
   b. [x] Add endpoint to test models API
   c. [x] Add endpoint to test artifacts API
- [x] Create comprehensive health status endpoint
   a. [x] Return detailed status for each MLflow API type
   b. [x] Include internal service connectivity status
   c. [x] Provide debugging information

## 6. Testing (Dependent on Implementation)
- [x] Write unit tests for proxy routing logic
   a. [x] Test path translation for all endpoint types
   b. [x] Test error handling scenarios
   c. [x] Test health check endpoints
- [ ] Create integration tests
   a. [ ] Test end-to-end model registration flow
   b. [ ] Test artifact upload and download
   c. [ ] Test with standard MLflow client
- [ ] Manual testing with test_real_registration.py
   a. [ ] Run registration test with updated routing
   b. [ ] Verify all MLflow operations succeed
   c. [ ] Document any issues found

## 7. Documentation
- [x] Update API documentation
   a. [x] Document internal routing architecture
   b. [x] Create troubleshooting guide
   c. [x] Add examples of correct MLflow client configuration
- [ ] Update README.md with configuration changes
   a. [ ] Document new environment variables
   b. [ ] Explain service discovery setup
   c. [ ] Add deployment instructions
- [ ] Create runbook for common issues
   a. [ ] How to debug routing problems
   b. [ ] How to verify service connectivity
   c. [ ] How to rollback if issues arise

## 8. Deployment and Verification
- [x] Deploy changes to development environment
   a. [x] Update ECS task definitions
   b. [x] Deploy new API container
   c. [x] Verify services start correctly
- [ ] Run comprehensive tests
   a. [ ] Execute test_real_registration.py
   b. [ ] Test all MLflow client operations
   c. [ ] Verify backward compatibility
- [ ] Monitor deployment
   a. [ ] Check CloudWatch logs for errors
   b. [ ] Monitor API response times
   c. [ ] Verify no increase in error rates

## 9. Rollback Plan
- [ ] Document rollback procedure
   a. [ ] How to revert task definitions
   b. [ ] How to restore previous environment variables
   c. [ ] How to verify rollback success
- [ ] Test rollback procedure
   a. [ ] Practice rollback in development
   b. [ ] Document time required for rollback
   c. [ ] Identify any data migration issues