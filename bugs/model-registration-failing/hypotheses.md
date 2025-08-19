# Root Cause Hypotheses: Model Registration Failure

## Hypothesis Summary Table

| # | Hypothesis | Confidence | Complexity | Impact if True |
|---|------------|------------|------------|----------------|
| 1 | ALB routing rules missing/misconfigured for registry.hokus.ai | High | Simple | Critical |
| 2 | MLflow service not running or unhealthy in ECS | High | Medium | Critical |
| 3 | API proxy service /api/mlflow routes not implemented | Medium | Medium | Critical |
| 4 | DNS/Route53 misconfiguration for registry.hokus.ai | Medium | Simple | Critical |
| 5 | Security groups blocking traffic between ALB and ECS | Low | Simple | Critical |

## Detailed Hypotheses

### Hypothesis 1: ALB Routing Rules Missing/Misconfigured
**Confidence**: High (85%)
**Category**: Infrastructure Configuration

#### Description
The Application Load Balancer (ALB) for registry.hokus.ai is not properly configured to route traffic to the MLflow or API services. After the infrastructure migration, the listener rules may not have been recreated or are pointing to wrong target groups.

#### Supporting Evidence
- All endpoints return 404 (typical of no routing rules matching)
- Previous Linear tickets mention "Configure ALB Routing for MLflow"
- Infrastructure was recently migrated to centralized repo
- Other services (auth.hokus.ai) work, suggesting selective routing issues

#### Why This Causes the Bug
When ALB receives requests for registry.hokus.ai, it checks listener rules to determine which target group to forward to. Without proper rules, it returns 404 as no backend handles the request.

#### Test Method
1. Check ALB listener rules: `aws elbv2 describe-listeners --load-balancer-arn <registry-alb-arn>`
2. Look for rules matching paths: `/`, `/api/mlflow/*`, `/api/2.0/mlflow/*`
3. Verify target groups are attached and healthy
4. Expected if TRUE: No rules or wrong target groups for registry paths
5. Expected if FALSE: Proper rules exist pointing to healthy targets

#### Code/Configuration to Check
```bash
# Get ALB ARN for registry
aws elbv2 describe-load-balancers --names hokusai-registry-development --region us-east-1

# Check listener rules
aws elbv2 describe-rules --listener-arn <listener-arn> --region us-east-1

# Check target group health
aws elbv2 describe-target-health --target-group-arn <target-group-arn> --region us-east-1
```

#### Quick Fix Test
Add a simple path-based routing rule for `/health` to the API service target group and test if it responds.

---

### Hypothesis 2: MLflow Service Not Running or Unhealthy
**Confidence**: High (80%)
**Category**: Service Health

#### Description
The MLflow ECS service is either not running, constantly restarting, or failing health checks, making it unavailable to serve requests even if routing is correct.

#### Supporting Evidence
- Complete service unavailability (not even partial responses)
- Previous issues with database connectivity for MLflow
- Multiple past tickets about service health problems
- Service was working before infrastructure migration

#### Why This Causes the Bug
If MLflow service is unhealthy, ECS removes it from target groups. Even with correct routing, ALB has no healthy targets to forward requests to.

#### Test Method
1. Check ECS service status: `aws ecs describe-services --cluster hokusai-development --services hokusai-mlflow-development`
2. Check running task count and desired count
3. Review task logs for startup failures
4. Expected if TRUE: 0 running tasks or continuous restarts
5. Expected if FALSE: Stable running tasks matching desired count

#### Code/Configuration to Check
```bash
# Check service status
aws ecs describe-services --cluster hokusai-development --services hokusai-mlflow-development --region us-east-1

# Get recent task ARNs
aws ecs list-tasks --cluster hokusai-development --service-name hokusai-mlflow-development --region us-east-1

# Check task logs
aws logs tail /ecs/hokusai-mlflow-development --follow --region us-east-1
```

#### Quick Fix Test
Manually force a new deployment of the service to see if fresh tasks become healthy.

---

### Hypothesis 3: API Proxy Routes Not Implemented
**Confidence**: Medium (60%)
**Category**: Application Code

#### Description
The API service is running but missing the implementation for `/api/mlflow/*` proxy routes that should forward requests to the internal MLflow service.

