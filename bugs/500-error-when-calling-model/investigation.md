# Bug Investigation: 500 Error When Calling Model

## 1. Bug Summary

**Issue:** Third-party users testing the Hokusai API for lead scoring (Model ID 21) receive a 500 Internal Server Error with the message: `{"detail":"HuggingFace token not configured"}`

**When it occurs:** Every time a prediction request is made to `/api/v1/models/21/predict`

**Who/what is affected:**
- All external API users attempting to use Model ID 21 (Sales Lead Scoring Model)
- Third-party integrators testing the Hokusai API
- Any model that requires HuggingFace Hub access for inference

**Business impact and severity:**
- **Severity:** Critical
- **Impact:** Complete blocking of third-party integration testing
- **Revenue impact:** Prevents customer onboarding and API adoption
- **Reputation risk:** External partners experiencing broken API endpoints

## 2. Reproduction Steps

**Verified step-by-step reproduction:**
1. Obtain a valid Hokusai API key
2. Initialize Hokusai API client pointing to `https://api.hokus.ai/api`
3. Call the prediction endpoint: `POST /api/v1/models/21/predict`
4. Provide valid input data for lead scoring

**Required environment/configuration:**
- Valid Hokusai API key (authentication passes successfully)
- Internet connectivity to api.hokus.ai
- Model ID 21 exists and is configured in the database

**Success rate of reproduction:** 100% - error occurs on every request

**Any variations in behavior:** None - consistent 500 error with same message

**Example request:**
```bash
curl -X POST https://api.hokus.ai/api/v1/models/21/predict \
  -H "X-API-Key: ${HOKUSAI_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "company_size": 1000,
      "engagement_score": 75,
      "industry": "Technology"
    }
  }'
```

**Error response:**
```json
{
  "detail": "HuggingFace token not configured"
}
```

## 3. Affected Components

**Services/modules:**
- **Primary:** API Service (ECS Task: `hokusai-api-development`)
- **Code:** `src/api/endpoints/model_serving.py` (ModelServingService class)
- **Infrastructure:** ECS Task Definition environment variables

**Database tables involved:** None directly (model metadata is queried but not the issue)

**API endpoints touched:**
- `POST /api/v1/models/{model_id}/predict` (Line 403 in model_serving.py)
- Specifically affects Model ID 21 and any other HuggingFace-backed models

**Frontend components impacted:**
- Third-party API clients
- Any client attempting to use HuggingFace-backed models

**Third-party dependencies:**
- HuggingFace Hub API (requires authentication token)
- huggingface_hub Python library (installed, working correctly)

## 4. Initial Observations

**Error messages or stack traces:**
```
2025-10-07 08:57:24 [error] Hokusai API error response
error='{"detail":"HuggingFace token not configured"}'
request_id=106a23d7-ff27-4f74-bf66-60d3db9951e4
status_code=500
```

**Code location of error:**
- File: `src/api/endpoints/model_serving.py`
- Line: 105 in `load_model_from_huggingface()` method
- Code: `if not self.hf_token: raise HTTPException(status_code=500, detail="HuggingFace token not configured")`

**Root cause mechanism:**
```python
class ModelServingService:
    def __init__(self):
        self.model_cache = {}
        self.hf_token = os.getenv("HUGGINGFACE_API_KEY")  # Line 63
        # ...

    async def load_model_from_huggingface(self, repository_id: str, model_type: str) -> Any:
        if not self.hf_token:  # Line 104-105
            raise HTTPException(status_code=500, detail="HuggingFace token not configured")
```

**Environment variable check results:**
- `.env.example` documents: `HUGGINGFACE_API_KEY=hf_your_token_here`
- ECS task definition environment variables: **MISSING** ❌
- ECS task definition secrets: **MISSING** ❌

**Recent changes to affected areas:**
- Previous bug fixes noted the configuration issue but didn't resolve it
- Referenced in `bugs/api-404-errors/ENDPOINT_TEST_RESULTS.md` (line 123-167)

**Similar past issues:**
- Issue previously identified in authentication routing bug investigation
- Documented as "separate task" to configure HUGGINGFACE_API_KEY
- Never completed as a follow-up action

## 5. Data Analysis Required

