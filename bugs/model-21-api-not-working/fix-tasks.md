# Fix Tasks: Model 21 API Not Working (Redis Connectivity)

## Overview

**Root Cause Confirmed**: Redis ElastiCache security group only allows ingress from security group `sg-0e61190afc2502b10` (`hokusai-ecs-tasks-*`), but the current ECS API service is using security group `sg-0864e6f6aee2a5cf4` (`hokusai-data-pipeline-ecs-tasks-*`).

**Solution**: Add the current ECS security group to Redis's ingress rules.

**Priority**: Critical - Blocking all API functionality

**Estimated Time**: 30 minutes (security group update + verification)

---

## Quick Fix: Update Redis Security Group (RECOMMENDED)

### Task 1.1: Add ECS Security Group to Redis Ingress Rules

**Location**: AWS Infrastructure (Security Groups)

**Action**: Update Redis ElastiCache security group to allow ingress from current ECS security group

- [ ] **Navigate to AWS Console → EC2 → Security Groups**
  - Go to security group: `sg-0454e74e2924a7754` (Redis)

- [ ] **Add inbound rule:**
  - Type: Custom TCP
  - Port: 6379
  - Source: `sg-0864e6f6aee2a5cf4` (hokusai-data-pipeline-ecs-tasks)
  - Description: "Allow API service to connect to Redis"

- [ ] **Verify rule was added:**
  ```bash
  aws ec2 describe-security-groups \
    --group-ids sg-0454e74e2924a7754 \
    --query 'SecurityGroups[0].IpPermissions[*].[FromPort,ToPort,IpProtocol,UserIdGroupPairs[*].GroupId]' \
    --output table
  ```

**Expected Result**: Should show both security groups:
- `sg-0e61190afc2502b10` (existing)
- `sg-0864e6f6aee2a5cf4` (newly added)

---

### Task 1.2: Verify Redis Connectivity from ECS

- [ ] **Get running task ID:**
  ```bash
  TASK_ARN=$(aws ecs list-tasks --cluster hokusai-development --service-name hokusai-api-development --query 'taskArns[0]' --output text)
  echo $TASK_ARN
  ```

- [ ] **Connect to running ECS task:**
  ```bash
  aws ecs execute-command \
    --cluster hokusai-development \
    --task $TASK_ARN \
    --container hokusai-api \
    --interactive \
    --command "/bin/bash"
  ```

- [ ] **Test Redis connectivity from inside container:**
  ```bash
  # Install redis-cli if not available
  apt-get update && apt-get install -y redis-tools

  # Test connection (with TLS)
  redis-cli -h master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com \
    -p 6379 \
    --tls \
    --insecure \
    -a $REDIS_AUTH_TOKEN \
    ping
  ```

**Expected Result**: Should return `PONG`

---

### Task 1.3: Restart API Service to Clear Connection Errors

- [ ] **Force new deployment to restart tasks:**
  ```bash
  aws ecs update-service \
    --cluster hokusai-development \
    --service hokusai-api-development \
    --force-new-deployment
  ```

- [ ] **Wait for deployment to complete:**
  ```bash
  aws ecs wait services-stable \
    --cluster hokusai-development \
    --services hokusai-api-development
  ```

- [ ] **Verify new task is running:**
  ```bash
  aws ecs describe-services \
    --cluster hokusai-development \
    --services hokusai-api-development \
    --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}'
  ```

---

### Task 1.4: Verify API Health

- [ ] **Check health endpoint:**
  ```bash
  curl -s https://api.hokus.ai/health | jq
  ```

**Expected Result:**
```json
{
  "status": "healthy",
  "services": {
    "mlflow": "healthy",
    "redis": "healthy",
    "message_queue": "healthy",
    "postgres": "healthy",
    "external_api": "healthy"
  }
}
```

- [ ] **Test Model 21 prediction endpoint (without auth - should return 401):**
  ```bash
  curl -X POST https://api.hokus.ai/api/v1/models/21/predict \
    -H "Content-Type: application/json" \
    -d '{"inputs": {"company_size": 1000}}' \
    -w "\nHTTP Status: %{http_code}\n"
  ```

**Expected Result**: HTTP 401 (Unauthorized) within 1-2 seconds (not timeout)

---

### Task 1.5: Test with Valid API Key

- [ ] **Get or create test API key**
  - Contact auth service team or use existing key

