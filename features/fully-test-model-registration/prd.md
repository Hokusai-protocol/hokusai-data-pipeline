# Product Requirements Document: Hokusai Data Pipeline Infrastructure Testing

## Executive Summary

The Hokusai data pipeline has recently migrated its infrastructure to a centralized repository. This migration has resulted in service deployment issues that are blocking model registration functionality. This PRD outlines a comprehensive testing strategy to validate the infrastructure setup, identify all issues, and provide clear documentation for the infrastructure team to resolve problems.

## Objectives

### Primary Objectives
- Validate the complete hokusai-data-pipeline infrastructure after centralized repository migration
- Execute comprehensive testing of all model registration components using existing test scripts
- Document all infrastructure issues with clear remediation steps for the infrastructure team
- Update MODEL_REGISTRATION_TEST_REPORT.md with current testing results

### Secondary Objectives
- Establish baseline metrics for infrastructure health monitoring
- Identify potential improvements to the testing framework
- Create reusable validation procedures for future infrastructure changes

## Personas

### Data Pipeline Developer
- Needs to verify infrastructure is properly configured for model registration
- Requires clear visibility into what components are working vs failing
- Must provide actionable feedback to infrastructure team

### Infrastructure Team Member
- Needs detailed documentation of infrastructure issues
- Requires specific error messages and failure points
- Must understand exact configuration changes needed

### Third-Party ML Engineer
- Expects model registration to work with their API key
- Needs clear error messages when registration fails
- Requires working endpoints for MLflow integration

## Success Criteria

### Must Have
- Execute all 9 test scripts in the comprehensive test suite
- Generate updated MODEL_REGISTRATION_TEST_REPORT.md with current results
- Document all failing components with specific error messages
- Provide infrastructure team with actionable fix requirements
- Achieve infrastructure health score measurement

### Should Have
- Test with multiple API keys to verify authentication consistency
- Measure response times for all endpoints
- Validate both Bearer token and X-API-Key authentication methods
- Test artifact storage functionality

### Nice to Have
- Performance benchmarks for model registration workflow
- Automated alerts for infrastructure degradation
- Rollback procedures documentation

## User Stories

### Story 1: Infrastructure Health Validation
As a data pipeline developer, I want to run infrastructure health checks so that I can verify all required services are deployed and healthy.

**Acceptance Criteria:**
- ALB connectivity verified
- All 3 ECS services status checked (auth, api, mlflow)
- Target group health validated
- Infrastructure score calculated

### Story 2: Model Registration Testing
As a third-party ML engineer, I want to register a model using my API key so that I can deploy models to the Hokusai platform.

**Acceptance Criteria:**
- API key authentication works
- MLflow experiments can be created
- Models can be registered and retrieved
- Artifacts can be stored and accessed

### Story 3: Issue Documentation
As an infrastructure team member, I want clear documentation of all failures so that I can quickly fix configuration issues.

**Acceptance Criteria:**
- Each failure includes service name and endpoint
- HTTP status codes and error messages provided
- Expected vs actual behavior documented
- Specific terraform resources identified

## Functional Requirements

### F1: Test Execution Framework
- Use tests/run_all_tests.py as the master test orchestrator
- Execute all 9 test scripts in defined sequence
- Collect results in both JSON and Markdown formats
- Handle API key as command-line parameter

### F2: Infrastructure Health Testing
- Test ALB connectivity to hokusai-development-953444464.us-east-1.elb.amazonaws.com
- Verify ECS service status for:
  - hokusai-auth-development
  - hokusai-api-development
  - hokusai-mlflow-development
- Check target group health for each service
- Calculate overall infrastructure health score (target: >80%)

### F3: Authentication Testing
- Test Bearer token authentication on all endpoints
- Test X-API-Key header authentication
- Verify authentication propagation to MLflow
- Document authentication success rates

### F4: Model Registration Workflow
- Stage 1: Create and train model locally
- Stage 2: Create MLflow experiment via API
- Stage 3: Log model run with metrics
- Stage 4: Register model in MLflow
- Stage 5: Retrieve registered model
- Stage 6: Test artifact storage and retrieval

### F5: Endpoint Availability Testing
- Discover all available endpoints
- Test each endpoint with proper authentication
- Document response codes and latency
- Identify routing configuration issues

### F6: Report Generation
- Update MODEL_REGISTRATION_TEST_REPORT.md with:
  - Timestamp of test execution
  - Infrastructure health score
  - Service availability matrix
  - Detailed failure analysis
  - Recommended fixes for infrastructure team
- Generate test_execution_summary.json with raw results
- Create INFRASTRUCTURE_ISSUES.md for infrastructure team

## Non-Functional Requirements

### Performance Requirements
- All health check endpoints should respond within 1000ms
- Model registration workflow should complete within 30 seconds
- Test suite execution should complete within 10 minutes

### Security Requirements
- API keys must be handled securely (not logged)
- Test data should not contain sensitive information
- Authentication headers must be properly validated

### Reliability Requirements
- Tests should be idempotent and repeatable
- Failed tests should not leave orphaned resources
- Test framework should handle service timeouts gracefully

