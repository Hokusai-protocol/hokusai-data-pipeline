# Fix Tasks: ECS Deployment Rollback Bug

**Bug**: Redis URL malformed, causing health check failures and deployment rollbacks
**Root Cause**: `src/api/utils/config.py` doesn't validate Redis URL format or support TLS
**Target**: Fix code to handle both full URLs and bare hostnames, support TLS connections

---

## 1. Immediate Fix (CRITICAL - Priority P0)

### Task 1.1: Fix Redis URL Construction Logic
- [ ] Update `redis_url` property in `src/api/utils/config.py` (lines 220-247)
  - [ ] Add validation: Check if REDIS_URL has scheme prefix
  - [ ] Add scheme correction: Prepend appropriate scheme if missing
  - [ ] Implement TLS support: Check `REDIS_TLS_ENABLED` environment variable
  - [ ] Add port handling: Include port in URL if not already present
  - [ ] Handle edge cases: Empty strings, localhost, IPv6 addresses

**Implementation Details**:
```python
@property
def redis_url(self) -> str:
    """Build Redis URL from components or environment variables with TLS support."""
    logger = logging.getLogger(__name__)

    # Check for explicit REDIS_URL first
    if redis_url := os.getenv("REDIS_URL"):
        # Validate and fix URL format if needed
        if not redis_url.startswith(("redis://", "rediss://", "unix://")):
            logger.warning(f"REDIS_URL missing scheme, will prepend based on TLS setting: {redis_url}")
            tls_enabled = os.getenv("REDIS_TLS_ENABLED", "false").lower() == "true"
            scheme = "rediss" if tls_enabled else "redis"

            # Add default port if not in URL
            if ":" not in redis_url or redis_url.count(":") == 0:
                port = os.getenv("REDIS_PORT", str(self.redis_port))
                redis_url = f"{scheme}://{redis_url}:{port}"
            else:
                redis_url = f"{scheme}://{redis_url}"

        logger.info(f"Using Redis URL from environment: {redis_url.split('@')[-1]}")  # Hide auth token in logs
        return redis_url

    # Build from components
    host = os.getenv("REDIS_HOST")
    if not host:
        raise ValueError(
            "Redis configuration missing: REDIS_HOST or REDIS_URL must be set. "
            "Redis will not fall back to localhost - explicit configuration required."
        )

    port = os.getenv("REDIS_PORT", str(self.redis_port))
    auth_token = os.getenv("REDIS_AUTH_TOKEN")
    tls_enabled = os.getenv("REDIS_TLS_ENABLED", "false").lower() == "true"

    # Use rediss:// for TLS connections, redis:// for non-TLS
    scheme = "rediss" if tls_enabled else "redis"

    if auth_token:
        # ElastiCache authenticated connection with TLS support
        url = f"{scheme}://:{auth_token}@{host}:{port}/0"
        logger.info(f"Built Redis URL from components with auth: {scheme}://<auth>@{host}:{port}/0")
        return url
    else:
        # Unauthenticated connection (development only)
        logger.warning(
            f"Redis connection without authentication to {host}:{port} - "
            "this should only be used in development"
        )
        return f"{scheme}://{host}:{port}/0"
```

**Dependencies**: None
**Estimated Time**: 1 hour
**Priority**: P0 - Blocking all deployments

---

### Task 1.2: Add Configuration Validation at Startup
- [ ] Create `validate_redis_configuration()` method in Settings class
  - [ ] Verify Redis URL format is valid
  - [ ] Check TLS setting matches URL scheme
  - [ ] Warn if configuration seems incorrect
  - [ ] Don't fail startup (Redis may be optional)

**Implementation Location**: `src/api/utils/config.py` - add to Settings class

**Dependencies**: Task 1.1
**Estimated Time**: 30 minutes
**Priority**: P0

---

## 2. Testing Tasks (HIGH - Priority P1)

