# Root Cause Hypotheses: ECS Deployment Rollbacks

## Hypothesis Summary Table
| # | Hypothesis | Confidence | Complexity | Impact if True |
|---|------------|------------|------------|----------------|
| 1 | Redis URL missing scheme prefix (rediss://) | **High (90%)** | Simple | **Critical** |
| 2 | Health check "degraded" status triggers circuit breaker | Medium (50%) | Medium | High |
| 3 | Circuit breaker thresholds too aggressive | Low (20%) | Simple | Medium |
| 4 | Application constructing Redis URL incorrectly | Low (15%) | Medium | High |

## Detailed Hypotheses

### Hypothesis 1: Redis URL Missing Scheme Prefix
**Confidence**: High (90%)
**Category**: Configuration Error

#### Description
The SSM Parameter Store value for `/hokusai/development/redis/endpoint` contains only the hostname without the required URL scheme prefix. The redis-py library requires URLs to start with `redis://`, `rediss://`, or `unix://`. When the health check attempts to connect using this incomplete URL, the Redis client throws a validation error, causing the health check to report "degraded" status.

#### Supporting Evidence
1. **Direct evidence**: SSM parameter value is `master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com` (no scheme)
2. **Error message**: "Redis URL must specify one of the following schemes (redis://, rediss://, unix://)"
3. **Consistent failures**: Every single health check shows this same error
4. **Task definition**: REDIS_URL secret references this malformed parameter
5. **Code context**: Line 119 in `health.py` calls `redis.Redis.from_url(settings.redis_url)` expecting full URL
6. **Working config elsewhere**: Redis TLS is correctly enabled (`REDIS_TLS_ENABLED=true`), suggesting intent to use `rediss://`

#### Why This Causes the Bug
```
Deployment starts
→ Task reads REDIS_URL from SSM: "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com"
→ Health check runs (/health endpoint)
→ check_redis_connection() calls redis.Redis.from_url(settings.redis_url)
→ redis-py validates URL format
→ Validation fails: URL must have scheme (redis://, rediss://, unix://)
→ Exception raised: "Redis URL must specify one of the following schemes..."
→ Health check returns status="degraded" (HTTP 200)
→ ALB/ECS marks target as unhealthy
→ Circuit breaker counts unhealthy checks
→ After threshold reached, deployment rolled back
```

#### Test Method
1. **Check current SSM value**:
   ```bash
   aws ssm get-parameter --name "/hokusai/development/redis/endpoint" --region us-east-1
   ```
   Expected if TRUE: Value is bare hostname
   Expected if FALSE: Value includes `rediss://` prefix

2. **Test Redis connection with fixed URL**:
   ```python
   import redis
   # Current (broken)
   redis.Redis.from_url("master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com")  # Should fail

   # Fixed
   redis.Redis.from_url("rediss://master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com:6379")  # Should succeed
   ```

3. **Update SSM parameter with proper scheme**:
   ```bash
   aws ssm put-parameter \
     --name "/hokusai/development/redis/endpoint" \
     --value "rediss://master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com:6379" \
     --type "String" \
     --overwrite \
     --region us-east-1
   ```

4. **Restart service and check health**:
   - Force new deployment
   - Watch CloudWatch logs for Redis connection errors
   - Verify health check returns "healthy" not "degraded"

Expected if TRUE: Redis errors disappear, health check becomes healthy, deployment succeeds
Expected if FALSE: Same errors persist, health check still degraded

#### Code/Configuration to Check
```bash
# Check SSM parameter
aws ssm get-parameter --name "/hokusai/development/redis/endpoint" --region us-east-1

# Check how Redis URL is used in code
src/api/routes/health.py:119 - redis.Redis.from_url(settings.redis_url)
src/api/utils/config.py - How settings.redis_url is loaded

# Check task definition environment/secrets
aws ecs describe-task-definition --task-definition hokusai-api-development:143 --query 'taskDefinition.containerDefinitions[0].secrets'
```

#### Quick Fix Test
Update SSM parameter to include scheme:
```bash
aws ssm put-parameter \
  --name "/hokusai/development/redis/endpoint" \
  --value "rediss://master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com:6379" \
  --type "String" \
  --overwrite \
  --region us-east-1
```

This immediate test will confirm if this is the root cause without code changes.

---

### Hypothesis 2: Health Check "Degraded" Status Triggers Circuit Breaker
**Confidence**: Medium (50%)
**Category**: Service Health Logic

#### Description
The `/health` endpoint returns HTTP 200 with `status: "degraded"` when optional services (like Redis) fail. However, ALB health checks may be parsing the response body and marking targets unhealthy when `status != "healthy"`. ECS circuit breaker interprets consecutive unhealthy targets as deployment failure.

Alternatively, the application should use the simpler `/health/alb` endpoint (line 334-341) which only checks if the service is running, not dependencies.

#### Supporting Evidence
1. **Health check always returns "degraded"**: Logs show `Health check completed: degraded` repeatedly
2. **HTTP 200 still returned**: Service not returning 503, yet deployment fails
3. **Unused ALB endpoint exists**: `/health/alb` endpoint designed specifically for ALB checks
4. **Circuit breaker triggers**: "deployment failed: tasks failed to start" despite tasks running
5. **Code comment**: "This endpoint is specifically for ALB health checks and doesn't check dependencies to avoid cascading failures"

#### Why This Causes the Bug
```
Health check runs
→ Redis fails (due to Hypothesis 1 or other reason)
→ Overall status = "degraded" (line 292 in health.py)
→ Returns HTTP 200 with {"status": "degraded"}
→ ALB health check configured to check response body
→ ALB marks target unhealthy (expecting "healthy" in body)
→ Circuit breaker counts unhealthy checks
→ Deployment rolled back
```

#### Test Method
1. **Check ALB health check configuration**:
   ```bash
   aws elbv2 describe-target-groups \
     --names hokusai-reg-api-development \
     --region us-east-1 \
     --query 'TargetGroups[0].HealthCheckPath'
   ```
   Expected if TRUE: Path is `/health` (checking dependencies)
   Expected if FALSE: Path is `/health/alb` (simple check)

2. **Review ALB health check matcher**:
   ```bash
   aws elbv2 describe-target-groups \
     --names hokusai-reg-api-development \
     --region us-east-1 \
     --query 'TargetGroups[0].Matcher'
   ```
   Check if it's parsing response body for specific status

3. **Test with simpler endpoint**:
   - Update ALB health check path to `/health/alb`
   - Attempt deployment
   - Check if deployment succeeds even with Redis degraded

Expected if TRUE: Using `/health/alb` allows deployment to succeed
Expected if FALSE: Deployment still fails even with simpler health check

#### Code/Configuration to Check
```bash
# Check current ALB target group health check configuration
aws elbv2 describe-target-groups --region us-east-1 | jq '.TargetGroups[] | select(.TargetGroupName | contains("hokusai-reg-api-development")) | {HealthCheckPath, Matcher, HealthCheckIntervalSeconds, HealthyThresholdCount, UnhealthyThresholdCount}'

# Review health endpoint logic
src/api/routes/health.py:172-331 - Full health check with dependencies
src/api/routes/health.py:334-341 - Simple ALB health check

# Check ECS service health check configuration
aws ecs describe-services --cluster hokusai-development --services hokusai-api-development --query 'services[0].healthCheckGracePeriodSeconds'
```

#### Quick Fix Test
Switch ALB to use simpler health check:
```bash
# Get target group ARN first
TG_ARN=$(aws elbv2 describe-target-groups --names hokusai-reg-api-development --query 'TargetGroups[0].TargetGroupArn' --output text --region us-east-1)

# Update health check path
aws elbv2 modify-target-group \
  --target-group-arn $TG_ARN \
  --health-check-path "/health/alb" \
  --region us-east-1
```

---

### Hypothesis 3: Circuit Breaker Thresholds Too Aggressive
**Confidence**: Low (20%)
**Category**: ECS Configuration

#### Description
ECS deployment circuit breaker may have thresholds that are too strict, triggering rollback before the service has time to stabilize. Health checks during startup may temporarily fail as dependencies initialize, causing premature rollback.

#### Supporting Evidence
1. **Quick rollback**: Deployment fails within 2-3 minutes
2. **Pattern of immediate failure**: No grace period for service warmup
3. **Logs show healthy service**: Service is running and responding, just degraded
4. **Multiple recent rollbacks**: Every deployment attempt rolls back

#### Why This Causes the Bug
```
Deployment starts
→ New task starts
→ Health checks begin immediately
→ Service still initializing (Redis connection pooling, etc.)
→ First few health checks fail or return degraded
→ Circuit breaker: 2 consecutive failures threshold met
→ Rollback triggered before service fully initialized
```

#### Test Method
1. **Check circuit breaker configuration**:
   ```bash
   aws ecs describe-services --cluster hokusai-development --services hokusai-api-development --query 'services[0].deploymentConfiguration.deploymentCircuitBreaker' --region us-east-1
   ```

2. **Check health check grace period**:
   ```bash
   aws ecs describe-services --cluster hokusai-development --services hokusai-api-development --query 'services[0].healthCheckGracePeriodSeconds' --region us-east-1
   ```

3. **Review ALB health check thresholds**:
   ```bash
   aws elbv2 describe-target-groups --names hokusai-reg-api-development --query 'TargetGroups[0].{Interval: HealthCheckIntervalSeconds, Timeout: HealthCheckTimeoutSeconds, HealthyThreshold: HealthyThresholdCount, UnhealthyThreshold: UnhealthyThresholdCount}' --region us-east-1
   ```

Expected if TRUE: Thresholds are 2-3 failures, interval is 10-15s, no grace period
Expected if FALSE: Reasonable thresholds (5+ failures, 30s+ grace period)

#### Code/Configuration to Check
```bash
# ECS service deployment configuration
aws ecs describe-services --cluster hokusai-development --services hokusai-api-development --query 'services[0].deploymentConfiguration' --region us-east-1

# ALB target group health check settings
aws elbv2 describe-target-groups --names hokusai-reg-api-development --region us-east-1
```

#### Quick Fix Test
Increase health check grace period and unhealthy threshold:
```bash
# Update ECS service
aws ecs update-service \
  --cluster hokusai-development \
  --service hokusai-api-development \
  --health-check-grace-period-seconds 180 \
  --region us-east-1

# Update ALB target group
aws elbv2 modify-target-group \
  --target-group-arn $TG_ARN \
  --unhealthy-threshold-count 5 \
  --health-check-interval-seconds 30 \
  --region us-east-1
```

---

### Hypothesis 4: Application Constructing Redis URL Incorrectly
**Confidence**: Low (15%)
**Category**: Application Logic

#### Description
The application may have code that attempts to construct the Redis URL from components (host, port, scheme) but is doing so incorrectly, resulting in a malformed URL even if SSM parameters are correct.

#### Supporting Evidence
1. **Multiple environment variables**: Task definition has REDIS_URL, REDIS_HOST, REDIS_PORT, REDIS_TLS_ENABLED
2. **Potential logic error**: Code may be reading wrong variable or constructing URL incorrectly
3. **TLS enabled**: REDIS_TLS_ENABLED=true suggests intent to use rediss:// but error shows no scheme

#### Why This Causes the Bug
```
Application startup
→ Reads REDIS_HOST from SSM (hostname only)
→ Reads REDIS_TLS_ENABLED=true
→ Should construct: "rediss://{host}:{port}"
→ But instead uses: settings.redis_url = REDIS_HOST (no scheme)
→ Health check fails with scheme validation error
```

#### Test Method
1. **Review config loading code**:
   ```python
   # Check src/api/utils/config.py
   # How is settings.redis_url set?
   # Does it construct from components or read directly?
   ```

2. **Check environment variables at runtime**:
   ```bash
   # Exec into running container
   aws ecs execute-command --cluster hokusai-development --task <task-id> --command "/bin/sh"

   # Inside container:
   echo $REDIS_URL
   echo $REDIS_HOST
   echo $REDIS_PORT
   echo $REDIS_TLS_ENABLED
   ```

3. **Test URL construction logic**:
   Add debug logging to show exactly what redis_url value is being used

Expected if TRUE: Code shows URL construction logic with bugs
Expected if FALSE: Settings directly use SSM value without modification

#### Code/Configuration to Check
```python
# Check configuration module
src/api/utils/config.py

# Look for redis_url property or method
# Check if it constructs URL from components
# Verify scheme is added when TLS is enabled
```

---

## Testing Priority Order

1. **Start with Hypothesis 1** (90% confidence)
   - Simplest to test (just check SSM parameter value)
   - Direct evidence (error message explicitly states missing scheme)
   - Quick fix (update SSM parameter)
   - If confirmed, fix is immediate and requires no code changes

2. **If Hypothesis 1 is false (or only partially solves it), test Hypothesis 2** (50% confidence)
   - Check ALB health check configuration
   - Test using `/health/alb` endpoint instead
   - Addresses cascading failure prevention

3. **If both above fail, test Hypothesis 3** (20% confidence)
   - Review circuit breaker thresholds
   - May be contributing factor even if not root cause

4. **Only if all above fail, investigate Hypothesis 4** (15% confidence)
   - More complex to test (requires code review)
   - Less direct evidence
   - Would require code changes to fix

## Alternative Hypotheses to Consider if All Above Fail

- **IAM permissions**: Task execution role cannot read updated SSM parameters (unlikely, working for v141)
- **Network issues**: Redis cluster unreachable from ECS tasks (unlikely, would affect v141 too)
- **Redis cluster unhealthy**: ElastiCache cluster actually down (check CloudWatch metrics)
- **Secrets Manager timeout**: Secrets taking too long to fetch at startup (check task startup logs)
- **Container startup order**: Redis connection attempted before all configs loaded (race condition)
- **ECS task definition caching**: Old task definition cached, updates not taking effect (unlikely)
- **ALB target registration delay**: Targets marked unhealthy before fully registered (check registration time)

## Data Needed for Further Investigation

If initial hypotheses don't pan out, gather:

### Configuration Data
- Complete ECS task definition JSON (all revisions 141-143)
- All SSM parameters: `/hokusai/development/redis/*`
- All Secrets Manager secrets: `hokusai/redis/development/*`
- ALB target group full configuration
- ECS service deployment configuration

### Runtime Data
- Environment variables inside running v141 task
- Environment variables inside failed v143 task (if logs available)
- Health check responses from both versions
- ALB access logs during failed deployment

### Metrics
- CloudWatch metrics for ElastiCache cluster health
- ECS service deployment metrics (task count, health status)
- ALB target health state changes timeline
- Health check latency and failure counts

### Logs
- Complete CloudWatch logs for stopped v143 tasks
- ECS service event history (full list, not just recent)
- ALB access logs for health check requests
- Application debug logs with Redis connection details
