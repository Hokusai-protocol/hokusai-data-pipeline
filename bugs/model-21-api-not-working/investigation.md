# Bug Investigation Plan: Model 21 API Not Working

## 1. Bug Summary

**Issue:** Third-party client attempting to use Model ID 21 API for lead scoring. API is "not working properly" and documentation is inadequate.

**Severity:** Critical - Blocks external customer integration

**Impact:**
- External customer cannot score leads using Model 21
- Customer-facing integration is blocked
- Revenue impact - customer paying for API access
- Documentation insufficient for troubleshooting
- Reputation impact with external developers

**When it occurs:** When third-party attempts to make POST request to `/api/v1/models/21/predict` endpoint

**Who is affected:** External API consumer (third-party in ../gtm-backend/)

## 2. Current Status

### Previous Investigation
- Previous investigation found **dual authentication layers** causing complexity
- Previous root cause identified middleware + endpoint auth conflict
- Fix tasks were created but implementation status unclear
- Model serving endpoint exists at [src/api/endpoints/model_serving.py](src/api/endpoints/model_serving.py)
- Model 21 configuration exists and is documented

### Current Testing Results
**Test Date:** 2025-11-07

**Test 1: Endpoint without authentication**
```bash
curl -X POST https://api.hokus.ai/api/v1/models/21/predict \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"company_size": 1000}}'
```
**Result:** Request **times out** after 10 seconds (no response)

**Observation:** This is **NOT** a 405 error as previously reported. The endpoint is either:
1. Not responding (service down)
2. Timing out before auth middleware can respond
3. DNS/routing issue preventing request from reaching the service

## 3. Third-Party Client Analysis

### Client Code Location
`../gtm-backend/agent/ml/hokusai_api_client.py`

### Client Request Pattern
```python
# From hokusai_api_client.py:113-159
url = f"{self.api_url}/v1/models/{self.model_id}/predict"
headers = {
    "Authorization": f"Bearer {self.api_key}",
    "Content-Type": "application/json",
    "X-Request-ID": request_id
}
response = requests.post(url, headers=headers, data=json.dumps(data), timeout=self.timeout)
```

### Expected Request Format
```json
{
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
}
```

### Client Configuration Required
- `HOKUSAI_API_URL`: Base URL (e.g., "https://api.hokus.ai/api")
- `HOKUSAI_API_KEY`: API key starting with "hk_"
- `HOKUSAI_MODEL_ID`: "21"
- `HOKUSAI_API_TIMEOUT`: Default timeout in seconds

## 4. Affected Components

### API Services
- **API Service:** `hokusai-api-development` (ECS)
  - Internal URL: `http://api.hokusai-development.local:8001`
  - External URL: `https://api.hokus.ai`
  - Port: 8001

- **Model Serving Router:** [src/api/endpoints/model_serving.py](src/api/endpoints/model_serving.py)
  - Route prefix: `/api/v1/models`
  - Endpoints: `/{model_id}/info`, `/{model_id}/predict`, `/{model_id}/health`

- **Auth Middleware:** [src/middleware/auth.py](src/middleware/auth.py)
  - Global middleware on all requests
  - Validates API keys with auth service
  - Caches results in Redis

### Infrastructure
- **Load Balancer:** ALB (hokusai-dp-development or hokusai-main-development)
  - Routes HTTPS traffic to ECS service
  - Path-based routing rules
  - Health check configuration

- **Auth Service:** `https://auth.hokus.ai`
  - External authentication service
  - API key validation endpoint
  - May be unreachable from ECS or timing out

- **Redis Cache:** Used for auth token caching
  - 5-minute TTL for auth validation
  - May be unreachable or misconfigured

- **HuggingFace Hub:** Model storage
  - Private repository: `timogilvie/hokusai-model-21-sales-lead-scorer`
  - Requires `HUGGINGFACE_API_KEY` environment variable
  - Model loaded on first request

### Database Tables
- Model configuration (likely in application code or database)
- API key validation (auth service database)

## 5. Initial Observations

### API Timeout Behavior
- **No response** within 10 seconds suggests:
  1. Service is not running or crashed
  2. Load balancer health checks failing
  3. ECS task not registered with target group
  4. Security group blocking traffic
  5. Service listening on wrong port
  6. Service stuck in startup/loading