### Task 2.1: Write Unit Tests for Redis URL Construction
- [ ] Create test file: `tests/unit/test_redis_url_config.py`
  - [ ] Test: Full URL with scheme is returned as-is
    ```python
    def test_redis_url_with_scheme():
        os.environ["REDIS_URL"] = "redis://localhost:6379"
        assert settings.redis_url == "redis://localhost:6379"
    ```
  - [ ] Test: Bare hostname gets scheme prepended (no TLS)
    ```python
    def test_redis_url_bare_hostname_no_tls():
        os.environ["REDIS_URL"] = "localhost"
        os.environ["REDIS_TLS_ENABLED"] = "false"
        assert settings.redis_url.startswith("redis://localhost")
    ```
  - [ ] Test: Bare hostname gets rediss:// when TLS enabled
    ```python
    def test_redis_url_bare_hostname_with_tls():
        os.environ["REDIS_URL"] = "master.redis.amazonaws.com"
        os.environ["REDIS_TLS_ENABLED"] = "true"
        assert settings.redis_url.startswith("rediss://master.redis")
    ```
  - [ ] Test: URL built from components with TLS
    ```python
    def test_redis_url_from_components_with_tls():
        os.environ["REDIS_HOST"] = "redis.example.com"
        os.environ["REDIS_PORT"] = "6379"
        os.environ["REDIS_AUTH_TOKEN"] = "secret123"
        os.environ["REDIS_TLS_ENABLED"] = "true"
        assert settings.redis_url == "rediss://:secret123@redis.example.com:6379/0"
    ```
  - [ ] Test: URL built from components without TLS
  - [ ] Test: Missing configuration raises ValueError
  - [ ] Test: Port added when missing from bare hostname
  - [ ] Test: Auth token properly included in URL

**Dependencies**: Task 1.1 (tests should fail before fix, pass after)
**Estimated Time**: 2 hours
**Priority**: P1

---

### Task 2.2: Write Integration Test for Health Check with Redis
- [ ] Create test file: `tests/integration/test_health_check_redis.py`
  - [ ] Test: Health check passes with valid Redis URL
  - [ ] Test: Health check degrades gracefully with invalid Redis URL
  - [ ] Test: Health check respects TLS setting
  - [ ] Test: Mock Redis responses for various scenarios
  - [ ] Test: Verify error messages are helpful

**Dependencies**: Task 1.1, 1.2
**Estimated Time**: 1.5 hours
**Priority**: P1

---

### Task 2.3: Add Test for Deployment Scenario
- [ ] Create test: `tests/integration/test_deployment_configuration.py`
  - [ ] Test: Simulate SSM parameter with bare hostname
  - [ ] Test: Verify application handles it correctly
  - [ ] Test: Simulate various REDIS_TLS_ENABLED values
  - [ ] Test: Verify all environment variable combinations

**Dependencies**: Task 1.1, 1.2
**Estimated Time**: 1 hour
**Priority**: P1

---

## 3. Validation Tasks (HIGH - Priority P1)

### Task 3.1: Local Testing
- [ ] Test fix locally with various Redis configurations
  - [ ] Test with local Redis (no TLS): `REDIS_URL=localhost`
  - [ ] Test with full URL: `REDIS_URL=redis://localhost:6379`
  - [ ] Test with bare hostname: `REDIS_URL=master.redis.amazonaws.com`
  - [ ] Test with TLS enabled: `REDIS_TLS_ENABLED=true`
  - [ ] Test with components: `REDIS_HOST`, `REDIS_PORT`, `REDIS_AUTH_TOKEN`
  - [ ] Verify health check returns "healthy" not "degraded"

**Dependencies**: Task 1.1, 2.1
**Estimated Time**: 1 hour
**Priority**: P1

---

### Task 3.2: Validate Against Original Bug
- [ ] Reproduce original failure scenario
  - [ ] Set REDIS_URL to bare hostname (as in SSM parameter)
  - [ ] Set REDIS_TLS_ENABLED=true
  - [ ] Run health check
  - [ ] Verify: No ValueError about missing scheme
  - [ ] Verify: Health check returns "healthy" or "degraded" appropriately
  - [ ] Verify: Connection attempt uses rediss:// scheme

