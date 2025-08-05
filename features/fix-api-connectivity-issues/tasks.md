# Implementation Tasks: Fix API Connectivity Issues

## 1. ALB Routing Configuration
1. [ ] Review current ALB listener rules in AWS console
   a. [ ] Document existing routing patterns
   b. [ ] Identify misconfigured routes for /api/mlflow/*
   c. [ ] Check target group associations

2. [ ] Update ALB listener rules
   a. [ ] Modify infrastructure/terraform/alb-listener-rules.tf
   b. [ ] Route /api/mlflow/* to API service target group (not MLflow directly)
   c. [ ] Maintain /mlflow/* routes for direct MLflow access
   d. [ ] Apply terraform changes to development environment

3. [ ] Verify ALB health checks
   a. [ ] Confirm API service health check path (/health)
   b. [ ] Confirm MLflow service health check path (/health)
   c. [ ] Adjust health check intervals and thresholds

## 2. Service Discovery Configuration (Dependent on ALB Routing)
4. [ ] Create ECS service discovery namespace
   a. [ ] Add Cloud Map configuration in infrastructure/terraform/service-discovery.tf
   b. [ ] Define namespace for hokusai-development
   c. [ ] Configure DNS settings for internal resolution

5. [ ] Register services with service discovery
   a. [ ] Register API service with Cloud Map
   b. [ ] Register MLflow service with Cloud Map
   c. [ ] Update ECS task definitions with service discovery attributes

6. [ ] Update application configuration
   a. [ ] Modify src/api/utils/config.py to use service discovery DNS
   b. [ ] Replace hardcoded IP (10.0.1.173:5000) with mlflow.hokusai.local:5000
   c. [ ] Add environment variables for service endpoints

## 3. Authentication Middleware Fixes (Dependent on Service Discovery)
7. [ ] Fix authentication middleware
   a. [ ] Update src/middleware/auth_fixed.py with correct header handling
   b. [ ] Ensure API keys are properly formatted in Authorization header
   c. [ ] Add logging for authentication debugging

8. [ ] Validate platform API key
   a. [ ] Test key: hk_live_NVWOYDfNfTJyFzUDkQDBk2LLA4pB5qza
   b. [ ] Verify key validation with auth service
   c. [ ] Check user context extraction

## 4. Network Security Updates
9. [ ] Update security groups
   a. [ ] Review current security group rules in infrastructure/terraform/main.tf
   b. [ ] Ensure API service can reach MLflow on port 5000
   c. [ ] Add ingress rule for internal service communication
   d. [ ] Apply security group changes

10. [ ] Verify network connectivity
    a. [ ] Test connectivity from API container to MLflow container
    b. [ ] Check DNS resolution within ECS tasks
    c. [ ] Validate port accessibility

## 5. Application Code Improvements
11. [ ] Enhance MLflow proxy implementation
    a. [ ] Update src/api/routes/mlflow_proxy_improved.py
    b. [ ] Add retry logic with exponential backoff
    c. [ ] Implement proper error handling for 502 errors
    d. [ ] Add detailed logging for request/response debugging

12. [ ] Add connection pooling
    a. [ ] Implement HTTP connection pooling for internal calls
    b. [ ] Configure timeout settings appropriately
    c. [ ] Add circuit breaker pattern for resilience

## 6. Testing and Validation
13. [ ] Run unit tests
    a. [ ] Test authentication middleware changes
    b. [ ] Test MLflow proxy route handlers
    c. [ ] Verify configuration loading

14. [ ] Execute integration tests
    a. [ ] Run test_model_registration_complete.py
    b. [ ] Execute scripts/test_mlflow_connection.py
    c. [ ] Validate with scripts/test_health_endpoints.py
    d. [ ] Test with platform API key end-to-end

15. [ ] Performance testing
    a. [ ] Load test the MLflow proxy endpoints
    b. [ ] Monitor response times and error rates
    c. [ ] Check for memory leaks or connection exhaustion

## 7. Documentation
16. [ ] Update technical documentation
    a. [ ] Document new service discovery setup
    b. [ ] Update API endpoint documentation
    c. [ ] Add troubleshooting guide for connectivity issues

17. [ ] Create runbook
    a. [ ] Document rollback procedures
    b. [ ] Add monitoring and alerting setup
    c. [ ] Include debugging commands and tools

## 8. Deployment and Monitoring
18. [ ] Deploy to development environment
    a. [ ] Apply infrastructure changes via Terraform
    b. [ ] Deploy updated API service container
    c. [ ] Verify all services are healthy

19. [ ] Set up monitoring
    a. [ ] Configure CloudWatch alarms for 502 errors
    b. [ ] Create dashboard for API health metrics
    c. [ ] Set up alerts for service discovery failures

20. [ ] Final validation
    a. [ ] Complete end-to-end model registration test
    b. [ ] Verify infrastructure health score improvement
    c. [ ] Confirm all success criteria are met