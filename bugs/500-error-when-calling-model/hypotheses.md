# Root Cause Hypotheses: 500 Error When Calling Model

## Hypothesis Summary Table

| # | Hypothesis | Confidence | Complexity | Impact if True |
|---|------------|------------|------------|----------------|
| 1 | HUGGINGFACE_API_KEY environment variable missing from ECS task definition | **Very High (95%)** | Simple | Critical - Blocks all HF model serving |
| 2 | HuggingFace token exists but lacks required permissions | Medium (30%) | Simple | High - Would need token regeneration |
| 3 | Token exists in wrong secret location or name | Low (10%) | Medium | Medium - Would need configuration update |
| 4 | Environment variable set but not propagated to container | Very Low (5%) | Medium | Medium - Docker/ECS configuration issue |

## Detailed Hypotheses

### Hypothesis 1: HUGGINGFACE_API_KEY Environment Variable Missing from ECS Task Definition

**Confidence**: Very High (95%)

**Category**: Configuration - Missing Environment Variable

#### Description

The `HUGGINGFACE_API_KEY` environment variable is not configured in the ECS task definition for the `hokusai-api-development` service. When the API container starts, `ModelServingService.__init__()` calls `os.getenv("HUGGINGFACE_API_KEY")` which returns `None`. When a prediction request requires downloading a model from HuggingFace, the code raises an HTTP 500 error.

#### Supporting Evidence

1. **Code inspection**: `src/api/endpoints/model_serving.py:63`
   ```python
   def __init__(self):
       self.hf_token = os.getenv("HUGGINGFACE_API_KEY")
   ```

2. **Error message is explicit**: `"HuggingFace token not configured"` - this is the exact error raised when `self.hf_token` is `None`

3. **ECS task definition verification**:
   ```bash
   aws ecs describe-task-definition --task-definition hokusai-api-development \
     --query 'taskDefinition.containerDefinitions[0].environment[?name==`HUGGINGFACE_API_KEY`]'
   # Returns: []
   ```

4. **No secret configured**:
   ```bash
   aws ecs describe-task-definition --task-definition hokusai-api-development \
     --query 'taskDefinition.containerDefinitions[0].secrets[?name==`HUGGINGFACE_API_KEY`]'
   # Returns: []
   ```

5. **Historical evidence**: Previous bug investigation documented this as a "separate task" that was never completed (`bugs/api-404-errors/ENDPOINT_TEST_RESULTS.md:123-167`)

6. **.env.example documents the variable**: Line 58 shows it's expected: `HUGGINGFACE_API_KEY=hf_your_token_here`

#### Why This Causes the Bug

1. ECS task starts without `HUGGINGFACE_API_KEY` environment variable
2. `ModelServingService` initializes with `self.hf_token = None`
3. User makes prediction request to `/api/v1/models/21/predict`
4. Code path: `predict()` → `serve_prediction()` → `load_model_from_huggingface()`
5. At line 104-105, condition check: `if not self.hf_token:`
6. Raises `HTTPException(status_code=500, detail="HuggingFace token not configured")`
7. FastAPI returns 500 error to client

#### Test Method

**Test 1: Verify environment variable is missing (Quick)**
```bash
# Check current ECS task environment
aws ecs describe-task-definition \
  --task-definition hokusai-api-development \
  --region us-east-1 \
  --query 'taskDefinition.containerDefinitions[0].{env:environment,secrets:secrets}' \
  | jq '.env[] | select(.name | contains("HUGGING"))'

# Expected: No output (confirms variable is missing)
```

**Test 2: Verify error code path (Code review)**
```bash
# Read the exact code that raises the error
grep -A 5 -B 5 "HuggingFace token not configured" src/api/endpoints/model_serving.py
```

Expected results:
- **If hypothesis is TRUE**: Environment variable is not in task definition
- **If hypothesis is FALSE**: Environment variable exists in task definition

#### Code/Configuration to Check

**Primary:**
- ECS task definition: `hokusai-api-development` (environment variables and secrets)
- Code: `src/api/endpoints/model_serving.py:63` (where variable is read)
- Code: `src/api/endpoints/model_serving.py:104-105` (where error is raised)

**Infrastructure (in hokusai-infrastructure repo):**
- Terraform file defining ECS task for API service
- File likely at: `environments/development/ecs-api-service.tf` or similar

#### Quick Fix Test

**Immediate verification (manual environment variable injection):**

Option A - Local test with environment variable:
```bash
# Run API locally with token
export HUGGINGFACE_API_KEY="hf_test_token"
python -c "import os; print('Token:', os.getenv('HUGGINGFACE_API_KEY'))"
# Should print the token
```

Option B - Update running ECS task (temporary, for testing only):
```bash
# Note: This would require updating task definition and forcing new deployment
# NOT recommended as a permanent fix, only for verification
```

**Expected outcome if hypothesis TRUE:**
- Adding the environment variable will resolve the 500 error
- Predictions will proceed to next stage (actual model download/inference)

