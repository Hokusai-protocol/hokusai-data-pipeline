# Tasks: Implement mTLS for Internal MLflow Communication

## 1. Certificate Generation and Management

1. [ ] Create certificate generation script
   a. [ ] Create `scripts/generate_mtls_certs.sh` script
   b. [ ] Generate CA certificate and private key
   c. [ ] Generate server certificate for MLflow service
   d. [ ] Generate client certificate for API service
   e. [ ] Add documentation comments to script
   f. [ ] Make script executable and test locally

2. [ ] Set up AWS Secrets Manager for certificate storage
   a. [ ] Create Secrets Manager secrets in development environment
   b. [ ] Upload CA certificate to `hokusai/development/mlflow/ca-cert`
   c. [ ] Upload server certificate to `hokusai/development/mlflow/server-cert`
   d. [ ] Upload server key to `hokusai/development/mlflow/server-key`
   e. [ ] Upload client certificate to `hokusai/development/mlflow/client-cert`
   f. [ ] Upload client key to `hokusai/development/mlflow/client-key`
   g. [ ] Verify all secrets are stored correctly

## 2. Infrastructure Configuration (Dependent on Certificate Generation)

3. [ ] Update Terraform configuration for Secrets Manager
   a. [ ] Add Secrets Manager resources to `hokusai-infrastructure/environments/development/main.tf`
   b. [ ] Create IAM policy for ECS task role to access secrets
   c. [ ] Attach IAM policy to MLflow service task role
   d. [ ] Attach IAM policy to API service task role
   e. [ ] Run `terraform plan` and review changes
   f. [ ] Apply Terraform changes to development environment
   g. [ ] Verify IAM permissions are working

4. [ ] Update ECS task definitions
   a. [ ] Add environment variable `ENABLE_MTLS_AUTH=true` to MLflow task
   b. [ ] Add environment variable `ENABLE_MTLS_AUTH=true` to API task
   c. [ ] Ensure tasks have sufficient IAM permissions
   d. [ ] Document environment variables in task definition

## 3. MLflow Service Configuration (Dependent on Infrastructure)

5. [ ] Create certificate loading script for MLflow
   a. [ ] Create `scripts/load_mlflow_certs.sh`
   b. [ ] Implement AWS Secrets Manager retrieval logic
   c. [ ] Add certificate file writing to /etc/mlflow/certs
   d. [ ] Set appropriate file permissions (600 for private keys)
   e. [ ] Export environment variables for MLflow server
   f. [ ] Add error handling and logging
   g. [ ] Make script executable

6. [ ] Update MLflow Dockerfile
   a. [ ] Copy certificate loading script to container
   b. [ ] Update CMD to run cert loading before MLflow server
   c. [ ] Add boto3 to requirements if not present
   d. [ ] Rebuild Docker image locally and test
   e. [ ] Tag image for deployment

7. [ ] Configure MLflow server for mTLS
   a. [ ] Research MLflow 3.4 mTLS configuration options
   b. [ ] Add server certificate configuration to MLflow startup
   c. [ ] Add client CA validation configuration
   d. [ ] Test MLflow server startup with certificates
   e. [ ] Verify certificate validation is working

## 4. API Service Configuration (Dependent on Infrastructure)

8. [ ] Enhance MLflow configuration module
   a. [ ] Add `configure_internal_mtls()` function to `src/utils/mlflow_config.py`
   b. [ ] Implement AWS Secrets Manager certificate retrieval
   c. [ ] Write certificates to /tmp/mlflow-certs directory
   d. [ ] Set MLflow environment variables for client certificates
   e. [ ] Add environment check (only staging/production)
   f. [ ] Add comprehensive logging
   g. [ ] Add error handling for missing secrets

9. [ ] Update MLflow client initialization
   a. [ ] Call `configure_internal_mtls()` in `MLFlowConfig.__init__()`
   b. [ ] Ensure mTLS is configured before tracking URI is set
   c. [ ] Add certificate verification to connection validation
   d. [ ] Test client certificate presentation
   e. [ ] Verify mTLS handshake succeeds

## 5. Authentication Middleware Enhancement (Dependent on MLflow/API Configuration)

10. [ ] Add internal request detection
    a. [ ] Implement `_is_internal_request()` method in `APIKeyAuthMiddleware`
    b. [ ] Check for private IP ranges (10.0.0.0/8)
    c. [ ] Add logging for internal request detection
    d. [ ] Test with internal and external IPs

11. [ ] Add mTLS certificate verification
    a. [ ] Implement `_verify_mtls_certificate()` method in `APIKeyAuthMiddleware`
    b. [ ] Check for peer certificate verification in request state
    c. [ ] Add fallback for different ASGI server implementations
    d. [ ] Add logging for certificate verification
    e. [ ] Test with valid and invalid certificates