**Dependencies**: Task 1.1, 2.1, 3.1
**Estimated Time**: 30 minutes
**Priority**: P1

---

### Task 3.3: Deploy to Development Environment
- [ ] Build Docker image with fix
  - [ ] Ensure platform is `linux/amd64` (see CLAUDE.md)
  - [ ] Tag image appropriately
  - [ ] Push to ECR
- [ ] Update ECS task definition to new image
- [ ] Deploy to hokusai-api-development service
  - [ ] Monitor CloudWatch logs for Redis errors
  - [ ] Verify health check passes
  - [ ] Verify deployment completes without rollback
  - [ ] Check service is healthy in ECS console
- [ ] Test Model 21 predictions work with HuggingFace token

**Dependencies**: Task 1.1, 2.1, 3.1, 3.2
**Estimated Time**: 1 hour (including build and deploy time)
**Priority**: P1

---

## 4. Code Quality Tasks (MEDIUM - Priority P2)

### Task 4.1: Add Comprehensive Code Comments
- [ ] Document `redis_url` property behavior
  - [ ] Explain URL validation logic
  - [ ] Explain TLS scheme selection
  - [ ] Document expected environment variable formats
  - [ ] Add examples in docstring

**Dependencies**: Task 1.1
**Estimated Time**: 30 minutes
**Priority**: P2

---

### Task 4.2: Add Type Hints and Validation
- [ ] Add type hints to all new/modified methods
- [ ] Use `typing.Optional` for nullable values
- [ ] Consider using `pydantic` validators for URL format

**Dependencies**: Task 1.1
**Estimated Time**: 30 minutes
**Priority**: P2

---

### Task 4.3: Improve Error Messages
- [ ] Make ValueError messages more helpful
  - [ ] Include current configuration values (sanitized)
  - [ ] Suggest correct format
  - [ ] Link to documentation

**Dependencies**: Task 1.1
**Estimated Time**: 20 minutes
**Priority**: P2

---

## 5. Monitoring & Observability (HIGH - Priority P1)

### Task 5.1: Add Configuration Logging
- [ ] Log Redis configuration at startup (INFO level)
  - [ ] Log scheme used (redis vs rediss)
  - [ ] Log hostname (hide auth token)
  - [ ] Log TLS setting
  - [ ] Log configuration source (REDIS_URL vs components)

**Dependencies**: Task 1.1
**Estimated Time**: 20 minutes
**Priority**: P1

---

### Task 5.2: Add Health Check Logging
- [ ] Improve Redis health check error logging
  - [ ] Log the actual Redis URL being used (sanitized)
  - [ ] Log TLS setting
  - [ ] Log connection attempt details
  - [ ] Distinguish between URL format errors vs connection errors

**Dependencies**: Task 1.1
**Estimated Time**: 30 minutes
**Priority**: P1

---

### Task 5.3: Create CloudWatch Alarm (Optional)
- [ ] Create alarm for repeated health check degradation
  - [ ] Trigger after 5+ consecutive degraded health checks
  - [ ] Send to SNS topic for ops team
  - [ ] Include troubleshooting link in alarm description

**Dependencies**: Task 3.3 (deployment to dev)
**Estimated Time**: 30 minutes
**Priority**: P2 (nice to have)

---

## 6. Documentation Tasks (MEDIUM - Priority P2)

### Task 6.1: Update Configuration Documentation
- [ ] Create or update `docs/configuration/redis.md`
  - [ ] Document all Redis configuration options
  - [ ] Provide examples for each configuration method
  - [ ] Document TLS requirements for AWS ElastiCache
  - [ ] Add troubleshooting section

**Dependencies**: Task 1.1
**Estimated Time**: 1 hour
**Priority**: P2

---

