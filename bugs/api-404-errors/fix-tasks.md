# Fix Tasks for API 404 Errors (Missing HTTPS Listener Rules)

## Summary
Root cause: ALB listener rules for `/api/v1/*` paths exist only for HTTP (port 80), not for HTTPS (port 443), causing all HTTPS API requests to hit the default 404 action.

**Affected Repositories:**
1. `hokusai-infrastructure` - Main fix location (ALB listener rules)
2. `hokusai-data-pipeline` - Integration tests and documentation

---

## 1. Immediate Fix (hokusai-infrastructure)

### Critical Priority - Fix HTTPS Listener Rules

1. [x] **Add HTTPS listener rules to main ALB**
   - [x] Add `api_v1_https` rule for `/api/v1/*` paths (priority 95)
   - [x] Add `api_https` rule for `/api*` paths (priority 100)
   - [x] Add `api_mlflow_proxy_https` rule for `/api/mlflow/*` (priority 85)
   - [x] Add `mlflow_https` rule for `/mlflow/*` paths (priority 200)
   - File: `terraform_module/data-pipeline/listeners.tf`

2. [ ] **Validate Terraform configuration**
   - [ ] Run `terraform validate` in environments directory
   - [ ] Run `terraform plan` and review changes
   - [ ] Verify resource count shows 4 new listener rules to be added
   - [ ] Check for any conflicts with existing resources

3. [ ] **Deploy infrastructure changes**
   - [ ] Apply Terraform changes to development environment
   - [ ] Verify ALB listener rules are created in AWS console
   - [ ] Check listener rule priorities don't conflict

---

## 2. Testing Tasks

### 2.1 Infrastructure Testing (hokusai-infrastructure)

4. [ ] **Test ALB configuration before deployment**
   - [ ] Run `terraform plan` and capture output
   - [ ] Verify new rules target correct target groups
   - [ ] Confirm priorities don't overlap with existing rules

5. [ ] **Post-deployment validation**
   - [ ] Verify HTTPS listener has 4 new rules in AWS console
   - [ ] Check target group health for API service
   - [ ] Test with curl commands (see validation section)

### 2.2 Application Testing (hokusai-data-pipeline)

6. [x] **Create integration tests for HTTPS endpoints**
   - [x] Test `/api/v1/models/{id}/info` via HTTPS
   - [x] Test `/api/v1/models/{id}/predict` via HTTPS
   - [x] Test `/api/v1/models/{id}/health` via HTTPS
   - [x] Test authentication still works
   - [x] Test that 404 with plain text "Not Found" doesn't occur
   - File: `tests/integration/test_https_model_serving_endpoints.py`

7. [ ] **Run integration tests against deployed environment**
   - [ ] Set HOKUSAI_API_KEY environment variable
   - [ ] Set API_BASE_URL=https://api.hokus.ai
   - [ ] Run: `pytest tests/integration/test_https_model_serving_endpoints.py -v`
   - [ ] Verify all tests pass

8. [ ] **Manual endpoint testing**
   - [ ] Test Model ID 21 info endpoint with third-party user
   - [ ] Test Model ID 21 predict endpoint
   - [ ] Verify JSON responses, not HTML 404
   - [ ] Test with and without API key

---

## 3. Validation Tasks

9. [ ] **Validate fix against original bug report**
   - [ ] Contact third-party user to test their integration
   - [ ] Verify they can access Model ID 21 endpoints
   - [ ] Confirm they receive JSON responses, not 404 HTML
   - [ ] Get confirmation that issue is resolved

