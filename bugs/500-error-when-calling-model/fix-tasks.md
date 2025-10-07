# Fix Tasks: 500 Error When Calling Model

## Root Cause Summary
**Issue:** Terraform configuration for `HUGGINGFACE_API_KEY` exists but was never deployed via `terraform apply`.

**Impact:** API service cannot access HuggingFace models, returning 500 errors to all prediction requests for Model ID 21.

**Fix Strategy:** Apply existing Terraform configuration to deploy the secret to ECS task definition.

---

## 1. Immediate Fix (CRITICAL - Priority 1)

### 1.1 Apply Terraform Configuration
- [ ] **Navigate to infrastructure repository**
  ```bash
  cd /Users/timothyogilvie/Dropbox/Hokusai/hokusai-infrastructure/environments
  ```

- [ ] **Review current Terraform state**
  ```bash
  terraform plan -out=tfplan-huggingface-fix
  ```
  - Verify plan shows adding `HUGGINGFACE_API_KEY` secret to hokusai-api-development task definition
  - Verify no unexpected changes are included
  - Expected: Task definition update (new revision created)

- [ ] **Apply Terraform changes**
  ```bash
  terraform apply tfplan-huggingface-fix
  ```
  - **Expected result:** New task definition revision created (likely revision 151)
  - **Expected output:** Task definition update successful

- [ ] **Verify task definition update**
  ```bash
  # Check new task definition includes the secret
  aws ecs describe-task-definition \
    --task-definition hokusai-api-development \
    --query 'taskDefinition.containerDefinitions[0].secrets[?name==`HUGGINGFACE_API_KEY`]'
  ```
  - **Expected:** Should return the secret ARN, not empty array

### 1.2 Force ECS Service Deployment
- [ ] **Trigger service redeployment with new task definition**
  ```bash
  aws ecs update-service \
    --cluster hokusai-development \
    --service hokusai-api-development \
    --force-new-deployment \
    --region us-east-1
  ```
  - **Why:** ECS service needs to use the new task definition revision
  - **Expected:** Service will stop old tasks and start new ones

- [ ] **Monitor deployment progress**
  ```bash
  # Watch service deployment
  aws ecs describe-services \
    --cluster hokusai-development \
    --services hokusai-api-development \
    --query 'services[0].deployments' \
    --region us-east-1
  ```
  - Wait for PRIMARY deployment to stabilize
  - Old tasks should drain and new tasks should be RUNNING

- [ ] **Check service health**
  ```bash
  # Wait 2-3 minutes for new tasks to be healthy
  aws ecs describe-services \
    --cluster hokusai-development \
    --services hokusai-api-development \
    --query 'services[0].{running:runningCount,desired:desiredCount,health:healthCheckGracePeriodSeconds}' \
    --region us-east-1
  ```
  - **Expected:** runningCount == desiredCount

### 1.3 Verify Secret Access in Running Container
- [ ] **Check task logs for startup**
  ```bash
  aws logs tail /ecs/hokusai-api-development \
    --follow --since 5m \
    --region us-east-1
  ```
  - Look for successful ModelServingService initialization
  - Should NOT see "HuggingFace token not configured" errors on startup

- [ ] **Verify environment variable is accessible (if exec enabled)**
  ```bash
  # Get running task ARN
  TASK_ARN=$(aws ecs list-tasks \
    --cluster hokusai-development \
    --service-name hokusai-api-development \
    --desired-status RUNNING \
    --query 'taskArns[0]' \
    --output text \
    --region us-east-1)

  # Check if variable is present (without revealing value)
  aws ecs execute-command \
    --cluster hokusai-development \
    --task $TASK_ARN \
    --container api \
    --command "env | grep HUGGINGFACE_API_KEY | cut -d= -f1" \
    --interactive \
    --region us-east-1
  ```
  - **Expected output:** `HUGGINGFACE_API_KEY` (without showing value)
  - **Note:** Only works if ECS Exec is enabled

---

## 2. Testing Tasks (CRITICAL - Priority 1)

**Dependency:** Complete all 1.x tasks first

### 2.1 Functional Testing
- [ ] **Test Model ID 21 prediction endpoint**
  ```bash
  curl -X POST https://api.hokus.ai/api/v1/models/21/predict \
    -H "X-API-Key: ${HOKUSAI_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{
      "inputs": {
        "company_size": 1000,
        "industry": "Technology",
        "engagement_score": 75,
        "website_visits": 10,
        "email_opens": 5,
        "content_downloads": 3,
        "demo_requested": true,
        "budget_confirmed": false,
        "decision_timeline": "Q2 2025",
        "title": "VP of Sales"
      }
    }'
  ```
  - **Expected:** HTTP 200 response with prediction results
  - **NOT:** HTTP 500 with "HuggingFace token not configured"