#### Supporting Evidence
- Linear ticket "Authentication proxy" mentions "/api/mlflow endpoint needs implementation"
- API service may be receiving requests but not handling them (404)
- Other API endpoints might work while MLflow proxy doesn't

#### Why This Causes the Bug
Without proxy route implementation, the API service returns 404 for MLflow paths even if it receives the requests correctly from ALB.

#### Test Method
1. Check API service routes: Review src/api/routes/ for MLflow proxy implementation
2. Test API health endpoint: `curl https://api.hokus.ai/health`
3. Check API logs for incoming requests to /api/mlflow
4. Expected if TRUE: No route handlers for /api/mlflow paths
5. Expected if FALSE: Proxy routes exist and are registered

#### Code/Configuration to Check
```bash
# Check for MLflow route implementation
grep -r "mlflow" src/api/routes/
grep -r "/api/mlflow" src/api/

# Check route registration
grep -r "router.register" src/api/
grep -r "app.include_router" src/api/
```

#### Quick Fix Test
Add a simple test route at `/api/mlflow/test` that returns 200 OK to verify routing works.

---

### Hypothesis 4: DNS/Route53 Misconfiguration
**Confidence**: Medium (40%)
**Category**: Infrastructure Configuration

#### Description
The registry.hokus.ai domain is not properly configured in Route53 or is pointing to the wrong load balancer.

#### Supporting Evidence
- Complete inability to reach any endpoint
- Infrastructure migration could have missed DNS updates
- Other domains (auth.hokus.ai) work correctly

#### Why This Causes the Bug
If DNS points to wrong or non-existent resources, all requests fail before reaching the application layer.

#### Test Method
1. Check DNS resolution: `nslookup registry.hokus.ai`
2. Verify Route53 records: `aws route53 list-resource-record-sets --hosted-zone-id <zone-id>`
3. Compare with working domain (auth.hokus.ai)
4. Expected if TRUE: DNS points to wrong IP or doesn't resolve
5. Expected if FALSE: DNS correctly points to registry ALB

#### Code/Configuration to Check
```bash
# Check DNS resolution
nslookup registry.hokus.ai
dig registry.hokus.ai

# Get Route53 hosted zones
aws route53 list-hosted-zones --region us-east-1

# Check A records for registry.hokus.ai
aws route53 list-resource-record-sets --hosted-zone-id <zone-id> --query "ResourceRecordSets[?Name=='registry.hokus.ai.']"
```

---

### Hypothesis 5: Security Groups Blocking Traffic
**Confidence**: Low (20%)
**Category**: Network Security

#### Description
Security groups on ALB or ECS tasks are blocking the required ports, preventing traffic flow even with correct routing.

#### Supporting Evidence
- Other services work, suggesting selective blocking
- Recent infrastructure changes could have modified security groups
- Less likely as typically causes timeouts, not 404s

#### Why This Causes the Bug
Blocked traffic would prevent ALB from reaching ECS tasks, resulting in no available targets.

#### Test Method
1. Check ALB security groups for port 443 ingress
2. Check ECS security groups for ALB access on service ports
3. Verify security group rules allow traffic flow
4. Expected if TRUE: Missing or incorrect security group rules
5. Expected if FALSE: Proper ingress/egress rules exist

## Testing Priority Order

1. Start with Hypothesis 1 (ALB routing) - quickest to verify and most likely given 404 responses
2. Then Hypothesis 2 (service health) - critical to know if service is even running
3. Then Hypothesis 3 (API proxy) - check application code if infrastructure is correct
4. Then Hypothesis 4 (DNS) - verify basic connectivity
5. Finally Hypothesis 5 (security groups) - least likely but easy to check

## Alternative Hypotheses if All Above Fail

- MLflow configuration pointing to wrong database
- Certificate/TLS issues with registry.hokus.ai
- Container image missing or corrupted after migration
- Environment variables not properly set in ECS task definitions
- Service discovery namespace issues
- MLflow authentication middleware rejecting all requests

## Data Needed for Further Investigation

If initial hypotheses don't resolve the issue:
- Full terraform configuration from hokusai-infrastructure repo
- Complete ALB access logs for failed requests
- ECS task definition comparison (before/after migration)
- Network flow logs to trace request path
- Application startup logs showing configuration loading