---

### Hypothesis 2: HuggingFace Token Exists but Lacks Required Permissions

**Confidence**: Medium (30%)

**Category**: Configuration - Invalid/Insufficient Permissions

#### Description

A `HUGGINGFACE_API_KEY` environment variable IS configured in the ECS task definition, but the token itself is invalid, expired, or lacks the necessary permissions to download private models from the `timogilvie/hokusai-model-21-sales-lead-scorer` repository.

#### Supporting Evidence

1. **Model is private**: Config shows `"is_private": True` and `"storage_type": "huggingface_private"`
2. **Token permission requirements**: Private models require read access
3. **Possible scenarios**:
   - Token expired
   - Token revoked
   - Token has only "write" access, not "read"
   - Token doesn't have access to specific organization/repo

#### Why This Causes the Bug

If this hypothesis were true:
1. `self.hf_token` would NOT be `None`
2. The check at line 104-105 would PASS
3. Code would proceed to `hf_hub_download()` at line 112-117
4. HuggingFace Hub API would return 401/403 error
5. **Different error message would be shown** (not "token not configured")

**Counter-evidence**: The actual error message is "HuggingFace token not configured", which is raised BEFORE any API call to HuggingFace. This makes Hypothesis 2 unlikely.

#### Test Method

**Only test if Hypothesis 1 is FALSE**

1. Check if token environment variable exists:
   ```bash
   aws ecs describe-tasks --cluster hokusai-development \
     --tasks $(aws ecs list-tasks --cluster hokusai-development \
       --service-name hokusai-api-development --query 'taskArns[0]' --output text) \
     --query 'tasks[0].overrides.containerOverrides[0].environment'
   ```

2. If token exists, test token validity:
   ```bash
   # Extract token from ECS or Secrets Manager
   TOKEN="<token_value>"

   # Test token with HuggingFace API
   curl -H "Authorization: Bearer $TOKEN" \
     https://huggingface.co/api/models/timogilvie/hokusai-model-21-sales-lead-scorer
   ```

Expected results:
- **If hypothesis is TRUE**: Token exists but API call fails with 401/403
- **If hypothesis is FALSE**: Either no token exists, or token works correctly

---

### Hypothesis 3: Token Exists in Wrong Secret Location or Name

**Confidence**: Low (10%)

**Category**: Configuration - Naming Mismatch

#### Description

The HuggingFace token might be stored in AWS Secrets Manager or as an ECS secret, but under a different name than what the code expects. For example:
- Secret named `HUGGINGFACE_TOKEN` instead of `HUGGINGFACE_API_KEY`
- Secret named `HF_TOKEN` instead of `HUGGINGFACE_API_KEY`
- Secret exists in Secrets Manager but not linked to ECS task

#### Supporting Evidence

- `.env.example` uses `HUGGINGFACE_API_KEY` (line 58)
- Other services might use different naming conventions
- Previous projects sometimes used `HF_TOKEN` or `HUGGINGFACE_TOKEN`

**Counter-evidence**:
- Initial ECS checks showed NO secrets or environment variables with "HUGGINGFACE" in the name
- Makes this hypothesis unlikely

#### Test Method

1. **Check all secrets in Secrets Manager:**
   ```bash
   aws secretsmanager list-secrets --region us-east-1 \
     --query 'SecretList[?contains(Name, `huggingface`) || contains(Name, `hf_`) || contains(Name, `HF`)]'
   ```

2. **Check all environment variables in task definition:**
   ```bash
   aws ecs describe-task-definition \
     --task-definition hokusai-api-development \
     --query 'taskDefinition.containerDefinitions[0].environment[*].name' \
     | grep -i "hf\|hugging"
   ```

3. **Check database for configuration storage:**
   ```bash
   # If configuration is stored in database
   # Query configuration table for HuggingFace-related keys
   ```

Expected results:
- **If hypothesis is TRUE**: Secret exists under different name
- **If hypothesis is FALSE**: No HuggingFace-related secrets exist anywhere

#### Quick Fix Test

If a misnamed secret is found:
```bash
# Option 1: Add environment variable mapping in ECS task definition
# Map the actual secret name to HUGGINGFACE_API_KEY

# Option 2: Update code to read from the actual secret name
# (Not recommended - infrastructure should match code expectations)
```

---

### Hypothesis 4: Environment Variable Set but Not Propagated to Container

**Confidence**: Very Low (5%)

**Category**: Infrastructure - Container Configuration

#### Description

The `HUGGINGFACE_API_KEY` is configured in the ECS task definition, but due to Docker or ECS configuration issues, it's not being propagated to the running container. This could be due to:
- Task definition not applied (using old revision)
- Docker entrypoint script not preserving environment variables
- ECS agent issue on the host

#### Supporting Evidence

- Extremely rare in ECS (would affect all environment variables)
- Would be evident in ECS agent logs
- Other environment variables (like `DATABASE_HOST`) work correctly

