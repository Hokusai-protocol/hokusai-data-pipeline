# Validation Checklist for API 404 HTTPS Fix

## Bug Fix Summary
**Fixed:** Missing HTTPS listener rules causing 404 errors on all `/api/v1/*` endpoints

**Repositories:**
- ✅ `hokusai-infrastructure` - Added 4 HTTPS listener rules
- ✅ `hokusai-data-pipeline` - Added integration tests and documentation

---

## Pre-Deployment Validation

### Infrastructure Code Review
- [ ] Terraform code reviewed and approved
- [ ] No syntax errors in `listeners.tf`
- [ ] Listener rule priorities don't conflict (85, 95, 100, 200)
- [ ] All 4 rules target correct target groups
- [ ] Rules use correct listener ARN (`main_https[0]`)

### Terraform Plan Review
```bash
cd /Users/timothyogilvie/Dropbox/Hokusai/hokusai-infrastructure/environments
terraform plan
```

**Expected Output:**
- [ ] 4 new resources to be added (aws_lb_listener_rule)
- [ ] 0 resources to be changed
- [ ] 0 resources to be destroyed
- [ ] Plan shows resources:
  - [ ] aws_lb_listener_rule.api_v1_https
  - [ ] aws_lb_listener_rule.api_https
  - [ ] aws_lb_listener_rule.api_mlflow_proxy_https
  - [ ] aws_lb_listener_rule.mlflow_https

---

## Deployment Steps

1. [ ] **Backup current state**
   ```bash
   cd environments
   terraform state pull > backup-$(date +%Y%m%d-%H%M%S).tfstate
   ```

2. [ ] **Apply Terraform changes**
   ```bash
   terraform apply
   # Review plan
   # Type 'yes' to confirm
   ```

3. [ ] **Verify resources created**
   ```bash
   # Check ALB listener rules
   aws elbv2 describe-rules \
     --listener-arn <HTTPS-LISTENER-ARN> \
     --query 'Rules[*].[Priority,Conditions[0].Values[0]]' \
     --output table
   ```

   **Expected:** See priorities 85, 95, 100, 200 with /api paths

---

## Post-Deployment Validation

### 1. AWS Console Verification
- [ ] Open AWS Console → EC2 → Load Balancers
- [ ] Find `hokusai-main-development` ALB
- [ ] Click "Listeners" tab
- [ ] Click on HTTPS:443 listener
- [ ] Verify 4 new rules visible:
  - [ ] Priority 85: `/api/mlflow/*` → API target group
  - [ ] Priority 95: `/api/v1/*` → API target group
  - [ ] Priority 100: `/api*` → API target group
  - [ ] Priority 200: `/mlflow/*` → MLflow target group

### 2. Target Health Check
```bash
# Check API service target health
aws elbv2 describe-target-health \
  --target-group-arn <API-TARGET-GROUP-ARN>
```

- [ ] All targets show "healthy" status
- [ ] No "unhealthy" or "draining" targets

### 3. Manual HTTPS Endpoint Testing

#### Test 1: Health Endpoint
```bash
curl -v https://api.hokus.ai/health
```

**Expected:**
- [ ] HTTP 200 OK
- [ ] Content-Type: application/json
- [ ] Response body contains health status
- [ ] **NOT** plain text "Not Found"
- [ ] **NOT** HTTP 404

#### Test 2: Model Info Endpoint (Without Auth)
```bash
curl -v https://api.hokus.ai/api/v1/models/21/info
```

**Expected:**
- [ ] HTTP 401 Unauthorized (auth required)
- [ ] Content-Type: application/json
- [ ] JSON error message about missing API key
- [ ] **NOT** HTTP 404
- [ ] **NOT** plain text "Not Found"

#### Test 3: Model Info Endpoint (With Auth)
```bash
curl -v https://api.hokus.ai/api/v1/models/21/info \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Expected:**
- [ ] HTTP 200 OK
- [ ] Content-Type: application/json
- [ ] JSON response with model info
- [ ] **NOT** HTTP 404

#### Test 4: Model Predict Endpoint
```bash
curl -X POST https://api.hokus.ai/api/v1/models/21/predict \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"company_size": 500, "industry": "Technology", "engagement_score": 75}}'
```

**Expected:**
- [ ] HTTP 200 OK or 400 (validation error)
- [ ] Content-Type: application/json
- [ ] JSON response (prediction or error)
- [ ] **NOT** HTTP 404

#### Test 5: Model Health Endpoint
```bash
curl -v https://api.hokus.ai/api/v1/models/21/health \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Expected:**
- [ ] HTTP 200 OK
- [ ] Content-Type: application/json
- [ ] JSON response with health status
- [ ] **NOT** HTTP 404

### 4. Integration Test Suite

