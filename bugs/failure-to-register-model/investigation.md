# Bug Investigation Plan: Failure to Register Model

## Bug Summary

**Issue**: Multiple attempts to register the LSCOR (Sales Lead Scoring) model with the Hokusai platform are failing due to MLflow backend authentication and connectivity issues.

**When it occurs**: During model registration attempts via the hokusai-ml-platform Python package when calling register_baseline() or attempting direct MLflow API calls.

**Who/what is affected**: 
- GTM Backend Team attempting to deploy models
- Third-party users trying to register models via the API
- Model deployment pipeline blocked

**Business impact and severity**: HIGH
- Blocking model deployment to production
- Preventing platform integration for external teams
- Cannot validate end-to-end model serving workflow
- Development delays for dependent teams

## Reproduction Steps

**Verified step-by-step reproduction**:
1. Install hokusai-ml-platform package from GitHub
2. Set environment variable: `HOKUSAI_API_KEY=hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN`
3. Configure MLflow tracking URI: `https://registry.hokus.ai/api/mlflow`
4. Attempt to register model using ModelRegistry class
5. Observe authentication failures and 404 responses

**Required environment/configuration**:
- Python 3.11.8
- hokusai-ml-platform package (latest)
- Valid API key starting with "hk_live_"
- Direct internet connection (no proxy)

**Success rate of reproduction**: 100% failure rate

**Variations in behavior**:
- Some operations achieve partial success (create run_id) but fail on model version creation
- Different error codes observed: 404 Not Found, 403 Forbidden, "API key required"

## Affected Components

**Services/modules**:
- API service (hokusai-api-development) - proxy routing
- MLflow service (hokusai-mlflow-development) - model registry
- Auth service (hokusai-auth-development) - API key validation
- ALB routing rules for registry.hokus.ai

**Database tables involved**:
- MLflow database tables (experiments, runs, models, model_versions)
- Auth database (api_keys table)

**API endpoints touched**:
- `/api/mlflow/api/2.0/mlflow/experiments/create`
- `/api/mlflow/api/2.0/mlflow/runs/create`
- `/api/mlflow/api/2.0/mlflow/runs/log-metric`
- `/api/mlflow/api/2.0/mlflow/registered-models/create`
- `/api/mlflow/api/2.0/mlflow/model-versions/create`

**Third-party dependencies**:
- MLflow client library
- Bearer token authentication

## Initial Observations

**Error messages**:
- `INTERNAL_ERROR: Response: {'detail': 'Not Found'}` - 404 on MLflow endpoints
- `INTERNAL_ERROR: Response: {'detail': 'API key required'}` - Auth rejection
- `Failed to register baseline model: API request to endpoint /api/2.0/mlflow/model-versions/create failed with error code 403`

**Relevant log entries**:
```
2025-08-18 18:22:02,861 - hokusai.core.registry - WARNING - Failed to connect to MLflow (attempt 1/3): INTERNAL_ERROR: Response: {'detail': 'API key required'}
2025-08-18 18:22:03,900 - hokusai.core.registry - WARNING - Failed to connect to MLflow (attempt 2/3): INTERNAL_ERROR: Response: {'detail': 'API key required'}
2025-08-18 18:22:05,943 - hokusai.core.registry - ERROR - Failed to create MLflow client after 3 attempts
```

**Recent changes**: 
- Migration from Redis pub/sub to webhook system (PR in feature/replace-redis-with-webhook branch)
- Previous infrastructure consolidation to hokusai-infrastructure repo

**Similar past issues**:
- Multiple completed Linear tickets show history of MLflow connectivity problems
- Previous fixes for proxy routing (PR #60)
- Auth service integration issues resolved in past

## Data Analysis Required

**Logs to examine**:
- CloudWatch logs for /ecs/hokusai-api-development
- CloudWatch logs for /ecs/hokusai-mlflow-development  
- CloudWatch logs for /ecs/hokusai-auth-development
- ALB access logs for registry.hokus.ai

**Database queries to run**:
- Check if API key exists and is active in auth database
- Verify MLflow experiments/runs table for partial registrations
- Check for any model registry entries

**Metrics to review**:
- API service health check status
- MLflow service health check status
- 4xx/5xx error rates on registry.hokus.ai
- Request latency patterns

**User reports to gather**:
- Confirm if issue affects all API keys or specific ones
- Check if any successful registrations have occurred recently
- Verify if MLflow UI access works directly

## Investigation Strategy

**Priority order for investigation**:
1. Verify API proxy routing configuration for /api/mlflow endpoints
2. Check auth service API key validation flow
3. Test MLflow service direct connectivity
4. Validate ALB routing rules and target group health
5. Review auth header forwarding in proxy implementation
6. Check for environment variable configuration issues

**Tools and techniques to use**:
- Direct curl tests to each endpoint
- AWS CLI to check ECS task definitions and environment variables
- Database queries to verify configurations
- Network tracing between services
- Code review of proxy implementation

**Key questions to answer**:
- Is the API key being properly forwarded to MLflow?
- Are the proxy routes correctly configured?
- Is the auth service validating API keys correctly?
- Are there any missing environment variables?
- Is the MLflow service healthy and accessible internally?

**Success criteria for root cause identification**:
- Can reproduce exact failure point in the request flow
- Understand why authentication is failing
- Identify configuration or code causing 404 responses
- Have clear path to fix

## Risk Assessment

**Current impact on users**:
- Complete blockage of model registration functionality
- Third-party integrations cannot proceed
- Development teams blocked

**Potential for escalation**:
- High - core platform functionality broken
- Affects multiple teams and external users
- Could impact platform adoption

**Security implications**:
- API keys may not be properly validated
- Potential for authentication bypass if misconfigured
- Need to ensure proper auth flow maintained

**Data integrity concerns**:
- Partial model registrations may leave orphaned data
- Need to verify cleanup of failed attempts
- Ensure no corruption in MLflow database

## Timeline

**When bug first appeared**: 
- Reported on 2025-08-18
- Likely present since recent webhook migration work

**Correlation with deployments/changes**:
- Current branch: feature/replace-redis-with-webhook
- Recent commits show webhook system implementation
- May correlate with removal of Redis dependencies

**Frequency of occurrence**: 
- 100% consistent failure
- Affects all registration attempts

**Patterns in timing**:
- No time-based patterns observed
- Consistent across multiple retry attempts
- Not related to load or time of day