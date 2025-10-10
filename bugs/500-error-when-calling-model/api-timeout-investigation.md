# API Timeout Investigation

## Issue Summary

**Problem:** After deploying the fix for HUGGINGFACE_API_KEY, the API is timing out on all requests, preventing validation of the fix.

**Status:** ✅ Root cause identified - Security group configuration not applied

---

## Symptoms

1. ✅ ECS task running successfully (revision 151 with HUGGINGFACE_API_KEY)
2. ❌ ALB health checks failing: `Target.Timeout` - "Request timed out"
3. ❌ All API endpoints timing out (30+ seconds)
4. ⚠️ Health check endpoint responding with HTTP 200 but taking >2 seconds

---

## Investigation Timeline

### Step 1: ECS Task Health ✅

**Command:**
```bash
aws ecs describe-tasks --cluster hokusai-development \
  --tasks <task-arn> \
  --query 'tasks[0].{lastStatus:lastStatus,healthStatus:healthStatus}'
```

**Result:**
```json
{
  "lastStatus": "RUNNING",
  "healthStatus": "UNKNOWN",
  "connectivity": "CONNECTED"
}
```

**Finding:** Task is running but health status is UNKNOWN (ALB hasn't marked it healthy)

---

### Step 2: ALB Target Health ❌

**Command:**
```bash
aws elbv2 describe-target-health \
  --target-group-arn <api-target-group-arn>
```

**Result:**
```json
{
  "TargetHealth": {
    "State": "unhealthy",
    "Reason": "Target.Timeout",
    "Description": "Request timed out"
  }
}
```

**Health Check Configuration:**
- Path: `/health`
- Protocol: HTTP
- Timeout: **5 seconds**
- Interval: 30 seconds

**Finding:** ALB health checks are timing out after 5 seconds

---

### Step 3: API Log Analysis 🔍

**Logs:**
```
14:10:41.613 INFO: Health check requested
14:10:41.687 WARNING: REDIS_URL missing scheme
14:10:43.692 ERROR: Redis connection failed: Timeout connecting to server
14:10:43.692 ERROR: Redis health check failed: Redis connection failed
14:10:43.708 INFO: Health check completed: degraded
14:10:43.709 INFO: "GET /health HTTP/1.1" 200 OK
```

**Finding:**
- Health check is **responding with HTTP 200**
- BUT it takes **~2 seconds** due to Redis connection timeout
- ALB timeout is 5 seconds, so occasionally the response doesn't arrive in time
- The Redis connection is consistently failing/timing out

---

### Step 4: Redis Status ✅

**Command:**
```bash
aws elasticache describe-replication-groups \
  --replication-group-id hokusai-redis-development
```

**Result:**
```json
{
  "Status": "available",
  "PrimaryEndpoint": {
    "Address": "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com",
    "Port": 6379
  }
}
```

**Finding:** Redis is running and available

---

### Step 5: Security Group Analysis ❌

**Redis Security Group: `sg-0454e74e2924a7754`**

Allowed inbound traffic from:
- `sg-0e61190afc2502b10` (Original ECS tasks security group) ✅

**API Service Security Group: `sg-0864e6f6aee2a5cf4`**

Current security group used by API service:
- Name: `hokusai-data-pipeline-ecs-tasks`
- ID: `sg-0864e6f6aee2a5cf4`

**Finding:** **MISMATCH!**

Redis allows traffic from `sg-0e61190afc2502b10`, but API is using `sg-0864e6f6aee2a5cf4`.

---

## Root Cause: Security Group Configuration Drift

### Expected Configuration (Terraform)

**File:** `redis-queue.tf`

```hcl
# Security group rule for data pipeline service access to Redis
resource "aws_security_group_rule" "redis_from_data_pipeline_ecs" {
  type                     = "ingress"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  security_group_id        = module.redis_queue.security_group_id
  source_security_group_id = aws_security_group.ecs_tasks.id  # Data pipeline SG
  description              = "Redis access from data pipeline ECS tasks"
}
```

**Purpose:** Allow data pipeline ECS tasks (using `sg-0864e6f6aee2a5cf4`) to access Redis.

### Actual Configuration (AWS)

**Verification:**
```bash
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=sg-0454e74e2924a7754" \
  --query 'SecurityGroupRules[?ReferencedGroupInfo.GroupId==`sg-0864e6f6aee2a5cf4`]'

# Result: []  (RULE DOES NOT EXIST)
```

**Finding:** The security group rule `redis_from_data_pipeline_ecs` is defined in Terraform but was **never applied** to AWS.

---

## Why This Happened

### Same Root Cause as HUGGINGFACE_API_KEY Issue

1. **Terraform configuration added** to `redis-queue.tf`
2. **`terraform apply` never executed** OR partially failed
3. **Configuration exists in code but not in AWS** (configuration drift)

### Evidence from Earlier Terraform Apply

When we ran `terraform apply tfplan-api-fix`, we saw these errors:

```
Error: setting ELBv2 Load Balancer subnets: At least two subnets in two different Availability Zones must be specified

Error: updating ElastiCache Subnet Group: SubnetInUse: The subnet ID is in use

Error: creating ElastiCache Parameter Group: Parameter group already exists
```

These errors likely **prevented the security group rule from being created** during the same apply.

---

## Impact

### Cascade of Effects

1. ❌ Redis connection fails → Health check slow (>2 seconds)
2. ❌ Health check slow → ALB marks target unhealthy
3. ❌ ALB marks target unhealthy → Removes from load balancer
4. ❌ Removed from load balancer → All API requests timeout
5. ❌ All API requests timeout → Cannot validate HUGGINGFACE_API_KEY fix

### Affected Functionality

- ✅ HUGGINGFACE_API_KEY fix is deployed (primary bug FIXED)
- ❌ Cannot validate fix due to API being unreachable
- ❌ Health checks failing
- ❌ Redis-dependent features broken (caching, pub/sub)
- ❌ External API users blocked

---

## Solution

### Option 1: Apply Terraform Configuration (Recommended)

**Required Actions:**

1. **Navigate to infrastructure repo**
   ```bash
   cd /Users/timothyogilvie/Dropbox/Hokusai/hokusai-infrastructure/environments
   ```

2. **Target specific resource to avoid ALB errors**
   ```bash
   terraform apply \
     -target=aws_security_group_rule.redis_from_data_pipeline_ecs
   ```

3. **Verify rule was created**
   ```bash
   aws ec2 describe-security-group-rules \
     --filters "Name=group-id,Values=sg-0454e74e2924a7754" \
     --region us-east-1 \
     --query 'SecurityGroupRules[?ReferencedGroupInfo.GroupId==`sg-0864e6f6aee2a5cf4`]'
   ```

4. **Wait for health checks to pass** (30-60 seconds)

5. **Verify ALB target health**
   ```bash
   aws elbv2 describe-target-health \
     --target-group-arn <api-target-group-arn> \
     --region us-east-1
   ```

**Expected Timeline:** 2-3 minutes

---

### Option 2: Manually Add Security Group Rule (Emergency)

**If Terraform has issues:**

```bash
aws ec2 authorize-security-group-ingress \
  --group-id sg-0454e74e2924a7754 \
  --protocol tcp \
  --port 6379 \
  --source-group sg-0864e6f6aee2a5cf4 \
  --region us-east-1
```

**⚠️ Warning:** This creates configuration drift (AWS ≠ Terraform)

---

### Option 3: Temporarily Switch Security Groups

**Quick workaround (not recommended for production):**

Update the API service to use the old security group:

```bash
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-api-development \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-08cb7663096ac0017],securityGroups=[sg-0e61190afc2502b10],assignPublicIp=DISABLED}" \
  --region us-east-1
```

**⚠️ Warning:** Reverts to old security group; may affect other features

---

## Verification Steps

Once the security group rule is in place:

### 1. Check Redis Connection from API
```bash
aws logs tail /ecs/hokusai-api-development --since 2m | grep -i redis
```

Expected: No more "Redis connection failed" errors

### 2. Check Health Check Response Time
```bash
aws logs tail /ecs/hokusai-api-development --since 2m | grep "Health check"
```

Expected: Health checks completing in <1 second

### 3. Check ALB Target Health
```bash
aws elbv2 describe-target-health \
  --target-group-arn <arn> \
  --region us-east-1 \
  --query 'TargetHealthDescriptions[*].TargetHealth.State'
```

Expected: `"healthy"`

### 4. Test API Endpoint
```bash
curl https://api.hokus.ai/health
```

Expected: Immediate response with HTTP 200

### 5. Test Model ID 21
```bash
curl -X POST https://api.hokus.ai/api/v1/models/21/predict \
  -H "X-API-Key: ${HOKUSAI_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"company_size": 1000, "engagement_score": 75}}'
```

Expected: HTTP 200 with prediction results (not 500 "HuggingFace token not configured")

---

## Lessons Learned

### Infrastructure Configuration Drift

**Problem:** Multiple Terraform configurations exist in code but were never applied to AWS.

**Examples Found:**
1. ✅ **FIXED:** `HUGGINGFACE_API_KEY` secret in ECS task definition
2. ⏳ **PENDING:** Security group rule for Redis access

**Why This Happens:**
- Manual `terraform apply` process
- Failed applies due to unrelated errors (ALB subnet issues)
- No automated verification of drift

### Proposed Solutions

1. **Automated Drift Detection**
   ```bash
   # In CI/CD pipeline
   terraform plan -detailed-exitcode
   # Exit code 2 = changes detected but not applied
   ```

2. **Targeted Applies**
   ```bash
   # Apply specific resources to avoid cascading failures
   terraform apply -target=resource.name
   ```

3. **Post-Deployment Verification**
   ```bash
   # Verify critical resources after deployment
   ./scripts/verify-deployment.sh
   ```

4. **Separate Terraform Workspaces**
   - Data pipeline resources
   - Networking resources
   - Security resources

   This prevents one failure from blocking all changes.

---

## Summary

### Primary Bug (FIXED ✅)
- **Issue:** HUGGINGFACE_API_KEY missing
- **Root Cause:** Configuration drift
- **Fix Applied:** Terraform apply, ECS redeployment
- **Status:** Deployed to revision 151

### Secondary Issue (IDENTIFIED 🔍)
- **Issue:** API timing out, health checks failing
- **Root Cause:** Security group rule not applied
- **Fix Required:** Apply Terraform for `redis_from_data_pipeline_ecs`
- **Status:** Solution identified, ready to implement

### Blocking Validation
The primary bug fix cannot be validated until the security group issue is resolved and the API becomes responsive.

---

## Next Steps

1. ✅ **Document investigation** (this file)
2. ⏭️ **Apply security group rule** (Option 1 recommended)
3. ⏭️ **Wait for health checks to pass**
4. ⏭️ **Validate HUGGINGFACE_API_KEY fix** (test Model ID 21)
5. ⏭️ **Notify third-party tester**
6. ⏭️ **Create PR for documentation**
7. ⏭️ **Implement drift detection** (longer-term)

**Estimated time to fix:** 5-10 minutes
**Estimated time for validation:** Additional 5-10 minutes

---

## Sign-off

- [x] Root cause identified (security group rule missing)
- [x] Solution documented
- [ ] Fix applied (pending approval)
- [ ] Validation complete (pending fix)

**Documented by:** Claude (AI Assistant)
**Date:** 2025-10-07
**Related Bug:** 500 error when calling model (primary bug fixed, validation blocked)