- [ ] **Test model info endpoint**
  ```bash
  curl https://api.hokus.ai/api/v1/models/21/info \
    -H "X-API-Key: ${HOKUSAI_API_KEY}"
  ```
  - **Expected:** HTTP 200 with model metadata

- [ ] **Test model health endpoint**
  ```bash
  curl https://api.hokus.ai/api/v1/models/21/health \
    -H "X-API-Key: ${HOKUSAI_API_KEY}"
  ```
  - **Expected:** HTTP 200 with health status

### 2.2 Error Handling Testing
- [ ] **Test with invalid inputs (should still work, different error)**
  ```bash
  curl -X POST https://api.hokus.ai/api/v1/models/21/predict \
    -H "X-API-Key: ${HOKUSAI_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"inputs": {}}'
  ```
  - **Expected:** HTTP 400 (bad request) or 422 (validation error)
  - **NOT:** HTTP 500 "HuggingFace token not configured"

- [ ] **Test with missing authentication**
  ```bash
  curl -X POST https://api.hokus.ai/api/v1/models/21/predict \
    -H "Content-Type: application/json" \
    -d '{"inputs": {"company_size": 100}}'
  ```
  - **Expected:** HTTP 401 (unauthorized)

### 2.3 Integration Testing
- [ ] **Run original failing client code from bug report**
  - Use the exact Python client code from the Linear issue
  - Should now succeed without errors

- [ ] **Test model caching (second request should be faster)**
  ```bash
  # First request (loads model)
  time curl -X POST https://api.hokus.ai/api/v1/models/21/predict \
    -H "X-API-Key: ${HOKUSAI_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"inputs": {"company_size": 1000, "engagement_score": 75}}'

  # Second request (uses cached model)
  time curl -X POST https://api.hokus.ai/api/v1/models/21/predict \
    -H "X-API-Key: ${HOKUSAI_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"inputs": {"company_size": 1000, "engagement_score": 75}}'
  ```
  - **Expected:** Second request should be significantly faster

---

## 3. Validation Tasks (HIGH - Priority 2)

**Dependency:** Complete all 2.x tasks first

### 3.1 Service Health Validation
- [ ] **Check CloudWatch logs for errors**
  ```bash
  aws logs filter-log-events \
    --log-group-name /ecs/hokusai-api-development \
    --start-time $(date -u -d '10 minutes ago' +%s)000 \
    --filter-pattern "ERROR" \
    --region us-east-1
  ```
  - Should NOT see "HuggingFace token not configured" errors

- [ ] **Verify no regression in other endpoints**
  ```bash
  # Test health endpoint (no auth)
  curl https://api.hokus.ai/health

  # Test models list endpoint (with auth)
  curl https://api.hokus.ai/api/v1/models \
    -H "X-API-Key: ${HOKUSAI_API_KEY}"
  ```
  - All should return successfully

### 3.2 Third-Party Integration Validation
- [ ] **Notify third-party tester that fix is deployed**
- [ ] **Request third-party to rerun their integration test**
- [ ] **Confirm successful prediction from third-party**

### 3.3 Performance Validation
- [ ] **Monitor API latency metrics**
  ```bash
  # Check CloudWatch metrics for API latency
  aws cloudwatch get-metric-statistics \
    --namespace AWS/ECS \
    --metric-name CPUUtilization \
    --dimensions Name=ServiceName,Value=hokusai-api-development Name=ClusterName,Value=hokusai-development \
    --start-time $(date -u -d '1 hour ago' +%s) \
    --end-time $(date -u +%s) \
    --period 300 \
    --statistics Average \
    --region us-east-1
  ```
  - CPU and memory should be within normal ranges

- [ ] **Check response time distribution**
  - First prediction (model load): 2-5 seconds expected
  - Cached predictions: <500ms expected

---

## 4. Code Quality Tasks (MEDIUM - Priority 3)

**Dependency:** None (can be done in parallel with testing)