```bash
cd /Users/timothyogilvie/Dropbox/Hokusai/hokusai-data-pipeline

# Set environment variables
export HOKUSAI_API_KEY="your-api-key-here"
export API_BASE_URL="https://api.hokus.ai"

# Run integration tests
pytest tests/integration/test_https_model_serving_endpoints.py -v
```

**Expected:**
- [ ] All tests pass (100% success rate)
- [ ] No 404 errors reported
- [ ] All assertions about JSON responses pass
- [ ] Authentication tests pass

### 5. Third-Party User Validation

- [ ] Contact third-party user who reported the bug
- [ ] Ask them to retry their integration
- [ ] Confirm they can successfully call Model ID 21 endpoints
- [ ] Verify they receive JSON responses, not HTML 404
- [ ] Get written confirmation that issue is resolved

### 6. Regression Testing

Test that existing endpoints still work:

#### MLflow Endpoints
```bash
curl -v https://registry.hokus.ai/mlflow/
```
- [ ] Returns MLflow UI (HTML or redirect)

#### Auth Endpoints
```bash
curl -v https://auth.hokus.ai/health
```
- [ ] Returns 200 OK with JSON

#### API Health
```bash
curl -v https://api.hokus.ai/api/health
```
- [ ] Returns 200 OK with JSON

---

## Performance Validation

### 7. Check Latency Metrics

```bash
# View ALB metrics in CloudWatch
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name TargetResponseTime \
  --dimensions Name=LoadBalancer,Value=<ALB-NAME> \
  --start-time $(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average
```

**Expected:**
- [ ] Average response time < 200ms
- [ ] No significant increase from baseline
- [ ] No spikes in latency

### 8. Check Error Rates

```bash
# Check 4XX errors
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name HTTPCode_Target_4XX_Count \
  --dimensions Name=LoadBalancer,Value=<ALB-NAME> \
  --start-time $(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

**Expected:**
- [ ] 404 count has decreased significantly
- [ ] 401 count may increase (auth working properly)
- [ ] No unexpected error spikes

---

## Monitoring Setup

### 9. CloudWatch Alarms

- [ ] Create alarm for 404 rate > 10/minute
  ```bash
  aws cloudwatch put-metric-alarm \
    --alarm-name api-404-rate-high \
    --alarm-description "Alert when 404 rate is high" \
    --metric-name HTTPCode_Target_4XX_Count \
    --namespace AWS/ApplicationELB \
    --statistic Sum \
    --period 300 \
    --threshold 50 \
    --comparison-operator GreaterThanThreshold
  ```

- [ ] Create alarm for target unhealthy
- [ ] Configure SNS notifications
- [ ] Test alarms trigger correctly

---

## Rollback Plan (If Needed)

### If Issues Occur:

1. **Immediate Rollback**
   ```bash
   cd /Users/timothyogilvie/Dropbox/Hokusai/hokusai-infrastructure/environments

   # Remove new rules
   terraform destroy \
     -target=aws_lb_listener_rule.api_v1_https \
     -target=aws_lb_listener_rule.api_https \
     -target=aws_lb_listener_rule.api_mlflow_proxy_https \
     -target=aws_lb_listener_rule.mlflow_https
   ```

2. **Verify Rollback**
   - [ ] HTTPS listener back to default 404 action
   - [ ] HTTP endpoints still work
   - [ ] No errors in Terraform

3. **Restore from Backup (if needed)**
   ```bash
   terraform state push backup-YYYYMMDD-HHMMSS.tfstate
   ```

### Rollback Triggers:
- [ ] ALB becomes completely unreachable
- [ ] Spike in 500 errors
- [ ] All API endpoints return errors
- [ ] Target groups go unhealthy

---

## Sign-Off

### Pre-Deployment
- [ ] Code reviewed by: ___________________
- [ ] Terraform plan approved by: ___________________
- [ ] Date: ___________________

### Post-Deployment
- [ ] All validation tests passed
- [ ] Third-party user confirmed fix
- [ ] No regressions detected
- [ ] Monitoring configured
- [ ] Documentation updated
- [ ] Deployed by: ___________________
- [ ] Date: ___________________

---

## Success Criteria (ALL must be checked)

- [ ] ✅ All 4 HTTPS listener rules created successfully
- [ ] ✅ HTTPS requests to `/api/v1/*` return JSON, NOT 404
- [ ] ✅ Model ID 21 endpoints accessible via HTTPS
- [ ] ✅ Integration tests pass 100%
- [ ] ✅ Third-party user confirms issue resolved
- [ ] ✅ No regressions in existing endpoints
- [ ] ✅ Performance metrics within acceptable range
- [ ] ✅ CloudWatch alarms configured
- [ ] ✅ Documentation updated

---

## Notes

**Date Deployed:** ___________________

**Issues Encountered:**




**Additional Testing Performed:**




**Follow-up Actions:**
