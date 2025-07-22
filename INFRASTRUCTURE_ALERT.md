# CRITICAL: Authentication Service Down

**Alert Time**: 2025-07-22 08:58 UTC  
**Severity**: CRITICAL  
**Impact**: Complete blockage of all API operations

## Issue Summary

The authentication service at `auth.hokus.ai` is completely offline, returning 503 Service Temporarily Unavailable errors on all endpoints. This prevents:

- Third-party model registration
- All API key validations
- Any authenticated API operations
- MLflow access through the proxy

## Affected Services

| Service | Status | Error |
|---------|--------|-------|
| auth.hokus.ai | ❌ DOWN | 503 Service Temporarily Unavailable |
| registry.hokus.ai/api/ | ⚠️ Degraded | Cannot validate auth - returns "Authentication service error" |
| MLflow | ✅ Running | Direct access works, but proxy auth blocked |

## Immediate Actions Required

1. **Check ECS Tasks**
   ```bash
   aws ecs list-tasks --cluster hokusai-cluster --service-name auth-service
   aws ecs describe-tasks --cluster hokusai-cluster --tasks <task-arn>
   ```

2. **Check CloudWatch Logs**
   ```bash
   aws logs tail /ecs/hokusai-auth --since 1h
   ```

3. **Verify ALB Target Health**
   ```bash
   aws elbv2 describe-target-health --target-group-arn <auth-service-tg-arn>
   ```

4. **Check Database Connectivity**
   - Verify RDS is accessible
   - Check security groups
   - Verify credentials haven't changed

## Test Results

All authentication attempts fail with 503:
- Direct validation: `POST /api/v1/keys/validate` → 503
- Health check: `GET /health` → 503  
- Root endpoint: `GET /` → 503
- All service_id values tested (including "platform")

## Recovery Steps

1. **Restart Service**
   ```bash
   aws ecs update-service --cluster hokusai-cluster --service auth-service --force-new-deployment
   ```

2. **Scale Up If Needed**
   ```bash
   aws ecs update-service --cluster hokusai-cluster --service auth-service --desired-count 2
   ```

3. **Check Resource Limits**
   - CPU/Memory allocation
   - Task definition limits
   - Container health checks

## Contact

If the service doesn't recover within 15 minutes, escalate to:
- Platform Team Lead
- On-call DevOps Engineer

## Verification

Once service is restored, verify with:
```bash
curl -X POST https://auth.hokus.ai/api/v1/keys/validate \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{"service_id": "platform", "client_ip": "127.0.0.1"}'
```

Expected: 200 OK response with validation details