10. [ ] **Validate no regressions**
    - [ ] Test existing HTTP endpoints still work
    - [ ] Test other API paths (/api/mlflow/*, /mlflow/*)
    - [ ] Verify health endpoints accessible
    - [ ] Check MLflow UI still works
    - [ ] Verify auth service endpoints unaffected

11. [ ] **Performance validation**
    - [ ] Check ALB request latency hasn't increased
    - [ ] Verify target group response times normal
    - [ ] Monitor ECS task CPU/memory usage

12. [ ] **Create validation checklist for reviewers**
    ```
    - [ ] Terraform plan shows 4 new listener rules
    - [ ] No existing resources are modified/destroyed
    - [ ] HTTPS requests to /api/v1/* return JSON, not 404
    - [ ] Model serving endpoints accessible
    - [ ] Integration tests pass
    - [ ] Third-party user confirms fix
    ```

---

## 4. Code Quality Tasks

13. [ ] **Add comments to Terraform code**
    - [x] Add section header for HTTPS rules
    - [ ] Add comment explaining mirror of HTTP rules
    - [ ] Document priority numbering scheme
    - [ ] Add reference to this bug in comments

14. [ ] **Infrastructure code review**
    - [ ] Check for similar patterns in other ALBs
    - [ ] Verify auth ALB has both HTTP and HTTPS rules
    - [ ] Verify registry ALB has both HTTP and HTTPS rules
    - [ ] Consider creating a module to DRY up listener rules

---

## 5. Monitoring & Observability

15. [ ] **Add CloudWatch alarms for 404 errors**
    - [ ] Create alarm for elevated 404 rate on api.hokus.ai
    - [ ] Set threshold (e.g., >10 404s per minute)
    - [ ] Configure SNS notification to ops team
    - [ ] Test alarm triggers correctly

16. [ ] **Add monitoring for ALB target health**
    - [ ] Ensure existing target health alarms cover API service
    - [ ] Add alarm for unhealthy targets
    - [ ] Configure CloudWatch dashboard for ALB metrics

17. [ ] **Add logging for API access patterns**
    - [ ] Enable ALB access logging if not already enabled
    - [ ] Configure S3 bucket for access logs
    - [ ] Create CloudWatch Insights queries for 404 analysis
    - [ ] Document how to check for 404 errors in logs

---

## 6. Documentation Tasks

18. [ ] **Update infrastructure documentation**
    - [ ] Document ALB listener rule structure
    - [ ] Add diagram showing HTTP vs HTTPS routing
    - [ ] Document priority numbering convention
    - [ ] Add to resource registry

19. [ ] **Update API documentation**
    - [ ] Confirm all endpoints documented use HTTPS URLs
    - [ ] Add note about HTTPS being required
    - [ ] Update example curl commands to use https://
    - [ ] Document authentication requirements

20. [ ] **Create troubleshooting guide entry**
    - [ ] Document this bug and fix
    - [ ] Add "How to check ALB listener rules"
    - [ ] Add "How to diagnose 404 errors from ALB"
    - [ ] Add to ops runbook

21. [ ] **Update deployment checklist**
    - [ ] Add step: "Verify HTTPS listener rules exist"
    - [ ] Add step: "Test HTTPS endpoints after ALB changes"
    - [ ] Add validation script to deployment process

---

## 7. Prevention Tasks

22. [ ] **Create pre-deployment validation script**
    - [ ] Script to check HTTP and HTTPS rules match
    - [ ] Verify no HTTPS listener has only default 404 action
    - [ ] Add to CI/CD pipeline

23. [ ] **Add to code review checklist**
    - [ ] "When adding HTTP listener rule, did you add HTTPS rule?"
    - [ ] "Are both HTTP and HTTPS listeners configured?"
    - [ ] "Did you test with curl over HTTPS?"

24. [ ] **Create Terraform validation tests**
    - [ ] Add test to ensure HTTPS rules exist for all HTTP rules
    - [ ] Verify listener priorities don't conflict
    - [ ] Run tests in CI/CD before apply

25. [ ] **Team knowledge sharing**
    - [ ] Document this bug in team wiki
    - [ ] Share learnings in team meeting
    - [ ] Add to onboarding documentation
    - [ ] Create architecture decision record (ADR)

---

## 8. Rollback Plan

26. [ ] **Document rollback procedure**
    - [ ] Save current Terraform state before apply
    - [ ] Document command: `terraform apply -target=-aws_lb_listener_rule.api_v1_https`
    - [ ] Test rollback in non-production first
    - [ ] Verify rollback process takes < 5 minutes

27. [ ] **Identify rollback triggers**
    - [ ] Spike in 500 errors after deployment
    - [ ] API endpoints become completely unreachable
    - [ ] Target groups go unhealthy
    - [ ] Terraform apply fails partway through

28. [ ] **Create rollback script**
    ```bash
    #!/bin/bash
    # rollback-https-rules.sh
    cd terraform_module/data-pipeline
    terraform destroy -target=aws_lb_listener_rule.api_v1_https
    terraform destroy -target=aws_lb_listener_rule.api_https
    terraform destroy -target=aws_lb_listener_rule.api_mlflow_proxy_https
    terraform destroy -target=aws_lb_listener_rule.mlflow_https
    ```

---

## 9. Deployment Steps (Ordered by Execution)

### Phase 1: Pre-Deployment (hokusai-infrastructure repo)
1. Validate Terraform configuration (Task #2)
2. Review Terraform plan (Task #4)
3. Get team approval on plan output

### Phase 2: Deployment
4. Apply Terraform changes to development (Task #3)
5. Verify resources created in AWS (Task #5)

### Phase 3: Post-Deployment Validation
6. Run manual curl tests (Task #5)
7. Run integration test suite (Task #7)
8. Test with third-party user (Task #9)
9. Check for regressions (Task #10)

### Phase 4: Monitoring & Documentation
10. Set up CloudWatch alarms (Tasks #15-16)
11. Update documentation (Tasks #18-21)
12. Share learnings with team (Task #25)

---

## Dependencies

```
Task 2 (Terraform validate) → Task 3 (Deploy)
Task 3 (Deploy) → Task 5 (Post-deployment validation)
Task 3 (Deploy) → Task 7 (Run integration tests)
Task 3 (Deploy) → Task 9 (Validate with third party)

Task 6 (Create tests) can run parallel to Task 1-3
Tasks 18-21 (Documentation) can run parallel to Tasks 1-5
```

---

## Success Criteria

- [x] Terraform changes applied successfully
- [ ] All 4 HTTPS listener rules created in AWS
- [ ] Integration tests pass 100%
- [ ] Third-party user confirms fix
- [ ] No regressions in existing endpoints
- [ ] CloudWatch alarms configured
- [ ] Documentation updated
- [ ] Team notified of fix

---

## Estimated Timeline

- **Phase 1 (Pre-Deployment):** 30 minutes
- **Phase 2 (Deployment):** 15 minutes
- **Phase 3 (Validation):** 1-2 hours
- **Phase 4 (Monitoring & Docs):** 2-3 hours
- **Total:** ~4-6 hours

---

## Risk Assessment

### Low Risk
- Changes are additive (no existing rules modified)
- Can be rolled back quickly
- Affects only HTTPS traffic (HTTP unaffected)

### Mitigation
- Deploy during low-traffic window
- Have rollback script ready
- Monitor ALB metrics during and after deployment
- Keep team available for 30 minutes post-deployment
