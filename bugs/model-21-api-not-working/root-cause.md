# Root Cause: Model 21 API Not Working

## Executive Summary

**Root Cause**: Redis ElastiCache is unreachable from the API service, causing the auth middleware to fail initialization and requests to timeout. The auth middleware attempts to ping Redis during startup with a 2-second timeout, but the connection never completes, causing the middleware to operate without caching but still attempting Redis operations on every health check.

**Severity**: Critical - All API endpoints are degraded due to Redis connectivity failure

**Impact**:
- Third-party clients cannot use Model 21 (or any API endpoint)
- All prediction requests timeout
- API service reports "degraded" health status
- Redis health check shows "unhealthy"

**Fix Complexity**: Medium - Requires either:
1. Fix Redis connectivity (infrastructure issue)
2. Improve Redis failure handling in auth middleware
3. Make auth middleware fully functional without Redis

---

## Technical Root Cause

### Problem: Redis ElastiCache Unreachable

The API service at `hokusai-api-development` cannot connect to Redis ElastiCache instance.

#### Evidence from Logs

**CloudWatch Logs** (`/ecs/hokusai-api-development`):
```
ERROR:src.api.routes.health:Redis connection failed: Timeout connecting to server
ERROR:src.api.routes.health:Redis health check failed: Redis connection failed: Timeout connecting to server
ERROR:src.events.publishers.factory:Failed to create Redis publisher: Failed to connect to Redis: Timeout connecting to server
WARNING:src.events.publishers.factory:Redis publisher creation/test failed: Failed to connect to Redis: Timeout connecting to server
```

**Redis Configuration** (from logs):
```
WARNING:src.api.utils.config:REDIS_URL missing scheme, will prepend based on TLS setting. Original value: master.hokusai-redis-development.lenvj6.use1.cache...
INFO:src.api.utils.config:Constructed Redis URL with rediss:// scheme and port. TLS enabled: True, Auth: enabled
```

**Health Endpoint Response:**
```json
{
  "status": "degraded",
  "services": {
    "mlflow": "healthy",
    "redis": "unhealthy",
    "message_queue": "degraded",
    "postgres": "healthy",
    "external_api": "healthy"
  }
}
```

---

## How This Breaks Model 21 API

### Request Flow (Normal)

1. Client → ALB → ECS Task (hokusai-api-development)
2. Request hits `APIKeyAuthMiddleware`
3. Middleware checks Redis cache for API key validation
4. If not cached, validates with auth service
5. Caches result in Redis
6. Passes request to endpoint handler
7. Endpoint returns prediction

### Request Flow (Current - Broken)

1. Client → ALB → ECS Task
2. Request hits `APIKeyAuthMiddleware`
3. Middleware attempts to read from Redis cache → **TIMEOUT (2+ seconds)**
4. Falls back to auth service validation
5. Auth service validation succeeds
6. Middleware attempts to write to Redis cache → **TIMEOUT (2+ seconds)**
7. After **10+ seconds total**, request times out before reaching endpoint
8. Client receives no response (connection timeout)

### Auth Middleware Initialization