- [ ] **Test prediction with valid auth:**
  ```bash
  curl -X POST https://api.hokus.ai/api/v1/models/21/predict \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${API_KEY}" \
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
        "title": "VP of Engineering"
      }
    }' \
    -w "\nHTTP Status: %{http_code}\nResponse Time: %{time_total}s\n"
  ```

**Expected Result**:
- HTTP 200
- Response time < 2 seconds
- Valid prediction response with lead_score

---

## Alternative Fix: Terraform Update (If Infrastructure as Code is Used)

### Task 2.1: Update Terraform Configuration

**If Redis security group is managed by Terraform:**

- [ ] **Find Redis security group resource in ../hokusai-infrastructure**
  ```bash
  grep -r "sg-0454e74e2924a7754\|hokusai-redis.*security" \
    ../hokusai-infrastructure/environments/development/
  ```

- [ ] **Update ingress rules to include both security groups:**
  ```hcl
  resource "aws_security_group_rule" "redis_ingress_from_ecs" {
    type                     = "ingress"
    from_port                = 6379
    to_port                  = 6379
    protocol                 = "tcp"
    security_group_id        = aws_security_group.redis.id
    source_security_group_id = aws_security_group.ecs_tasks.id
    description              = "Allow ECS API service to connect to Redis"
  }

  # Keep existing rule or add new one
  resource "aws_security_group_rule" "redis_ingress_from_old_ecs" {
    type                     = "ingress"
    from_port                = 6379
    to_port                  = 6379
    protocol                 = "tcp"
    security_group_id        = aws_security_group.redis.id
    source_security_group_id = "sg-0e61190afc2502b10"  # Old ECS security group
    description              = "Allow old ECS tasks to connect to Redis"
  }
  ```

- [ ] **Plan and apply Terraform changes:**
  ```bash
  cd ../hokusai-infrastructure/environments/development
  terraform plan
  terraform apply
  ```

---

## Validation Tasks

### Task 3.1: Verify Redis Metrics

- [ ] **Check CloudWatch metrics for Redis:**
  ```bash
  aws cloudwatch get-metric-statistics \
    --namespace AWS/ElastiCache \
    --metric-name NetworkBytesIn \
    --dimensions Name=ReplicationGroupId,Value=hokusai-redis-development \
    --start-time $(date -u -d '10 minutes ago' +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
    --period 300 \
    --statistics Sum \
    --output table
  ```

**Expected**: Should show increased network traffic after fix

### Task 3.2: Monitor CloudWatch Logs

- [ ] **Watch API logs for Redis connection success:**
  ```bash
  aws logs tail /ecs/hokusai-api-development --follow | grep -i "redis\|cache"
  ```

**Expected**:
- "Redis cache connected for auth middleware"
- No more "Redis connection failed: Timeout" errors
- "Using cached validation" messages appearing

### Task 3.3: Test Third-Party Client

- [ ] **Coordinate with third-party to test their client code**
  - Provide them with valid API key if needed
  - Ask them to run their integration test
  - Monitor logs during their test

- [ ] **Verify their client can connect:**
  - Should receive HTTP 200
  - Should get valid predictions
  - Response time < 2 seconds

### Task 3.4: Performance Testing

- [ ] **Compare response times before/after:**
  ```bash
  # Run 10 test requests and measure time
  for i in {1..10}; do
    time curl -s -X POST https://api.hokus.ai/api/v1/models/21/predict \
      -H "Authorization: Bearer ${API_KEY}" \
      -H "Content-Type: application/json" \
      -d '{"inputs": {"company_size": 1000, "industry": "Technology", "engagement_score": 75, "website_visits": 10, "email_opens": 5, "content_downloads": 3, "demo_requested": true, "budget_confirmed": false, "decision_timeline": "Q2 2025", "title": "VP"}}' \
      > /dev/null
  done
  ```

**Expected**: All requests complete in < 2 seconds (vs. 10+ seconds before)

---

## Rollback Plan

### If Security Group Update Causes Issues

- [ ] **Remove the newly added ingress rule:**
  ```bash
  # Get rule ID
  aws ec2 describe-security-groups \
    --group-ids sg-0454e74e2924a7754 \
    --query 'SecurityGroups[0].IpPermissions[?UserIdGroupPairs[?GroupId==`sg-0864e6f6aee2a5cf4`]]'

  # Revoke rule
  aws ec2 revoke-security-group-ingress \
    --group-id sg-0454e74e2924a7754 \
    --protocol tcp \
    --port 6379 \
    --source-group sg-0864e6f6aee2a5cf4
  ```

