# Bug Investigation: ECS Deployment Rollbacks

## Bug Summary

**Issue**: ECS deployments for the API service are regularly rolling back due to health check failures. Task definition v143 attempted to deploy with HuggingFace API key secret, but circuit breaker triggered rollback to v141.

**When it occurs**: During every deployment attempt with new task definitions

**Who/what is affected**:
- hokusai-api-development ECS service
- Model 21 (LSCOR) cannot make predictions (missing HuggingFace token)
- Model serving functionality degraded

**Business impact and severity**: **HIGH**
- Critical deployment blocker
- Model 21 infrastructure complete but cannot serve predictions
- Development velocity impacted - cannot deploy new features

## Reproduction Steps

1. Create new task definition with updated configuration
2. Update ECS service to use new task definition
3. Health checks begin executing
4. Health checks report "degraded" status due to Redis connection errors
5. ECS circuit breaker interprets degraded status as failure
6. After 2-3 failed health checks, circuit breaker triggers rollback
7. Service returns to previous stable task definition

**Required environment/configuration**: AWS ECS development cluster, ALB health checks

**Success rate of reproduction**: 100% - happens on every deployment

**Variations in behavior**: Service returns 200 OK but with "degraded" status, which may be confusing circuit breaker logic

## Affected Components

### Services/Modules:
- **hokusai-api-development** (ECS service)
- Health check endpoint (`/health`)
- Redis connection module (`src/api/routes/health.py`)
- Circuit breaker configuration (ECS deployment settings)

### Database tables involved:
- None directly affected

### API endpoints touched:
- `/health` - Primary health check endpoint used by ALB
- `/health/alb` - Simple ALB health check (not being used)
- `/ready` - Readiness probe

### Frontend components impacted:
- None directly

### Third-party dependencies:
- **AWS ElastiCache Redis** cluster
- **redis-py** library connection logic
- ECS circuit breaker service

## Initial Observations

### Error messages:
```
ERROR:src.api.routes.health:Redis connection failed: Redis URL must specify one of the following schemes (redis://, rediss://, unix://)
ERROR:src.api.routes.health:Redis health check failed: Redis connection failed: Redis URL must specify one of the following schemes (redis://, rediss://, unix://)
INFO:src.api.routes.health:Health check completed: degraded
```

### Relevant log entries:
- Health checks consistently returning "degraded" status
- Redis connection errors on every health check
- Service marked as degraded but still returning HTTP 200
- ECS events: "(deployment ecs-svc/9214183178940874271) deployment failed: tasks failed to start."

### Metrics/monitoring anomalies:
- Circuit breaker rolling back deployments
- Tasks starting but failing health checks

### Recent changes to affected areas:
- Task definition v143 added HuggingFace secret
- Multiple previous task definition revisions (131-143) attempted with secrets changes
- Previous deployment issues documented in DEPLOYMENT_ISSUES_2025-09-30.md

### Similar past issues:
- Sept 27-30: 3-day outage due to missing database secrets
- Multiple task definitions created without proper secrets configuration
- IAM permission issues with Secrets Manager access

## Data Analysis Required

### Logs to examine:
- [x] `/ecs/hokusai-api-development` CloudWatch logs (completed)
- [ ] ECS task stopped events and reasons
- [ ] ALB target health check logs

### Database queries to run:
- None required

### Metrics to review:
- [ ] ECS service deployment metrics
- [ ] Health check success/failure rates
- [ ] Target group health status over time

### Configuration to verify:
- [x] Redis URL format in SSM Parameter Store (found issue!)
- [x] Task definition secrets configuration (reviewed)
- [ ] ALB health check settings (timeout, interval, healthy threshold)
- [ ] ECS circuit breaker thresholds

## Investigation Strategy