### Previous Error (405)
- Previous investigation mentioned **405 Method Not Allowed**
- Current testing shows **timeout** instead
- This suggests the problem has changed OR environment is different:
  - Development vs. Production
  - Service was redeployed and stopped working
  - Infrastructure change broke connectivity

### Documentation Gap
- [MODEL_21_VERIFICATION_REPORT.md](MODEL_21_VERIFICATION_REPORT.md) shows endpoint should work
- Report claims "✅ VERIFIED" but current testing contradicts this
- Documentation may be outdated or from different environment

## 6. Data Analysis Required

### Service Health
- [ ] Check ECS service status: `hokusai-api-development`
- [ ] Check task count (should be > 0 running tasks)
- [ ] Check task health status
- [ ] Review ECS task definition

### Logs
- [ ] Check CloudWatch logs: `/ecs/hokusai-api-development`
- [ ] Look for startup errors
- [ ] Check for auth service connection errors
- [ ] Check for dependency failures (Redis, HuggingFace, etc.)
- [ ] Filter for Model 21 related logs

### Load Balancer
- [ ] Verify ALB target group health
- [ ] Check target registration status
- [ ] Review ALB access logs for requests to `/api/v1/models/21/predict`
- [ ] Verify path-based routing rules

### Network & Security
- [ ] Check security groups allow traffic on port 8001
- [ ] Verify service discovery DNS resolves correctly
- [ ] Test internal connectivity from another ECS task
- [ ] Check VPC networking configuration

### Dependencies
- [ ] Verify auth service is reachable: `curl https://auth.hokus.ai/health`
- [ ] Check Redis connectivity
- [ ] Verify HuggingFace API key is configured
- [ ] Test HuggingFace repository accessibility

### Environment Variables
- [ ] Verify all required env vars set in ECS task definition:
  - `HOKUSAI_AUTH_SERVICE_URL`
  - `HUGGINGFACE_API_KEY`
  - `REDIS_URL` or `REDIS_HOST`/`REDIS_PORT`
  - Any other required configuration

## 7. Investigation Strategy

### Priority 1: Verify Service is Running (15 min)
1. Check ECS service status and running tasks
2. Review recent deployments and task changes
3. Check CloudWatch logs for errors
4. Verify service is actually listening on port 8001

### Priority 2: Test Connectivity (15 min)
1. Test ALB health check endpoint: `https://api.hokus.ai/health`
2. Test from within VPC if possible
3. Check DNS resolution for internal/external domains
4. Verify security groups and network ACLs

### Priority 3: Check Dependencies (20 min)
1. Test auth service connectivity from ECS task
2. Verify Redis is accessible
3. Check HuggingFace API connectivity
4. Review environment variable configuration

### Priority 4: Reproduce and Debug (30 min)
1. Get valid API key for testing
2. Test with proper authentication headers
3. Check if endpoint responds with auth
4. Review route registration in FastAPI app

### Tools and Techniques
- AWS Console (ECS, CloudWatch, Load Balancers)
- AWS CLI for ECS/logs queries
- curl for endpoint testing
- CloudWatch Logs Insights
- ECS exec for debugging running containers

### Key Questions to Answer
1. **Is the API service running?** Check ECS task count and health
2. **Is the service reachable?** Test ALB and target group health
3. **Are there startup errors?** Review CloudWatch logs
4. **Has anything changed recently?** Check deployment history
5. **Do environment variables exist?** Review task definition
6. **Is the endpoint registered?** Check FastAPI route registration
7. **Can auth service be reached?** Test from ECS task
8. **Is the right API key being used?** Verify key format and validity

### Success Criteria
- Identified why endpoint is timing out
- Determined root cause (service, network, or configuration)
- Service health status confirmed
- Clear path to resolution identified

## 8. Risk Assessment

### Current Impact
- **Critical:** Customer integration completely blocked
- No predictions possible for Model 21
- Customer unable to use paid API service
- Potential SLA breach if customer has one
- Revenue loss during downtime