**Counter-evidence**:
- ECS describe-task-definition shows no HUGGINGFACE_API_KEY at all
- Other environment variables work (authentication passes, database connects)
- Makes this hypothesis extremely unlikely

#### Test Method

1. **Verify current task revision:**
   ```bash
   aws ecs describe-services \
     --cluster hokusai-development \
     --services hokusai-api-development \
     --query 'services[0].taskDefinition'
   ```

2. **Check running task environment:**
   ```bash
   # Connect to running container (if possible)
   aws ecs execute-command \
     --cluster hokusai-development \
     --task <task-arn> \
     --container api \
     --command "env | grep HUGGING"
   ```

3. **Check if service is using latest task definition:**
   ```bash
   # Compare service task definition vs latest
   SERVICE_REVISION=$(aws ecs describe-services \
     --cluster hokusai-development \
     --services hokusai-api-development \
     --query 'services[0].taskDefinition' --output text | cut -d: -f7)

   LATEST_REVISION=$(aws ecs describe-task-definition \
     --task-definition hokusai-api-development \
     --query 'taskDefinition.revision' --output text)

   echo "Service: $SERVICE_REVISION, Latest: $LATEST_REVISION"
   ```

Expected results:
- **If hypothesis is TRUE**: Variable exists in definition but not in container
- **If hypothesis is FALSE**: Variable doesn't exist in definition at all

---

## Testing Priority Order

### Priority 1: Test Hypothesis 1 (IMMEDIATE)

**Why start here:**
- Highest confidence (95%)
- Simplest to verify (single AWS CLI command)
- Error message directly supports this hypothesis
- Historical evidence confirms it was a known gap

**Test command:**
```bash
aws ecs describe-task-definition \
  --task-definition hokusai-api-development \
  --query 'taskDefinition.containerDefinitions[0].{environment:environment,secrets:secrets}' \
  | jq -r '.environment[]?, .secrets[]? | select(.name | contains("HUGGINGFACE"))'
```

**Expected result:** No output (confirming variable is missing)

**If confirmed:** Proceed directly to fix implementation (Step 7: Generate Fix Tasks)

**If rejected:** Unlikely, but would proceed to Hypothesis 2

---

### Priority 2: Test Hypothesis 2 (if H1 is FALSE)

**Why test this second:**
- Next most likely (30%)
- Error message would be different, but worth checking
- Token validation is simple

**Only test if:** Hypothesis 1 is proven FALSE (environment variable exists)

---

### Priority 3: Test Hypothesis 3 (if H1 and H2 are FALSE)

**Why test this third:**
- Low probability (10%)
- Requires broader secrets investigation
- More time-consuming to verify

---

### Priority 4: Test Hypothesis 4 (if all others FALSE)

**Why test this last:**
- Extremely low probability (5%)
- Would indicate ECS infrastructure issue (very rare)
- Most complex to diagnose

---

## Alternative Hypotheses to Consider if All Above Fail

**(These are extremely unlikely given the clear error message)**

1. **Network connectivity issue between ECS and HuggingFace**
   - Would produce different error (connection timeout, DNS failure)
   - Authentication passes, so networking works

2. **Code path difference in production vs development**
   - Different environment branches or feature flags
   - Would need code review for conditional logic

3. **HuggingFace API service outage**
   - Would affect all users globally
   - Error occurs before HF API is even called

4. **Model repository deleted or moved**
   - Would produce "repository not found" error
   - Error occurs before repository access is attempted

5. **Python package issue (huggingface_hub library)**
   - Import would fail, not token check
   - Other imports work, so package installation is fine

---

## Data Needed for Further Investigation

**If Hypothesis 1-4 all prove FALSE (extremely unlikely):**

1. **Enable debug logging:**
   ```python
   # Add to model_serving.py
   logger.debug(f"HF Token at init: {self.hf_token}")
   logger.debug(f"Environment vars: {os.environ}")
   ```

2. **Collect full ECS task environment:**
   ```bash
   aws ecs describe-tasks --cluster hokusai-development \
     --tasks $(aws ecs list-tasks --cluster hokusai-development \
       --service-name hokusai-api-development --query 'taskArns[0]' --output text)
   ```

3. **Check application startup logs:**
   ```bash
   aws logs tail /ecs/hokusai-api-development \
     --since 1h --filter-pattern "ModelServingService"
   ```

4. **Verify Python environment in container:**
   ```bash
   # Execute in running container
   python -c "import os; print('HUGGINGFACE_API_KEY' in os.environ)"
   ```

---

## Recommendation

**Proceed immediately with testing Hypothesis 1.**

The evidence is overwhelming:
- ✅ Error message is explicit and matches expected code path
- ✅ AWS CLI confirms no environment variable in task definition
- ✅ Historical documentation confirms this was known missing configuration
- ✅ Code inspection shows exact line that raises this error

**Confidence level: 95%** that the root cause is confirmed and we can proceed to fix implementation.