### 4.1 Code Improvements (Optional)
- [ ] **Consider adding startup validation**
  ```python
  # In ModelServingService.__init__()
  if not self.hf_token:
      logger.warning("HUGGINGFACE_API_KEY not configured - model serving will fail")
  else:
      logger.info("HuggingFace API key configured successfully")
  ```
  - This would make the issue visible in startup logs
  - **Note:** This is optional - the current error handling is clear

### 4.2 Error Message Improvements (Optional)
- [ ] **Enhance error message with troubleshooting hints**
  ```python
  if not self.hf_token:
      raise HTTPException(
          status_code=500,
          detail={
              "error": "HuggingFace token not configured",
              "hint": "Ensure HUGGINGFACE_API_KEY environment variable is set in ECS task definition",
              "docs": "https://docs.hokus.ai/troubleshooting/huggingface-config"
          }
      )
  ```
  - Provides actionable guidance for operators
  - **Note:** Current error is already clear enough

---

## 5. Monitoring & Observability (HIGH - Priority 2)

**Dependency:** Complete 1.x tasks first

### 5.1 Add Monitoring for Configuration Drift
- [ ] **Create CloudWatch alarm for this specific error**
  ```bash
  aws cloudwatch put-metric-alarm \
    --alarm-name hokusai-api-huggingface-token-missing \
    --alarm-description "Alert if HuggingFace token error occurs" \
    --metric-name ErrorCount \
    --namespace AWS/ApiGateway \
    --statistic Sum \
    --period 300 \
    --threshold 1 \
    --comparison-operator GreaterThanThreshold \
    --datapoints-to-alarm 1 \
    --evaluation-periods 1 \
    --region us-east-1
  ```

- [ ] **Add log-based metric for "HuggingFace token not configured"**
  ```bash
  aws logs put-metric-filter \
    --log-group-name /ecs/hokusai-api-development \
    --filter-name HuggingFaceTokenError \
    --filter-pattern '"HuggingFace token not configured"' \
    --metric-transformations \
      metricName=HuggingFaceTokenError,\
metricNamespace=Hokusai/API,\
metricValue=1 \
    --region us-east-1
  ```

### 5.2 Startup Health Check
- [ ] **Add startup log verification to deployment process**
  - After deployment, automatically check logs for successful initialization
  - Alert if "HuggingFace token not configured" appears in startup logs

---

## 6. Documentation Tasks (MEDIUM - Priority 3)

### 6.1 Update Deployment Documentation
- [ ] **Document the deployment process in `DEPLOYMENT_README.md`**
  - Add step: "Verify Terraform changes are applied before testing"
  - Add checklist for environment variable verification

- [ ] **Update deployment checklist**
  ```markdown
  ## Pre-Deployment Checklist
  - [ ] All Terraform changes applied (`terraform apply`)
  - [ ] ECS service redeployed with new task definition
  - [ ] Environment variables verified in running tasks
  - [ ] Smoke tests passed
  ```

### 6.2 Create Troubleshooting Guide Entry
- [ ] **Add to troubleshooting guide**
  ```markdown
  ## "HuggingFace token not configured" Error

  **Symptom:** API returns 500 error with message "HuggingFace token not configured"

  **Cause:** HUGGINGFACE_API_KEY environment variable missing from ECS task

  **Fix:**
  1. Verify secret exists in AWS Secrets Manager
  2. Verify Terraform configuration includes secret reference
  3. Run `terraform apply` in infrastructure repo
  4. Force ECS service redeployment
  5. Verify environment variable in running task
  ```

### 6.3 Document Root Cause in Knowledge Base
- [ ] **Create post-mortem document** (already done - `bugs/500-error-when-calling-model/root-cause.md`)
- [ ] **Share learnings with team**
  - Process improvement: Terraform state verification
  - Lesson: Configuration drift detection needed

---

## 7. Prevention Tasks (HIGH - Priority 2)

### 7.1 Automated Terraform State Verification
- [ ] **Create CI/CD check to detect drift**
  ```bash
  # In CI/CD pipeline
  cd infrastructure/environments
  terraform plan -detailed-exitcode
  # Exit code 2 means changes exist but weren't applied
  ```

- [ ] **Add post-deployment verification script**
  ```bash
  #!/bin/bash
  # verify-ecs-config.sh
  # Verify all expected environment variables are in deployed ECS task

  EXPECTED_VARS=("DATABASE_HOST" "MLFLOW_SERVER_URL" "HUGGINGFACE_API_KEY")
  TASK_DEF="hokusai-api-development"

  for var in "${EXPECTED_VARS[@]}"; do
    aws ecs describe-task-definition \
      --task-definition $TASK_DEF \
      --query "taskDefinition.containerDefinitions[0].secrets[?name=='$var']" \
      --output text
    if [ $? -ne 0 ]; then
      echo "ERROR: $var not found in task definition"
      exit 1
    fi
  done
  ```