### Potential for Escalation
- **High:** If service is down, affects all API endpoints
- May affect other models beyond Model 21
- Could indicate broader infrastructure issue
- Other customers may be impacted

### Security Implications
- **Low:** Timeout suggests service unavailable, not security issue
- No evidence of unauthorized access
- Auth system may be functioning but unreachable

### Data Integrity Concerns
- **Low:** Service unavailability doesn't affect data integrity
- No predictions being made means no incorrect data stored

## 9. Timeline

### When Bug First Appeared
- **Unknown** - need to check logs and deployment history
- Previous investigation was for "405 error"
- Current symptom is "timeout"
- May be a different issue or evolution of previous issue

### Correlation with Deployments
- [ ] Check last deployment to `hokusai-api-development`
- [ ] Review infrastructure changes (ALB, security groups, etc.)
- [ ] Check if any dependency services were updated
- [ ] Review recent code changes to model serving endpoint

### Frequency of Occurrence
- Appears to be **100% failure rate** (consistent)
- Not intermittent - suggests systemic issue
- Affects all requests to this endpoint

### Patterns in Timing
- No time-based pattern expected (persistent failure)
- Likely started with a specific deployment or config change
- Need to establish timeline from logs

## 10. Hypotheses

### Hypothesis 1: ECS Service Not Running
**Likelihood:** High
**Reason:** Timeout with no response suggests service unavailable
**Test:** Check ECS service status and running task count
**Expected if true:** 0 running tasks or all tasks unhealthy

### Hypothesis 2: Load Balancer Misconfiguration
**Likelihood:** Medium
**Reason:** Requests not reaching service
**Test:** Check ALB target group health and routing rules
**Expected if true:** Target group shows unhealthy targets

### Hypothesis 3: Service Startup Failure
**Likelihood:** Medium
**Reason:** Tasks start but crash during initialization
**Test:** Review CloudWatch logs for startup errors
**Expected if true:** Repeated task restarts and startup errors in logs

### Hypothesis 4: Missing Environment Variables
**Likelihood:** Medium
**Reason:** Service fails to start due to missing required config
**Test:** Review ECS task definition environment variables
**Expected if true:** Missing HUGGINGFACE_API_KEY or other critical vars

### Hypothesis 5: Auth Service Unreachable
**Likelihood:** Medium
**Reason:** Auth middleware times out waiting for auth service
**Test:** Test auth service connectivity from ECS task
**Expected if true:** Auth service timeout errors in logs

### Hypothesis 6: Port Mismatch
**Likelihood:** Low
**Reason:** Service listening on different port than ALB expects
**Test:** Check service port in code vs. target group port
**Expected if true:** ALB health checks failing, logs show correct port

### Hypothesis 7: DNS Resolution Issue
**Likelihood:** Low
**Reason:** Service Discovery DNS not resolving correctly
**Test:** Test DNS resolution from within VPC
**Expected if true:** Cannot resolve api.hokus.ai or internal service names

### Hypothesis 8: Security Group Blocking Traffic
**Likelihood:** Low
**Reason:** Security group rules preventing traffic
**Test:** Review security group rules for port 8001
**Expected if true:** ALB cannot reach targets, all health checks fail

## 11. Next Steps

1. **Immediate:** Check ECS service health and logs
2. **High Priority:** Test ALB and connectivity
3. **Medium Priority:** Verify all dependencies accessible
4. **Follow-up:** Review previous fix implementation status
5. **Documentation:** Update investigation plan with findings

## 12. Success Metrics for Resolution

- [ ] API endpoint responds within 2 seconds
- [ ] Valid API key returns 200 with predictions
- [ ] Invalid API key returns 401 with clear error message
- [ ] Missing API key returns 401 with helpful error
- [ ] Third-party client can successfully make predictions
- [ ] No timeout or connection errors
- [ ] Logs show successful auth and prediction flow
- [ ] Performance within acceptable limits (p95 < 1s)

## Notes

- This is a **customer-blocking** issue requiring urgent attention
- Previous investigation exists but current symptoms differ (timeout vs. 405)
- Need to verify if previous fixes were actually deployed
- Must coordinate with third-party for testing after fix
- Update Linear ticket with progress
