# Bug Resolution: API 404 Errors on HTTPS

## ✅ Status: RESOLVED

**Resolution Date:** 2025-10-02
**Resolution Method:** Manual AWS deployment (during investigation)
**Verification:** Production endpoints confirmed working

---

## Summary

### Bug Report
Third-party users receiving 404 errors when calling Model ID 21 endpoints via HTTPS at `https://api.hokus.ai/api/v1/models/*`

### Root Cause (Confirmed)
ALB listener rules for `/api/v1/*` paths were missing for HTTPS (port 443). Only HTTP (port 80) rules existed, causing HTTPS requests to fall through to the default 404 action.

### Resolution
HTTPS listener rules were **manually created in AWS Console** on the Registry ALB (`hokusai-registry-development`) while investigation was in progress.

**Deployed Rules:**
- Priority 110: `/api/*` → Registry API target group
- Priority 105: `/api/mlflow/*` → Registry API target group
- Priority 50: `/mlflow/*` → Registry MLflow target group

### Verification (2025-10-02)

**Production Tests:**
```bash
✅ https://api.hokus.ai/health → HTTP 200 OK
✅ https://api.hokus.ai/api/v1/models → HTTP 401 (routing works, auth required)
```

**DNS Configuration:**
- `api.hokus.ai` → Points to `hokusai-registry-development` ALB (not Main ALB)
- Registry ALB has HTTPS listener rules deployed and working

---

## Investigation Value

While the fix was deployed manually during investigation, this bug workflow delivered:

### 1. Documentation ✅
- Complete root cause analysis
- Systematic hypothesis testing methodology
- Fix tasks and deployment procedures
- Validation checklist for future deployments

### 2. Integration Tests ✅
Created comprehensive test suite to prevent regression:
- `tests/integration/test_https_model_serving_endpoints.py`
- Tests verify HTTPS endpoints return JSON, not 404
- Tests verify authentication still required
- Tests verify no plain-text ALB default responses

### 3. Infrastructure Code ✅
Terraform code committed for future reference:
- `hokusai-infrastructure` commit f42d483
- Documents the correct HTTPS listener rule configuration
- Can be used to recreate rules if needed

### 4. Process Improvement ✅
- Identified Terraform state sync issue
- Highlighted need for infrastructure change coordination
- Created reusable bug investigation template

---

## Terraform State Sync Required

⚠️ **Action Item:** Import manually created AWS resources into Terraform state

The HTTPS listener rules exist in AWS but are not tracked in Terraform state. To prevent Terraform from trying to recreate them:

```bash
# Navigate to infrastructure repo
cd /Users/timothyogilvie/Dropbox/Hokusai/hokusai-infrastructure/environments

# Get listener rule ARNs
aws elbv2 describe-rules \
  --listener-arn $(aws elbv2 describe-listeners \
    --load-balancer-arn $(aws elbv2 describe-load-balancers \
      --names hokusai-registry-development \
      --query 'LoadBalancers[0].LoadBalancerArn' --output text) \
    --query 'Listeners[?Port==`443`].ListenerArn' --output text) \
  --query 'Rules[?Priority!=`default`].[RuleArn,Priority,Conditions[0].Values[0]]' \
  --output table

# Import each rule (example)
# terraform import aws_lb_listener_rule.registry_api[0] <arn-of-priority-110-rule>
```

**Note:** Defer this until ready to sync all infrastructure state changes.

---

## Files Created During Investigation

### hokusai-data-pipeline Repository

**Branch:** `bugfix/api-404-errors`

**Documentation:**
- `bugs/api-404-errors/investigation.md` - Investigation plan
- `bugs/api-404-errors/hypotheses.md` - Root cause hypotheses
- `bugs/api-404-errors/test-results.md` - Hypothesis testing
- `bugs/api-404-errors/root-cause.md` - Root cause analysis
- `bugs/api-404-errors/root-cause-confirmed.md` - Confirmed findings
- `bugs/api-404-errors/fix-tasks.md` - Fix implementation tasks
- `bugs/api-404-errors/validation.md` - Deployment validation checklist
- `bugs/api-404-errors/RESOLUTION.md` - This file

**Tests:**
- `tests/integration/test_https_model_serving_endpoints.py` - HTTPS endpoint tests

**Commits:**
- 5c46b32: Investigation and tests
- 354400e: Validation checklist

### hokusai-infrastructure Repository

**Branch:** `bugfix/add-https-listener-rules-for-api`

**Code Changes:**
- `terraform_module/data-pipeline/listeners.tf` - HTTPS listener rules (Terraform code)

**Commits:**
- f42d483: HTTPS listener rules Terraform code

---

## Lessons Learned

### What Went Well ✅
1. **Systematic investigation:** Root cause correctly identified through hypothesis testing
2. **Comprehensive documentation:** Complete paper trail of investigation process
3. **Test creation:** Integration tests prevent future regression
4. **Parallel fix:** Manual deployment resolved user impact quickly

### Challenges ⚠️
1. **Infrastructure coordination:** Manual AWS changes created Terraform state drift
2. **DNS discovery:** Initially assumed `api.hokus.ai` pointed to Main ALB (actually Registry ALB)
3. **Communication gap:** Investigation proceeded without knowing fix was being deployed

### Improvements for Next Time 🎯
1. **Check production first:** Verify bug still exists before deep investigation
2. **Coordinate with team:** Check if anyone is working on the same issue
3. **Infrastructure changes:** Establish process for manual AWS changes + Terraform sync
4. **Documentation location:** Consider shared doc for active infrastructure work

---

## Recommendations

### Immediate Actions
1. ✅ Mark Linear issue as resolved
2. ✅ Keep investigation branch for historical reference
3. ✅ Merge integration tests to main (prevent regression)
4. ⏭️ Schedule Terraform state sync (when infrastructure is stable)

### Future Prevention
1. **Integration tests:** Run `test_https_model_serving_endpoints.py` in CI/CD
2. **ALB monitoring:** Alert on elevated 404 rates for critical paths
3. **Infrastructure review:** Periodic Terraform plan to catch state drift
4. **Documentation:** Update deployment checklist to verify HTTPS rules

---

## Sign-Off

**Investigation Completed By:** Claude (AI Assistant)
**Investigation Date:** 2025-10-02
**Resolution Verified:** 2025-10-02
**Status:** RESOLVED ✅
**Third-Party User Impact:** Issue resolved, endpoints accessible

**Linear Issue:** Ready to close
**Branches:** Can be merged or archived as reference

---

## References

- **Original Bug Report:** Linear issue - "Still getting 404 errors when calling API"
- **Investigation Branch:** `bugfix/api-404-errors` (hokusai-data-pipeline)
- **Infrastructure Branch:** `bugfix/add-https-listener-rules-for-api` (hokusai-infrastructure)
- **Production Endpoint:** https://api.hokus.ai/api/v1/models/21/info
- **Registry ALB:** hokusai-registry-development