12. [ ] Implement hybrid authentication dispatch
    a. [ ] Update `dispatch()` method to check for internal mTLS requests
    b. [ ] Bypass auth service validation for verified mTLS requests
    c. [ ] Set appropriate request.state attributes for internal requests
    d. [ ] Maintain existing API key flow for external requests
    e. [ ] Add metrics for auth path taken (mTLS vs API key)
    f. [ ] Test both authentication paths

## 6. Testing (Dependent on Implementation)

13. [ ] Write unit tests for certificate management
    a. [ ] Create `tests/unit/test_mtls_config.py`
    b. [ ] Test certificate loading from Secrets Manager
    c. [ ] Test certificate validation logic
    d. [ ] Test error handling for missing certificates
    e. [ ] Test error handling for invalid certificates
    f. [ ] Test environment-specific behavior (dev vs staging)
    g. [ ] Ensure all tests pass

14. [ ] Write unit tests for middleware
    a. [ ] Create `tests/unit/test_auth_middleware_mtls.py`
    b. [ ] Test `_is_internal_request()` with various IPs
    c. [ ] Test `_verify_mtls_certificate()` logic
    d. [ ] Test hybrid auth dispatch decision tree
    e. [ ] Test request.state attributes set correctly
    f. [ ] Mock external auth service to verify bypass
    g. [ ] Ensure all tests pass

15. [ ] Write integration tests for mTLS connection
    a. [ ] Create `tests/integration/test_mtls_connection.py`
    b. [ ] Test successful mTLS handshake with valid certificates
    c. [ ] Test connection failure with invalid certificates
    d. [ ] Test connection failure without certificates
    e. [ ] Test server certificate validation
    f. [ ] Ensure all tests pass

16. [ ] Write integration tests for auth middleware
    a. [ ] Create `tests/integration/test_auth_mtls_dispatch.py`
    b. [ ] Test internal request with mTLS bypasses auth service
    c. [ ] Test external request uses API key authentication
    d. [ ] Test internal request without mTLS falls back to API key
    e. [ ] Mock auth service and verify call counts
    f. [ ] Ensure all tests pass

17. [ ] Write integration tests for MLflow operations
    a. [ ] Create `tests/integration/test_mlflow_mtls_operations.py`
    b. [ ] Test model registration via mTLS
    c. [ ] Test experiment creation via mTLS
    d. [ ] Test artifact upload via mTLS
    e. [ ] Test metrics logging via mTLS
    f. [ ] Verify operations succeed without auth service calls
    g. [ ] Ensure all tests pass

18. [ ] Update existing tests
    a. [ ] Review all MLflow-related tests for compatibility
    b. [ ] Update tests to handle mTLS configuration
    c. [ ] Add mocks for certificate loading where needed
    d. [ ] Ensure backward compatibility tests pass
    e. [ ] Run full test suite and verify no regressions

## 7. Documentation

19. [ ] Update architecture documentation
    a. [ ] Update `docs/ARCHITECTURE.md` with mTLS architecture diagram
    b. [ ] Document hybrid authentication strategy
    c. [ ] Explain request flow for internal vs external requests
    d. [ ] Add security considerations section

20. [ ] Create certificate management documentation
    a. [ ] Create `docs/MTLS_CERTIFICATE_MANAGEMENT.md`
    b. [ ] Document certificate generation process
    c. [ ] Document certificate rotation procedure
    d. [ ] Document troubleshooting steps
    e. [ ] Add example commands for certificate operations

21. [ ] Update deployment documentation
    a. [ ] Update deployment runbooks with mTLS steps
    b. [ ] Document environment variables required
    c. [ ] Add pre-deployment checklist for mTLS
    d. [ ] Document rollback procedure

22. [ ] Update README
    a. [ ] Add mTLS feature to README.md features list
    b. [ ] Link to detailed mTLS documentation
    c. [ ] Update security section with mTLS benefits

## 8. Monitoring and Observability (Dependent on Implementation)

23. [ ] Add mTLS metrics
    a. [ ] Create Prometheus metrics for mTLS connections
    b. [ ] Track mTLS success/failure rates
    c. [ ] Track auth path distribution (mTLS vs API key)
    d. [ ] Add metrics to existing Prometheus endpoint

24. [ ] Create CloudWatch dashboards
    a. [ ] Create dashboard for mTLS health monitoring
    b. [ ] Add widget for certificate expiration warnings
    c. [ ] Add widget for auth path distribution
    d. [ ] Add widget for internal request latency

