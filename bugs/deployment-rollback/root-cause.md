# Root Cause Analysis: ECS Deployment Rollbacks

## Executive Summary

**Root Cause**: Application code in `src/api/utils/config.py` does not properly construct Redis URLs for TLS connections, resulting in malformed URLs that fail redis-py client validation. This causes health checks to report "degraded" status, which triggers ECS circuit breaker rollbacks.

**Impact**: 100% deployment failure rate since October 1, 2025. All code deployments roll back within 2-3 minutes due to health check failures.

**Fix Complexity**: Low - requires code change in one file to add URL scheme validation and TLS support.

---

## Technical Explanation

### The Bug

**File**: [`src/api/utils/config.py`](src/api/utils/config.py) lines 220-247

The `redis_url` property has two critical flaws:

#### Flaw 1: No URL Validation (Line 223-224)
```python
@property
def redis_url(self) -> str:
    # Check for explicit REDIS_URL first
    if redis_url := os.getenv("REDIS_URL"):
        return redis_url  # ← Returns whatever is in env var, no validation!
```

**Problem**: If `REDIS_URL` environment variable contains a bare hostname (without `redis://` or `rediss://` scheme), the code returns it as-is without validation or correction.

**Current State**:
- SSM Parameter `/hokusai/development/redis/endpoint` = `master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com`
- Task definition maps this to `REDIS_URL` environment variable
- Application receives: `REDIS_URL="master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com"`
- Code returns bare hostname to redis-py client
- redis-py rejects it with: `ValueError: Redis URL must specify one of the following schemes (redis://, rediss://, unix://)`

#### Flaw 2: No TLS Support (Line 239)
```python
if auth_token:
    # ElastiCache authenticated connection
    return f"redis://:{auth_token}@{host}:{port}/0"  # ← Always uses redis://, never rediss://!
```

**Problem**: Even when building URL from components, code always uses `redis://` scheme, never `rediss://` for TLS connections.

**Current State**:
- Task definition has `REDIS_TLS_ENABLED=true`
- Code never checks this environment variable
- AWS ElastiCache Redis cluster requires TLS (`rediss://` scheme)
- Application attempts non-TLS connection (`redis://`) which would fail even if URL format were correct

### Why This Wasn't Caught Earlier

1. **Configuration Drift**: Recent infrastructure changes updated SSM parameters to store bare hostnames instead of full URLs
2. **Silent Degradation**: Health check returns HTTP 200 even when Redis fails, masking the severity
3. **Incomplete Testing**: No unit tests for Redis URL construction with various input formats
4. **Missing Validation**: No pre-deployment checks for Redis connectivity
5. **Environment Differences**: May have worked in development with different Redis configuration

### The Cascading Failure

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Task Starts                                                  │
│    REDIS_URL="master.hokusai-redis-development....com"         │
│    REDIS_TLS_ENABLED="true"                                    │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Health Check Runs (/health endpoint)                        │
│    check_redis_connection() called                             │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Config Property Accessed                                     │
│    settings.redis_url → returns bare hostname (no scheme)      │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Redis Client Init                                            │
│    redis.Redis.from_url("master.hokusai-redis...com")         │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. redis-py URL Validation                                      │
│    ValueError: Redis URL must specify scheme                   │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Health Check Result                                          │
│    status: "degraded" (HTTP 200)                               │
│    services.redis: "unhealthy"                                 │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. ALB Target Health Check                                      │
│    Target marked unhealthy                                      │
│    (fails to reach healthy threshold)                           │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 8. ECS Circuit Breaker                                          │
│    Counts consecutive unhealthy checks                          │
│    Threshold reached (2-3 failures)                             │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 9. Deployment Rollback                                          │
│    "deployment failed: tasks failed to start"                   │
│    Service reverts to previous task definition                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Impact Assessment

### Severity: **CRITICAL**

- **Deployment Blockage**: 100% of deployments roll back
- **Feature Delivery**: Cannot deploy Model 21 (LSCOR) with HuggingFace token
- **Security Risk**: Cannot deploy security patches or bug fixes
- **Development Velocity**: Team unable to release any changes

### Affected Components

#### Directly Affected
- `hokusai-api-development` ECS service (all deployments fail)
- Health check endpoint (`/health`)
- Redis connectivity monitoring
- Model serving functionality (degraded mode)

#### Indirectly Affected
- Model 21 (LSCOR): Infrastructure ready but cannot deploy
- CI/CD pipeline: All deployment attempts fail
- Development workflow: Cannot test changes in development environment

#### Not Affected
- `hokusai-mlflow-development` (separate Redis configuration)
- `hokusai-auth-development` (uses different services)
- Existing stable deployment (v141 continues running)

### Timeline

- **Oct 1, 2025 09:03 AM**: Task definition v143 created with HuggingFace secret
- **Oct 1, 2025 10:34 AM**: Deployment attempted
- **Oct 1, 2025 10:45 AM**: Circuit breaker triggered rollback
- **Oct 1, 2025 10:47 AM**: Service rolled back to v141
- **Ongoing**: Every subsequent deployment attempt fails with same issue

---

## Related Code Sections