### Priority order for investigation:
1. **CRITICAL**: Fix Redis URL format in SSM Parameter Store (missing scheme prefix)
2. **HIGH**: Verify ALB health check configuration and circuit breaker thresholds
3. **MEDIUM**: Review health check logic - should degraded services cause deployment rollback?
4. **LOW**: Consider if `/health/alb` endpoint should be used instead of `/health`

### Tools and techniques to use:
- AWS CLI for SSM/ECS configuration review
- CloudWatch Logs Insights for error pattern analysis
- ECS service event history analysis
- Health check endpoint testing

### Key questions to answer:
1. **Why is Redis URL missing the scheme prefix?** (ANSWERED: SSM parameter stores raw hostname)
2. **Should health check construct the full Redis URL from components?**
3. **Is "degraded" status acceptable or should it fail health checks?**
4. **Are circuit breaker thresholds too aggressive for gradual service degradation?**
5. **Should we use the simpler `/health/alb` endpoint for ALB health checks?**

### Success criteria for root cause identification:
- Identify why Redis URL is malformed
- Determine if health check logic should handle URL construction
- Verify if circuit breaker interprets "degraded" as "unhealthy"
- Confirm the proper Redis URL format with TLS

## Risk Assessment

### Current impact on users:
- **MEDIUM**: Model 21 cannot serve predictions (infrastructure ready but not deployed)
- **MEDIUM**: Development team cannot deploy new code
- **LOW**: Existing stable version (v141) continues serving other models

### Potential for escalation:
- **MEDIUM**: Any emergency fix attempts will also roll back
- **HIGH**: If manual intervention attempted, could destabilize currently working v141

### Security implications:
- **LOW**: No security vulnerabilities identified
- Redis TLS correctly enabled in configuration

### Data integrity concerns:
- **NONE**: Issue is infrastructure/configuration only

## Timeline

### When bug first appeared:
- Most recent occurrence: October 1, 2025, 10:45 AM EDT
- Pattern visible since: September 30, 2025 (multiple task definition attempts)

### Correlation with deployments/changes:
- **September 15**: Last successful deployment (revision 130)
- **September 15-27**: Revisions 131-133 created without proper secrets
- **September 27**: Services went down (3-day outage)
- **September 30**: Manual fixes applied for database/MLflow
- **October 1**: Attempted deployment with HuggingFace secret - rolled back

### Frequency of occurrence:
- **100%** of deployment attempts since September 15

### Patterns in timing:
- Immediate failure on health checks after task starts
- Rollback occurs within 2-3 minutes of deployment start
- Pattern consistent across all recent deployment attempts

## Root Cause Hypothesis

### Primary Hypothesis: **Malformed Redis URL**

**Evidence:**
1. SSM Parameter `/hokusai/development/redis/endpoint` contains raw hostname without scheme
2. Health check code calls `redis.Redis.from_url(settings.redis_url)` expecting full URL
3. Redis client library requires `redis://`, `rediss://`, or `unix://` scheme
4. Error message explicitly states: "Redis URL must specify one of the following schemes"

**Expected format:** `rediss://master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com:6379`
**Actual value:** `master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com`

### Secondary Hypothesis: **Health Check "degraded" Status Interpreted as Failure**

The health endpoint returns HTTP 200 with `"status": "degraded"` when Redis fails. This may be:
1. Confusing ECS/ALB health checks (expecting purely healthy/unhealthy)
2. Triggering circuit breaker due to non-"healthy" status in response body
3. Should use `/health/alb` endpoint which ignores dependencies

### Impact Chain:
```
Bad Redis URL → Redis connection fails → Health status = "degraded"
→ ALB marks target unhealthy → Circuit breaker triggered → Deployment rolled back
```

## Next Steps

1. **Test Hypothesis**: Fix Redis URL format in SSM Parameter Store or application configuration
2. **Generate Fix Tasks**: Create specific implementation tasks
3. **Validate**: Test health check with proper Redis URL
4. **Deploy**: Attempt deployment with fix and monitor results