25. [ ] Set up alerts
    a. [ ] Create CloudWatch alarm for certificate expiring < 30 days
    b. [ ] Create alarm for mTLS failure rate > 1%
    c. [ ] Create alarm for unexpected API key auth from internal IPs
    d. [ ] Test all alarms trigger correctly

## 9. Deployment to Development (Dependent on Testing)

26. [ ] Pre-deployment verification
    a. [ ] Run full test suite locally
    b. [ ] Verify all certificates uploaded to Secrets Manager
    c. [ ] Verify Terraform infrastructure applied
    d. [ ] Review deployment checklist

27. [ ] Deploy MLflow service
    a. [ ] Build MLflow Docker image with mTLS support
    b. [ ] Push image to ECR
    c. [ ] Update ECS task definition with new image
    d. [ ] Deploy to development environment
    e. [ ] Monitor logs for certificate loading
    f. [ ] Verify MLflow service is healthy

28. [ ] Deploy API service
    a. [ ] Build API Docker image with mTLS support
    b. [ ] Push image to ECR
    c. [ ] Update ECS task definition with new image
    d. [ ] Deploy to development environment
    e. [ ] Monitor logs for mTLS configuration
    f. [ ] Verify API service is healthy

29. [ ] Post-deployment verification
    a. [ ] Test internal MLflow requests via API service
    b. [ ] Verify mTLS authentication in CloudWatch logs
    c. [ ] Verify auth service is not called for internal requests
    d. [ ] Test external API requests still work
    e. [ ] Run integration test suite against deployed services
    f. [ ] Monitor error rates and latency
    g. [ ] Verify all health checks pass

## 10. Performance Validation

30. [ ] Establish baseline metrics
    a. [ ] Collect 24 hours of pre-mTLS metrics
    b. [ ] Document average internal request latency
    c. [ ] Document auth service request volume
    d. [ ] Document Redis cache hit rates

31. [ ] Post-deployment performance analysis
    a. [ ] Collect 24 hours of post-mTLS metrics
    b. [ ] Compare internal request latency (target: >20% improvement)
    c. [ ] Compare auth service request volume (target: >50% reduction)
    d. [ ] Create performance comparison report
    e. [ ] Document any unexpected performance changes

## 11. Staging Deployment (Dependent on Development Success)

32. [ ] Prepare staging environment
    a. [ ] Generate staging certificates
    b. [ ] Upload staging certificates to Secrets Manager
    c. [ ] Apply Terraform changes to staging
    d. [ ] Verify IAM permissions in staging

33. [ ] Deploy to staging
    a. [ ] Build and push Docker images
    b. [ ] Deploy MLflow service to staging
    c. [ ] Deploy API service to staging
    d. [ ] Run full integration test suite
    e. [ ] Monitor for issues
    f. [ ] Verify performance improvements

## 12. Production Deployment (Dependent on Staging Success)

34. [ ] Prepare production environment
    a. [ ] Generate production certificates (90-day expiration)
    b. [ ] Upload production certificates to Secrets Manager
    c. [ ] Apply Terraform changes to production
    d. [ ] Schedule deployment during low-traffic window
    e. [ ] Prepare rollback plan

35. [ ] Deploy to production
    a. [ ] Build and push production Docker images
    b. [ ] Deploy MLflow service to production
    c. [ ] Monitor logs and metrics
    d. [ ] Deploy API service to production
    e. [ ] Monitor logs and metrics
    f. [ ] Verify zero increase in error rates
    g. [ ] Verify performance improvements
    h. [ ] Monitor for 24 hours

36. [ ] Post-production validation
    a. [ ] Run production smoke tests
    b. [ ] Verify auth service load reduced
    c. [ ] Check certificate expiration dates
    d. [ ] Update production runbook
    e. [ ] Document lessons learned

## Task Summary

- Total Tasks: 36
- Total Subtasks: 218
- Critical Path: Certificate Generation → Infrastructure → Implementation → Testing → Deployment
- Estimated Timeline: 3 weeks (Development: 1 week, Staging: 1 week, Production: 1 week)

## Dependencies

```
1-2 (Certificates) → 3-4 (Infrastructure) → 5-9 (Implementation)
5-9 (Implementation) → 10-12 (Middleware) → 13-18 (Testing)
13-18 (Testing) → 26-29 (Development Deployment)
26-29 (Development) → 32-33 (Staging)
32-33 (Staging) → 34-36 (Production)
```

## Risk Mitigation

- All deployment phases include rollback procedures
- Feature flag `ENABLE_MTLS_AUTH` allows quick disable
- Fallback to API key auth ensures service continuity
- Comprehensive testing before each deployment phase