### Task 6.2: Update Deployment Troubleshooting Guide
- [ ] Add section: "Deployment Rollback Due to Health Check Failures"
  - [ ] Symptoms: Circuit breaker rollback, "degraded" health status
  - [ ] Common causes: Redis URL format, TLS misconfiguration
  - [ ] How to check: Review CloudWatch logs for Redis errors
  - [ ] How to fix: Correct REDIS_URL or REDIS_TLS_ENABLED

**Dependencies**: Task 1.1, 3.3
**Estimated Time**: 30 minutes
**Priority**: P2

---

### Task 6.3: Update CLAUDE.md
- [ ] Add section on Redis configuration requirements
  - [ ] Document expected SSM parameter format
  - [ ] Document required environment variables
  - [ ] Add link to redis configuration docs

**Dependencies**: Task 6.1
**Estimated Time**: 15 minutes
**Priority**: P2

---

## 7. Prevention Tasks (MEDIUM - Priority P2)

### Task 7.1: Add Pre-deployment Configuration Check
- [ ] Create script: `scripts/validate_ecs_config.py`
  - [ ] Check SSM parameters have required format
  - [ ] Validate task definition environment variables
  - [ ] Check for common misconfigurations
  - [ ] Run as part of CI/CD before deployment

**Dependencies**: Task 1.1, 3.3
**Estimated Time**: 2 hours
**Priority**: P2

---

### Task 7.2: Add Configuration Validation Tests to CI
- [ ] Add test stage to GitHub Actions
  - [ ] Run configuration validation script
  - [ ] Fail CI if configuration invalid
  - [ ] Run before Docker build

**Dependencies**: Task 7.1
**Estimated Time**: 30 minutes
**Priority**: P2

---

### Task 7.3: Create Configuration Template
- [ ] Create `.env.example` or update existing
  - [ ] Document all Redis environment variables
  - [ ] Provide example values
  - [ ] Add comments explaining TLS requirements

**Dependencies**: Task 6.1
**Estimated Time**: 15 minutes
**Priority**: P2

---

## 8. Infrastructure Tasks (MEDIUM - Priority P2)

### Task 8.1: Review SSM Parameter Format (Optional)
- [ ] Decide: Should SSM parameter contain full URL or just hostname?
  - [ ] Option A: Update SSM to store full URL with scheme
  - [ ] Option B: Keep hostname only, document that app adds scheme
  - [ ] Document decision in infrastructure repo

**Dependencies**: None (independent of code fix)
**Estimated Time**: 30 minutes (discussion + update if needed)
**Priority**: P2 (code fix makes this optional)

---

### Task 8.2: Update Infrastructure as Code
- [ ] Update Terraform in `hokusai-infrastructure` repo
  - [ ] Ensure task definition includes REDIS_TLS_ENABLED
  - [ ] Document Redis configuration pattern
  - [ ] Add validation for task definition secrets

**Dependencies**: Task 1.1, 3.3
**Estimated Time**: 1 hour
**Priority**: P2

---

### Task 8.3: Consider Simpler Health Check for ALB
- [ ] Evaluate using `/health/alb` instead of `/health`
  - [ ] Review pros/cons of dependency checking in health endpoint
  - [ ] Update ALB target group if decided
  - [ ] Test deployment with simpler health check

**Dependencies**: Task 3.3
**Estimated Time**: 1 hour (including testing)
**Priority**: P3 (nice to have, not required for fix)

---

## 9. Rollback Plan (HIGH - Priority P1)

### Task 9.1: Document Rollback Procedure
- [ ] Create `bugs/deployment-rollback/rollback-procedure.md`
  - [ ] If fix causes issues: Revert to task definition v141
  - [ ] Command: `aws ecs update-service --service hokusai-api-development --task-definition hokusai-api-development:141`
  - [ ] Verify: Check service returns to healthy state
  - [ ] Notify: Team that fix was rolled back

**Dependencies**: None
**Estimated Time**: 15 minutes
**Priority**: P1 (before deployment)

---

### Task 9.2: Prepare Rollback Script
- [ ] Create `scripts/rollback_api_service.sh`
  - [ ] Accept task definition revision as parameter
  - [ ] Update ECS service
  - [ ] Wait for rollout to complete
  - [ ] Verify health