**Location:** [src/middleware/auth.py:91-139](src/middleware/auth.py#L91-L139)

```python
# Initialize cache if not provided
if cache is None:
    try:
        # Build Redis URL...
        redis_url = f"rediss://{redis_host}:{redis_port}/0"

        self.cache = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,  # 2 second connection timeout
            socket_timeout=2,
            ssl_cert_reqs=None,  # Allow self-signed certs for ElastiCache
        )
        # Test connection with timeout
        self.cache.ping()  # ← THIS TIMES OUT
        logger.info("Redis cache connected for auth middleware")
    except Exception as e:
        # Cache is optional - continue without it
        logger.warning(f"Redis cache not available: {e}")
        self.cache = None  # ← Middleware continues without cache
```

**The Problem:**
- Line 129: `self.cache.ping()` times out after 2 seconds
- Exception is caught and `self.cache` is set to `None`
- Middleware continues without Redis caching
- **BUT** health checks and other parts of the code still try to use Redis
- Each Redis operation adds 2+ seconds of timeout delay

### Why Requests Timeout

Even though the middleware **should** work without Redis (line 137 sets `self.cache = None`), the following still happens:

1. **Health checks** repeatedly try to connect to Redis (adding delays)
2. **Event publishers** try to connect to Redis (adding delays)
3. **Message queue** tries to connect to Redis (degraded status)
4. Multiple components timing out → cumulative delay exceeds client timeout
5. Client gives up after 10 seconds (default timeout in client code)

---

## Why Redis is Unreachable

### Possible Causes

#### 1. Security Group Configuration ❓
- ECS security group may not allow outbound traffic to Redis port (6379)
- Redis security group may not allow inbound traffic from ECS

#### 2. Network Configuration ❓
- VPC routing issue
- Subnet configuration changed
- NACLs blocking traffic

#### 3. Redis Instance Down ❓
- ElastiCache cluster stopped or terminated
- Failover in progress
- Maintenance window

#### 4. Wrong Redis Endpoint ❓
- Environment variable contains incorrect endpoint
- DNS resolution failing for `master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com`
- Port mismatch (using 6379 but ElastiCache on different port)

#### 5. TLS/Auth Configuration Issue ❓
- Using `rediss://` (TLS) but ElastiCache not configured for encryption in transit
- Auth token incorrect or missing
- Certificate validation failing

### Investigation Needed

- [ ] Verify Redis ElastiCache instance exists and is running
- [ ] Check ElastiCache cluster endpoint matches environment variable
- [ ] Verify security groups allow traffic between ECS and ElastiCache
- [ ] Check if ElastiCache encryption-in-transit is enabled
- [ ] Verify AUTH token if ElastiCache has auth enabled
- [ ] Test connectivity from ECS task to Redis endpoint
- [ ] Check recent infrastructure changes

---

## Why Previous Investigation Mentioned 405 Error

The previous investigation in [bugs/api-id-21-connection-405-error/](../api-id-21-connection-405-error/) mentioned a **405 Method Not Allowed** error. Current testing shows **timeout** instead.

**Possible Explanations:**
1. **Different environment** - Previous investigation was in different deployment
2. **Problem evolved** - Redis was working then, broke recently
3. **Client configuration** - Previous client had shorter timeout, got 405 before timeout
4. **ALB behavior changed** - Load balancer routing rules modified

The **405 error** was likely a **red herring**. The real issue has always been Redis connectivity, but manifested differently depending on timeout configurations.

---

## Impact Assessment

### Current Impact

**Critical:**
- **All API endpoints affected** (not just Model 21)
- Auth middleware delays every request by 4+ seconds (2s cache read timeout + 2s cache write timeout)
- Cumulative delays cause client timeouts
- Health status "degraded" alerts monitoring systems
- Customer integration completely blocked

**Performance:**
- No Redis caching → Auth service called on every request
- Auth service load increases significantly
- Response times unacceptable (10+ seconds vs expected <1s)

**Cascading Effects:**
- Message queue degraded (likely also uses Redis)
- Event publishing failing
- Potential memory leaks if uncached data accumulates

### Affected Users

**External Customers:**
- Third-party using Model 21 API (immediate issue)
- Any customer using Hokusai API (broader issue)
- All prediction endpoints non-functional

**Internal Services:**
- Any service depending on hokusai-api
- Integration tests likely failing
- Monitoring/alerting triggered

### Business Impact

- **Revenue loss:** Customers cannot use paid API service
- **SLA breach:** If customers have availability SLAs
- **Reputation damage:** External developers blocked
- **Support overhead:** Customers reporting issues
- **Development blocked:** Cannot test or deploy changes

---

## Related Code Sections

### Auth Middleware
**File:** [src/middleware/auth.py](src/middleware/auth.py)

**Key Lines:**
- **Line 91-139:** Redis initialization with 2-second timeout
- **Line 129:** `self.cache.ping()` that times out
- **Line 134-137:** Exception handling (sets `self.cache = None`)
- **Line 420-433:** Cache read with timeout
- **Line 439-455:** Cache write with timeout

### Health Check
**File:** [src/api/routes/health.py](src/api/routes/health.py)

**Redis Health Check:** Repeatedly tries to connect, logs errors every 2 seconds

### Event Publishers
**File:** [src/events/publishers/factory.py](src/events/publishers/factory.py)

**Fallback Logic:** Falls back to non-Redis publisher when Redis unavailable

---

## Why It Wasn't Caught Earlier

### 1. Gradual Degradation
- Service still "works" without Redis (returns 200 on /health)
- Health status shows "degraded" not "unhealthy"
- No alerts configured for "degraded" status
- Load balancer health checks still pass (just slower)

### 2. Insufficient Monitoring
- No alerts on Redis connectivity failures
- No tracking of auth middleware latency
- No end-to-end API tests in production
- CloudWatch alarms not configured for this scenario

### 3. Infrastructure Change Not Communicated
- Redis ElastiCache may have been modified/terminated
- Security group rules may have changed
- No change log correlating infrastructure changes to API failures

### 4. Testing Gaps
- Integration tests may not actually call Redis
- Development environment may not use Redis at all
- Staging environment may have working Redis (but prod doesn't)

### 5. Graceful Degradation Masking Issue
- Middleware "handles" Redis failures by continuing without cache
- But doesn't handle them **well** (still times out on every operation)
- Health endpoint shows "degraded" but service stays up
- Appears to work until you actually try to use it

---

## Recommended Fix Strategy

### Option 1: Fix Redis Connectivity (Infrastructure - Recommended)

**Pros:**
- Addresses root cause
- Restores caching functionality
- Improves performance
- Returns service to full health

**Cons:**
- Requires infrastructure access/changes
- May take longer if complex networking issue
- Need to understand why it broke

**Steps:**
1. Identify why Redis is unreachable
2. Fix network, security groups, or Redis configuration
3. Verify connectivity from ECS task
4. Restart API service to clear connection errors
5. Monitor for successful Redis connections

### Option 2: Improve Redis Failure Handling (Code - Quick Fix)

**Pros:**
- Can deploy quickly
- Service works without Redis
- Reduces timeout delays
- Unblocks customers immediately

**Cons:**
- Loses caching benefits
- Increased load on auth service
- Slower response times (but acceptable)
- Doesn't fix underlying infrastructure issue

**Implementation:**
```python
# src/middleware/auth.py line 91-139

# Option A: Reduce timeouts dramatically
self.cache = redis.from_url(
    redis_url,
    decode_responses=True,
    socket_connect_timeout=0.1,  # ← Changed from 2 to 0.1 seconds
    socket_timeout=0.1,           # ← Changed from 2 to 0.1 seconds
    ssl_cert_reqs=None,
)

# Option B: Skip Redis entirely if ping fails quickly
try:
    self.cache = redis.from_url(redis_url, ...)
    with async_timeout.timeout(0.5):  # Only wait 0.5s for ping
        self.cache.ping()
    logger.info("Redis cache connected")
except (asyncio.TimeoutError, redis.ConnectionError, redis.TimeoutError) as e:
    logger.warning(f"Redis unavailable, continuing without cache: {e}")
    self.cache = None

# Option C: Make Redis completely optional
if os.getenv("ENABLE_REDIS_CACHE", "false").lower() == "true":
    # Only try Redis if explicitly enabled
    try:
        self.cache = redis.from_url(redis_url, ...)
    except Exception as e:
        logger.warning(f"Redis cache failed: {e}")
        self.cache = None
else:
    logger.info("Redis caching disabled, using auth service directly")
    self.cache = None
```

### Option 3: Hybrid Approach (Best)

1. **Immediate:** Deploy code fix (Option 2) to unblock customers
2. **Parallel:** Investigate and fix Redis infrastructure issue
3. **Follow-up:** Revert code fix once Redis is healthy
4. **Long-term:** Add monitoring and alerts to catch this earlier

---

## Prevention Measures

### 1. Infrastructure Monitoring
- [ ] CloudWatch alarm for Redis connection failures
- [ ] CloudWatch alarm for ElastiCache health
- [ ] Alert on "degraded" health status (not just "unhealthy")
- [ ] Network connectivity monitoring between ECS and ElastiCache

### 2. Better Error Handling
- [ ] Reduce Redis timeouts (2s → 0.1s)
- [ ] Fast-fail on Redis unavailability
- [ ] Circuit breaker pattern for Redis connections
- [ ] Graceful degradation with minimal latency impact

### 3. Testing
- [ ] Integration tests that verify Redis connectivity
- [ ] Load tests with Redis disabled to measure impact
- [ ] Chaos engineering: regularly test with Redis unavailable
- [ ] Synthetic monitoring to catch issues before customers

### 4. Documentation
- [ ] Document Redis dependency clearly
- [ ] Runbook for Redis connectivity issues
- [ ] Architecture diagram showing Redis dependency
- [ ] Troubleshooting guide for timeout issues

### 5. Configuration
- [ ] Feature flag for Redis caching
- [ ] Environment variable to disable Redis
- [ ] Configurable timeouts (not hardcoded)
- [ ] Clear logging when Redis is unavailable

---

## Next Steps

See [fix-tasks.md](fix-tasks.md) for detailed implementation tasks.

## Conclusion

The Model 21 API (and all Hokusai API endpoints) are timing out because:

1. **Redis ElastiCache is unreachable** from the ECS service
2. **Auth middleware tries to connect** with 2-second timeout
3. **Every request times out** waiting for Redis operations (read + write = 4+ seconds minimum)
4. **Cumulative timeouts** cause requests to exceed client timeout (10s)
5. **Clients receive no response** and report "API not working"

**The 405 error** from the previous investigation was likely unrelated or a different manifestation of the same underlying timeout issue.

**Primary recommendation:** Fix Redis connectivity as soon as possible while deploying code changes to handle Redis failures more gracefully.

**Secondary recommendation:** Add comprehensive monitoring and alerting for Redis health to catch this type of issue immediately in the future.

**Immediate action:** Deploy timeout reduction or Redis-optional code to unblock customers while infrastructure fix is in progress.