### 7.2 Environment Variable Documentation
- [ ] **Create `ENVIRONMENT_VARIABLES.md` in data-pipeline repo**
  - Document all required variables
  - Document where each is configured (Terraform file, line number)
  - Document secret ARNs

- [ ] **Add environment variable sync validation**
  ```python
  # scripts/validate-environment.py
  # Parse .env.example and verify all required vars are in Terraform
  ```

### 7.3 Deployment Process Improvements
- [ ] **Add to deployment runbook**
  ```markdown
  ## Deployment Steps
  1. Merge PR to main branch
  2. **Navigate to infrastructure repo**
  3. **Run `terraform plan` and review changes**
  4. **Run `terraform apply` if changes exist**
  5. **Force ECS service deployment if task definition changed**
  6. Run smoke tests
  7. Monitor for errors
  ```

- [ ] **Create deployment automation script**
  ```bash
  #!/bin/bash
  # deploy-with-infrastructure-sync.sh
  # Automatically checks for Terraform drift and applies changes
  ```

---

## 8. Rollback Plan

### 8.1 If Fix Causes Issues
- [ ] **Rollback procedure** (unlikely to be needed)
  ```bash
  # Revert to previous task definition revision
  aws ecs update-service \
    --cluster hokusai-development \
    --service hokusai-api-development \
    --task-definition hokusai-api-development:150 \
    --force-new-deployment \
    --region us-east-1
  ```

- [ ] **Monitor rollback**
  - Verify service returns to stable state
  - Note: Rollback would bring back the original bug

### 8.2 Alternative Fix (if primary fails)
- [ ] **Option 1: Set environment variable directly (temporary workaround)**
  ```bash
  # Update task definition manually via AWS Console
  # Add HUGGINGFACE_API_KEY as plain environment variable (NOT RECOMMENDED - insecure)
  ```

- [ ] **Option 2: Use different secret ARN**
  ```bash
  # If secret ARN is wrong, create new secret and update Terraform
  aws secretsmanager create-secret \
    --name hokusai/development/huggingface/api-key-v2 \
    --secret-string "hf_your_token_here" \
    --region us-east-1
  ```

---

## Implementation Checklist

### Pre-Implementation
- [x] Root cause confirmed (configuration drift)
- [x] Terraform configuration verified (exists in code)
- [x] AWS Secret verified (exists in Secrets Manager)
- [ ] Team notification (deployment window communicated)
- [ ] Backup plan documented

### Critical Path (Must complete in order)
1. [ ] Section 1: Immediate Fix (Apply Terraform, redeploy ECS)
2. [ ] Section 2: Testing Tasks (Verify fix works)
3. [ ] Section 3: Validation Tasks (Confirm no regressions)
4. [ ] Section 5: Monitoring (Ensure we detect future issues)

### Parallel Tasks (Can do anytime)
- [ ] Section 4: Code Quality (Optional improvements)
- [ ] Section 6: Documentation (Update guides)
- [ ] Section 7: Prevention (Process improvements)

### Post-Implementation
- [ ] All tests passing
- [ ] Third-party integration confirmed working
- [ ] Monitoring alerts configured
- [ ] Documentation updated
- [ ] Team notified of fix completion
- [ ] Post-mortem shared with team

---

## Estimated Timeline

- **Section 1 (Immediate Fix):** 15-20 minutes
- **Section 2 (Testing):** 15-20 minutes
- **Section 3 (Validation):** 10-15 minutes
- **Section 5 (Monitoring):** 20-30 minutes
- **Section 7 (Prevention):** 1-2 hours (can be done later)

**Total critical path time:** ~1 hour
**Total with prevention:** ~2-3 hours

---

## Success Criteria

- [x] Root cause identified
- [ ] Terraform applied successfully
- [ ] ECS service redeployed with new task definition
- [ ] Model ID 21 predictions return 200 (not 500)
- [ ] Third-party integration working
- [ ] No regressions in other endpoints
- [ ] Monitoring configured
- [ ] Documentation updated
- [ ] Process improvements implemented

**Ready to proceed with implementation?** ✅ YES