### Primary Culprit
**File**: [`src/api/utils/config.py`](src/api/utils/config.py#L220-L247)
```python
@property
def redis_url(self) -> str:
    """Build Redis URL from components or environment variables."""
    # Check for explicit REDIS_URL first
    if redis_url := os.getenv("REDIS_URL"):
        return redis_url  # BUG: No validation or scheme addition

    # Build from components
    host = os.getenv("REDIS_HOST")
    port = os.getenv("REDIS_PORT", str(self.redis_port))
    auth_token = os.getenv("REDIS_AUTH_TOKEN")

    if auth_token:
        return f"redis://:{auth_token}@{host}:{port}/0"  # BUG: Always redis://, never rediss://
    else:
        return f"redis://{host}:{port}/0"  # BUG: No TLS support
```

### Health Check Using Redis
**File**: [`src/api/routes/health.py`](src/api/routes/health.py#L119-L124)
```python
def check_redis_connection(timeout: float = None) -> tuple[bool, str]:
    redis = _get_redis()

    # Create Redis client with timeouts
    r = redis.Redis.from_url(
        settings.redis_url,  # ← Receives malformed URL here
        socket_connect_timeout=timeout,
        socket_timeout=timeout,
        health_check_interval=30
    )

    result = r.ping()  # Never reaches this due to ValueError in from_url()
```

### Configuration Source
**SSM Parameter**: `/hokusai/development/redis/endpoint`
```
Current Value: master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com
Expected Value: rediss://master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com:6379
```

**Task Definition v143**: `hokusai-api-development:143`
```json
{
  "secrets": [
    {
      "name": "REDIS_URL",
      "valueFrom": "/hokusai/development/redis/endpoint"
    }
  ],
  "environment": [
    {
      "name": "REDIS_TLS_ENABLED",
      "value": "true"
    }
  ]
}
```

---

## Why This Bug Exists

### Historical Context
1. **Original Implementation**: Code may have been written when Redis URL was stored as full URL in SSM
2. **Infrastructure Changes**: SSM parameters recently updated to store components (host, port) separately
3. **Incomplete Migration**: Code not updated when infrastructure configuration changed
4. **Missing Requirements**: `REDIS_TLS_ENABLED` added to task definition but not implemented in code

### Design Issues
1. **No Input Validation**: Code assumes environment variables are well-formed
2. **Silent Failures**: Health check degradation doesn't fail deployments immediately
3. **Configuration Complexity**: Multiple ways to configure Redis (URL vs components) without clear precedence
4. **Missing Documentation**: No clear specification of required Redis URL format

### Testing Gaps
1. **No Unit Tests**: Redis URL construction not covered by tests
2. **No Integration Tests**: Health check with actual Redis not tested in CI
3. **No Pre-deployment Validation**: Configuration not validated before deployment
4. **No Configuration Tests**: SSM parameter format not validated

---

## Lessons Learned

### What Went Wrong
1. **Configuration as Code**: Infrastructure changes (SSM parameters) not synchronized with application code
2. **Insufficient Validation**: Application assumed valid inputs without checking
3. **Silent Degradation**: Health check returns HTTP 200 even when services fail, masking issues
4. **Missing Monitoring**: No alerts for repeated health check degradation

### What Went Right
1. **Circuit Breaker Worked**: ECS circuit breaker correctly prevented unhealthy deployment
2. **Rollback Successful**: Service remained available on previous version (v141)
3. **Investigation Tools**: CloudWatch logs provided clear error messages
4. **Fast Root Cause**: Systematic debugging identified issue quickly

### Prevention Strategies
1. **Configuration Validation**: Add startup checks for critical configuration
2. **Pre-deployment Tests**: Validate configuration before deploying
3. **Health Check Clarity**: Return 503 for critical service failures, not 200 with degraded status
4. **Integration Tests**: Test actual Redis connections in CI pipeline
5. **Configuration Documentation**: Document expected format for all configuration values
6. **Deployment Monitoring**: Alert on repeated deployment rollbacks

---

## Fix Requirements

### Must Fix
1. ✅ Add URL scheme validation and correction in `redis_url` property
2. ✅ Implement TLS support based on `REDIS_TLS_ENABLED` environment variable
3. ✅ Handle both full URLs and bare hostnames gracefully
4. ✅ Add unit tests for Redis URL construction

### Should Fix
1. ⚠️ Update SSM parameter to include proper scheme (or document current format)
2. ⚠️ Add configuration validation at application startup
3. ⚠️ Improve health check to return 503 for critical failures
4. ⚠️ Add pre-deployment configuration validation

### Nice to Have
1. 💡 Consider using `/health/alb` for ALB health checks (simpler, no dependencies)
2. 💡 Add circuit breaker monitoring and alerting
3. 💡 Document all configuration parameters and their expected formats
4. 💡 Add integration tests for health check with real dependencies

---

## References

### Files Examined
- [src/api/utils/config.py](src/api/utils/config.py) - Configuration settings
- [src/api/routes/health.py](src/api/routes/health.py) - Health check endpoints
- [DEPLOYMENT_ISSUES_2025-09-30.md](DEPLOYMENT_ISSUES_2025-09-30.md) - Previous deployment issues
- [MODEL_21_VERIFICATION_REPORT.md](MODEL_21_VERIFICATION_REPORT.md) - Model 21 documentation

### AWS Resources
- ECS Cluster: `hokusai-development`
- ECS Service: `hokusai-api-development`
- Task Definition: `hokusai-api-development:141` (stable), `hokusai-api-development:143` (failed)
- SSM Parameter: `/hokusai/development/redis/endpoint`
- ElastiCache Cluster: `hokusai-redis-development`
- CloudWatch Log Group: `/ecs/hokusai-api-development`

### Error Messages
```
ERROR:src.api.routes.health:Redis connection failed: Redis URL must specify one of the following schemes (redis://, rediss://, unix://)
ERROR:src.api.routes.health:Redis health check failed: Redis connection failed: Redis URL must specify one of the following schemes (redis://, rediss://, unix://)
INFO:src.api.routes.health:Health check completed: degraded
```

```
(service hokusai-api-development) (deployment ecs-svc/9214183178940874271) deployment failed: tasks failed to start.
(service hokusai-api-development) rolling back to deployment ecs-svc/7812920447217021088.
```

---

## Next Steps

See [`fix-tasks.md`](fix-tasks.md) for detailed implementation plan.
