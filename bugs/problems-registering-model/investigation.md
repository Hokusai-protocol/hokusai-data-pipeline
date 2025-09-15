# Bug Investigation: Problems Registering Model

## 1. Bug Summary

**Issue**: Third-party users are unable to register models in the MLflow registry due to permission restrictions on API keys.

**When it occurs**: During model registration attempts via the Hokusai API (registry.hokus.ai)

**Who/what is affected**:
- External users trying to register models
- Model deployment pipeline
- Third-party integrations

**Business impact and severity**:
- **Severity**: HIGH
- **Impact**: Blocks external users from contributing models to the platform, preventing core platform functionality and potentially losing customers/contributors

## 2. Reproduction Steps

**Verified reproduction**:
1. Obtain a Hokusai API key (example: hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN)
2. Configure MLflow client to use https://registry.hokus.ai/api/mlflow
3. Authenticate with the API key
4. Attempt to create a run or register a model
5. Observe 403 Forbidden error on write operations

**Required environment**:
- MLflow client configured for Hokusai registry
- Valid Hokusai API key
- Network access to registry.hokus.ai

**Success rate**: 100% reproducible with read-only API keys

**Variations**:
- Read operations (querying experiments) work successfully
- Only write operations (creating runs, registering models) fail

## 3. Affected Components

**Services/Modules**:
- hokusai-auth-service: API key generation and permission management
- hokusai-data-pipeline/api: API service handling model registration
- hokusai-data-pipeline/mlflow: MLflow server and registry

**Database tables**:
- Auth service: api_keys, permissions, user_roles
- MLflow: experiments, runs, registered_models, model_versions

**API endpoints**:
- POST /api/mlflow/api/2.0/mlflow/runs/create
- POST /api/mlflow/api/2.0/mlflow/registered-models/create
- POST /api/mlflow/api/2.0/mlflow/model-versions/create

**Infrastructure**:
- ALB routing rules for registry.hokus.ai
- ECS service: hokusai-mlflow-development
- Service discovery: mlflow.hokusai-development.local

## 4. Initial Observations

**Error details**:
- HTTP 403 Forbidden on write operations
- Authentication succeeds (not 401)
- Read operations return 200 OK

**Key observations**:
- API key is valid and authenticates successfully
- The issue is specifically with authorization, not authentication
- Suggests permission scope limitation on the API key

**Recent changes to investigate**:
- Changes to auth service permission model
- Updates to API key generation logic
- Modifications to MLflow integration middleware

## 5. Data Analysis Required

**Logs to examine**:
```bash
# Auth service logs
aws logs tail /ecs/hokusai-auth-development --follow --since 1d --filter-pattern "hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN"

# API service logs
aws logs tail /ecs/hokusai-api-development --follow --since 1d --filter-pattern "403"

# MLflow service logs
aws logs tail /ecs/hokusai-mlflow-development --follow --since 1d
```

**Database queries**:
- Check API key permissions in auth database
- Verify user role assignments
- Review permission scopes for model registration

**Metrics to review**:
- 403 error rate trends
- API key creation patterns
- Model registration success/failure rates

## 6. Investigation Strategy

**Priority order**:
1. Verify API key permission configuration in auth service
2. Check middleware authorization logic in API service
3. Review MLflow authentication/authorization integration
4. Examine API key generation process
5. Test with different permission scopes

**Tools and techniques**:
- Direct database queries to check permissions
- API request tracing through services
- Test API key creation with different scopes
- Compare working vs non-working API keys

**Key questions**:
- What permission scopes are assigned to new API keys by default?
- Is there a separate permission for model write operations?
- Are third-party users assigned different roles than internal users?
- Has the permission model changed recently?

**Success criteria**:
- Identify exact permission missing from API keys
- Understand why keys are created with limited permissions
- Determine proper permission configuration for model registration

## 7. Risk Assessment

**Current impact**:
- Third-party users cannot contribute models
- Platform adoption blocked for external contributors
- Potential revenue/growth impact

**Potential for escalation**:
- Could affect all new user registrations
- May impact existing users if permissions are retroactively changed
- Could lead to data inconsistency if partially fixed

**Security implications**:
- Must ensure fix doesn't over-provision permissions
- Need to maintain proper access control
- Audit trail for permission changes required

**Data integrity concerns**:
- No data corruption risk identified
- Model registry remains consistent
- Existing models unaffected

## 8. Timeline

**First occurrence**: Based on bug report, recently discovered by third party

**Deployment correlation**:
- Check recent deployments to auth service
- Review infrastructure changes to permissions
- Examine any MLflow version updates

**Frequency**: Consistent - affects all API keys with read-only permissions

**Patterns**:
- Only affects write operations
- Consistent across all third-party API keys tested
- No time-based variation observed