**Dependencies**: None
**Estimated Time**: 20 minutes
**Priority**: P1 (before deployment)

---

## 10. Post-Fix Tasks (LOW - Priority P3)

### Task 10.1: Team Knowledge Sharing
- [ ] Schedule short team meeting to discuss bug
  - [ ] Present root cause analysis
  - [ ] Discuss prevention strategies
  - [ ] Review code changes

**Dependencies**: Task 3.3 (after successful deployment)
**Estimated Time**: 30 minutes (meeting)
**Priority**: P3

---

### Task 10.2: Update Code Review Checklist
- [ ] Add item: "Verify configuration value validation"
- [ ] Add item: "Check for TLS/SSL scheme handling"
- [ ] Add item: "Ensure configuration changes tested"

**Dependencies**: Task 1.1, 3.3
**Estimated Time**: 10 minutes
**Priority**: P3

---

## Task Summary & Dependencies

### Critical Path (Must Complete for Fix)
1. Task 1.1: Fix Redis URL construction (no dependencies)
2. Task 2.1: Write unit tests (depends on 1.1)
3. Task 3.1: Local testing (depends on 1.1, 2.1)
4. Task 3.2: Validate against original bug (depends on 1.1, 2.1, 3.1)
5. Task 3.3: Deploy to development (depends on all above)

**Estimated Critical Path Time**: ~6 hours (including build/deploy time)

### High Priority (Should Complete Soon After)
- Task 1.2: Configuration validation (30 min)
- Task 2.2: Integration tests (1.5 hours)
- Task 5.1: Configuration logging (20 min)
- Task 5.2: Health check logging (30 min)
- Task 9.1 & 9.2: Rollback procedures (35 min)

**Estimated High Priority Time**: ~3 hours

### Medium Priority (Complete Within Sprint)
- All Task 4.x: Code quality (1.5 hours)
- All Task 6.x: Documentation (1.75 hours)
- All Task 7.x: Prevention (2.75 hours)
- All Task 8.x: Infrastructure (2.5 hours)

**Estimated Medium Priority Time**: ~8.5 hours

### Low Priority (Nice to Have)
- All Task 10.x: Post-fix improvements (40 min)

---

## Validation Checklist for QA/Reviewers

Before marking fix as complete, verify:

- [ ] ✅ **Unit tests pass**: All new tests in `test_redis_url_config.py` pass
- [ ] ✅ **Integration tests pass**: Health check test passes
- [ ] ✅ **Local testing complete**: Fix works with various Redis configurations
- [ ] ✅ **Original bug resolved**: Bare hostname + TLS enabled works correctly
- [ ] ✅ **Deployment succeeds**: No circuit breaker rollback
- [ ] ✅ **Health check healthy**: Service reports "healthy" not "degraded"
- [ ] ✅ **Logs clean**: No Redis URL scheme errors in CloudWatch
- [ ] ✅ **Model 21 works**: Can make predictions with HuggingFace token
- [ ] ✅ **Rollback plan ready**: Documented and tested
- [ ] ✅ **Code reviewed**: At least one senior engineer approval
- [ ] ⚠️ **Documentation updated**: Configuration guide updated
- [ ] ⚠️ **Infrastructure aligned**: Terraform matches application requirements

---

## Estimated Total Time

- **Critical Path**: ~6 hours
- **High Priority**: ~3 hours
- **Medium Priority**: ~8.5 hours
- **Total for Complete Fix**: ~17.5 hours (~2-3 days)

**Recommended Timeline**:
- **Day 1**: Complete critical path (Tasks 1.1, 2.1, 3.1-3.3) + rollback plan
- **Day 2**: High priority tasks (1.2, 2.2-2.3, 5.x, 9.x)
- **Day 3**: Medium priority tasks (4.x, 6.x, 7.x, 8.x)
- **Post-fix**: Low priority tasks (10.x) as time allows