**Logs to examine:**
- ✅ Already examined: ECS logs show clear "HuggingFace token not configured" error
- No further log analysis needed - error message is explicit

**Infrastructure queries to run:**
```bash
# Verify ECS task definition does not have HUGGINGFACE_API_KEY
aws ecs describe-task-definition \
  --task-definition hokusai-api-development \
  --query 'taskDefinition.containerDefinitions[0].environment[?name==`HUGGINGFACE_API_KEY`]'

# Check if token exists in AWS Secrets Manager
aws secretsmanager list-secrets --region us-east-1 \
  --query 'SecretList[?contains(Name, `huggingface`)]'
```

**Configuration to verify:**
- Terraform configuration for ECS task definition
- AWS Secrets Manager for HuggingFace token storage
- Environment variable propagation from infrastructure to ECS

## 6. Investigation Strategy

**Priority order for investigation:**
1. ✅ **Confirm root cause** (COMPLETED)
   - Environment variable `HUGGINGFACE_API_KEY` is not set in ECS task definition
   - Code expects it at initialization: `self.hf_token = os.getenv("HUGGINGFACE_API_KEY")`

2. **Determine proper secret storage location**
   - Check if secret should be in AWS Secrets Manager
   - Review infrastructure repo for secret configuration patterns

3. **Identify infrastructure code that needs updating**
   - Locate Terraform ECS task definition for hokusai-api-development
   - Find where environment variables and secrets are configured

4. **Verify HuggingFace token availability**
   - Confirm valid HuggingFace token exists
   - Verify token has necessary permissions (read access to private repos)

**Tools and techniques to use:**
- AWS CLI for ECS task definition inspection ✅
- Terraform for infrastructure changes
- AWS Secrets Manager for secure token storage

**Key questions to answer:**
- ✅ Is the environment variable missing from ECS? **YES**
- Where should the HuggingFace token be stored? **AWS Secrets Manager (best practice)**
- Does a valid token exist that we can use? **Need to verify**
- What Terraform file defines the API service task definition? **Need to locate**

**Success criteria for root cause identification:**
- ✅ Identified exact cause: Missing `HUGGINGFACE_API_KEY` environment variable in ECS
- ✅ Understood code path: `ModelServingService.__init__()` → `os.getenv()` → `None` → HTTPException
- Determined infrastructure fix location: Pending

## 7. Risk Assessment

**Current impact on users:**
- 100% of API requests to Model ID 21 fail
- External partner integration completely blocked
- No workaround available for users

**Potential for escalation:**
- Low escalation risk (doesn't affect other services)
- High business impact (blocks customer onboarding)
- Quick fix available once token is configured

**Security implications:**
- Token must be stored securely in AWS Secrets Manager
- Token should NOT be hardcoded or stored in environment variables directly
- ECS task should reference secret ARN, not plain text value

**Data integrity concerns:**
- None - this is a configuration issue, not a data issue
- No risk to existing data or models

## 8. Timeline

**When bug first appeared:**
- Model serving endpoint was implemented with HuggingFace support
- Token configuration step was noted but never completed
- Documented in previous bug investigation (api-404-errors) as separate task

**Correlation with deployments/changes:**
- Issue exists since initial deployment of model serving feature
- Not related to recent code changes
- Configuration gap from original implementation

**Frequency of occurrence:**
- Every single request to HuggingFace-backed models fails
- 100% failure rate

**Any patterns in timing:**
- No time-based patterns
- Consistently fails regardless of time, load, or user

## 9. Investigation Status

**Root cause identified:** ✅ YES

**Root cause:**
The `HUGGINGFACE_API_KEY` environment variable is not configured in the ECS task definition for the `hokusai-api-development` service. The `ModelServingService` class attempts to read this variable during initialization (`self.hf_token = os.getenv("HUGGINGFACE_API_KEY")`), and when it's not present, the service initializes with `hf_token = None`. When a prediction request is made that requires downloading a model from HuggingFace, the code explicitly checks for this token and raises a 500 error if it's missing.

**Next steps:**
1. Generate hypotheses about how to best implement the fix
2. Test hypothesis by configuring the environment variable
3. Implement permanent fix via infrastructure-as-code
4. Verify fix resolves the issue