### Documentation Requirements
- All test results must be timestamped
- Error messages must include full stack traces
- Reports must be in standard Markdown format
- Infrastructure issues must reference specific terraform resources

## Technical Architecture

### Test Infrastructure
```
┌─────────────────┐
│run_all_tests.py │
└────────┬────────┘
         │
    ┌────┴────┬──────────┬──────────┬──────────┐
    │         │          │          │          │
┌───▼───┐┌───▼───┐┌─────▼─────┐┌───▼───┐┌────▼────┐
│Infra  ││Auth   ││Registration││MLflow ││E2E Test │
│Health ││Test   ││Flow Test   ││Routing││Scripts  │
└───┬───┘└───┬───┘└─────┬─────┘└───┬───┘└────┬────┘
    │        │          │          │          │
    └────────┴────┬─────┴──────────┴──────────┘
                  │
            ┌─────▼─────┐
            │  Reports  │
            └───────────┘
```

### Infrastructure Components Under Test
- Application Load Balancer (ALB)
- ECS Fargate Services
- Target Groups
- MLflow Service
- API Gateway Service
- Authentication Service
- S3 Artifact Storage
- RDS PostgreSQL Database

## Implementation Tasks

### Task 1: Environment Preparation
- Obtain valid API key from user
- Verify test script dependencies
- Check connectivity to AWS resources
- Set up result collection directories

### Task 2: Infrastructure Health Assessment
- Run test_infrastructure_health.py
- Document ECS service status
- Verify target group configurations
- Calculate infrastructure score

### Task 3: Authentication System Validation
- Execute test_authentication.py
- Test both authentication methods
- Document authentication success rates
- Identify auth service dependencies

### Task 4: Model Registration Testing
- Run test_model_registration_flow.py
- Test each stage of registration
- Document failure points
- Collect error messages and stack traces

### Task 5: Comprehensive Test Suite Execution
- Execute tests/run_all_tests.py with API key
- Monitor test execution progress
- Collect all generated reports
- Verify report completeness

### Task 6: Analysis and Documentation
- Analyze test results for patterns
- Update MODEL_REGISTRATION_TEST_REPORT.md
- Create detailed INFRASTRUCTURE_ISSUES.md
- Prepare executive summary of findings

### Task 7: Infrastructure Team Communication
- Share reports with infrastructure team
- Highlight critical blockers
- Provide terraform resource references
- Suggest prioritized fix sequence

## Timeline

### Phase 1: Preparation (2 hours)
- Environment setup
- API key configuration
- Dependency verification

### Phase 2: Testing (8 hours)
- Infrastructure health tests (2 hours)
- Authentication tests (1 hour)
- Model registration tests (3 hours)
- Comprehensive suite execution (2 hours)

### Phase 3: Analysis and Documentation (4 hours)
- Result analysis (2 hours)
- Report generation (1 hour)
- Infrastructure team handoff (1 hour)

Total estimated time: 14 hours

## Risk Analysis

### High Risk
- Complete infrastructure failure preventing any testing
- API key access issues blocking authentication tests
- Missing ECS services causing 100% test failure

### Medium Risk
- Partial service availability leading to incomplete testing
- Network connectivity issues to AWS resources
- Test script dependencies not properly installed

### Low Risk
- Report generation failures
- Performance degradation during testing
- Temporary service interruptions

## Dependencies

### External Dependencies
- Access to valid Hokusai API key
- AWS infrastructure accessibility
- Infrastructure team availability for fixes

### Internal Dependencies
- Python environment with required packages
- Test scripts in working condition
- Write access to update reports

## Quality Assurance

### Test Coverage Requirements
- 100% of endpoints must be tested
- All authentication methods validated
- Every stage of model registration verified
- All error paths documented

### Report Quality Standards
- Clear problem statements with evidence
- Specific error messages and codes
- Actionable remediation steps
- Terraform resource identification

### Success Metrics
- Test execution completion rate: 100%
- Report generation success: 100%
- Issue documentation clarity: High
- Infrastructure team acceptance: Required

## Appendices

### A. Test Script Inventory
1. test_infrastructure_health.py - Infrastructure validation
2. test_authentication.py - Auth system testing
3. test_endpoint_availability.py - Endpoint discovery
4. test_model_registration_flow.py - Registration workflow
5. test_mlflow_routing.py - MLflow proxy validation
6. test_services.py - Service connectivity
7. test_services_direct.py - Direct service testing
8. test_health_endpoints.py - Health check validation
9. test_e2e_model_registration.py - End-to-end testing

### B. Expected Infrastructure State
- hokusai-auth-development: RUNNING (1/1 tasks)
- hokusai-api-development: RUNNING (expected)
- hokusai-mlflow-development: RUNNING (expected)
- All target groups: HEALTHY
- Infrastructure score: >80%

### C. Report Templates
- MODEL_REGISTRATION_TEST_REPORT.md
- test_execution_summary.json
- INFRASTRUCTURE_ISSUES.md
- infrastructure_health_report.json