- [ ] **Service will return to "degraded" state but won't be worse**

### If Service Issues Persist After Fix

- [ ] **Check if there are other networking issues:**
  - Verify subnet routing tables
  - Check NACLs
  - Verify DNS resolution
  - Check Redis AUTH token is correct

---

## Long-Term Prevention

### Task 4.1: Infrastructure as Code

- [ ] **Ensure all security group rules are in Terraform**
  - No manual changes to security groups
  - All rules documented and version-controlled
  - Peer review required for security changes

### Task 4.2: Monitoring & Alerting

- [ ] **Create CloudWatch alarm for Redis connectivity:**
  ```bash
  aws cloudwatch put-metric-alarm \
    --alarm-name "hokusai-api-redis-connection-failures" \
    --alarm-description "Alert when API service cannot connect to Redis" \
    --metric-name "redis_connection_errors" \
    --namespace "HokusaiAPI" \
    --statistic Sum \
    --period 300 \
    --evaluation-periods 2 \
    --threshold 10 \
    --comparison-operator GreaterThanThreshold
  ```

- [ ] **Alert on "degraded" health status:**
  - Create synthetic monitor that checks /health endpoint
  - Alert if status != "healthy"
  - PagerDuty integration for critical services

### Task 4.3: Documentation

- [ ] **Update runbook with Redis troubleshooting:**
  - Document this specific issue and fix
  - Add security group verification checklist
  - Include connectivity testing procedures

- [ ] **Architecture diagram:**
  - Show Redis dependency clearly
  - Document security group relationships
  - Include network topology

### Task 4.4: Testing

- [ ] **Add integration test for Redis connectivity:**
  - Test runs as part of deployment pipeline
  - Verifies Redis connection from ECS task
  - Fails deployment if Redis unreachable

- [ ] **Chaos engineering:**
  - Regularly test with Redis unavailable
  - Verify graceful degradation works correctly
  - Measure performance impact without Redis

---

## Communication

### Task 5.1: Notify Stakeholders

- [ ] **Update Linear ticket with findings:**
  - Root cause: Security group mismatch
  - Fix: Added ECS security group to Redis ingress rules
  - Status: Fixed and verified

- [ ] **Notify third-party customer:**
  - Explain issue and resolution
  - Apologize for downtime
  - Provide updated status
  - Offer support for testing

- [ ] **Internal team notification:**
  - Post-mortem in team channel
  - Lessons learned
  - Prevention measures implemented

### Task 5.2: Post-Mortem

- [ ] **Schedule post-mortem meeting:**
  - Why did security groups get out of sync?
  - Why wasn't this caught in monitoring?
  - What alerts should have fired?
  - How to prevent similar issues?

- [ ] **Action items from post-mortem:**
  - Assign owners for prevention tasks
  - Set deadlines for improvements
  - Follow up in 2 weeks

---

## Success Criteria

- [x] Root cause identified (security group mismatch)
- [ ] Security group rule added
- [ ] Redis connectivity restored
- [ ] Health status shows "healthy" (not "degraded")
- [ ] Model 21 API responds within 2 seconds
- [ ] Third-party client can successfully make predictions
- [ ] No Redis connection errors in logs
- [ ] All automated tests pass
- [ ] Customer notified and satisfied

---

## Timeline

**Immediate (Next 30 minutes):**
1. Add security group rule (5 min)
2. Restart API service (10 min)
3. Verify health and connectivity (10 min)
4. Test with valid API key (5 min)

**Follow-up (Next 2 hours):**
5. Test with third-party client
6. Performance testing
7. Update Linear ticket
8. Notify customer

**Next Week:**
9. Post-mortem meeting
10. Implement monitoring improvements
11. Update documentation
12. Add integration tests

---

## Notes

- **Critical:** Do NOT remove the existing security group rule (`sg-0e61190afc2502b10`) as other services may still be using it
- **Coordination:** Notify other team members before making security group changes
- **Verification:** Test thoroughly in development before considering production impact
- **Documentation:** Update architecture docs to prevent future mismatches

---

## Current Status

- [x] Root cause confirmed: Security group mismatch
- [ ] Fix deployed: Waiting for security group update
- [ ] Verification complete: Pending
- [ ] Customer notified: Pending

**Next Action:** Add ECS security group to Redis ingress rules (Task 1.1)
