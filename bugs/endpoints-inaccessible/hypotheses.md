# Root Cause Hypotheses: Endpoints Inaccessible

## Hypothesis Priority Ranking
Listed in order of likelihood based on symptoms and previous issues documented in Linear backlog.

## Hypothesis 1: Infrastructure Not Deployed [HIGH PRIORITY]
### Proposed Root Cause
The infrastructure components (ALBs, target groups, Route53 records) may not be deployed or may have been destroyed/removed from AWS.

### Why This Could Cause the Behavior
- Connection timeouts suggest no ALB responding at the DNS endpoints
- 404 errors indicate ALB exists but has no routing rules or targets
- Previous Linear issues mention "infrastructure fixes" and migrations

### How to Test/Validate
```bash
# Check if ALBs exist
aws elbv2 describe-load-balancers --query 'LoadBalancers[?contains(LoadBalancerName, `hokusai`)].{Name:LoadBalancerName,State:State.Code,DNS:DNSName}'

# Check Route53 records
nslookup registry.hokus.ai
nslookup api.hokus.ai

# Check if target groups exist
aws elbv2 describe-target-groups --query 'TargetGroups[?contains(TargetGroupName, `hokusai`)].[TargetGroupName,HealthCheckPath,UnhealthyThresholdCount]'
```

### Expected Outcome if Correct
- Missing ALBs or target groups
- DNS records pointing to non-existent resources
- No active infrastructure in AWS

## Hypothesis 2: ECS Services Not Running [HIGH PRIORITY]
### Proposed Root Cause
The ECS services (api, mlflow, auth) are not running or are constantly failing/restarting.

### Why This Could Cause the Behavior
- No healthy targets would cause ALB to return 503/504 or connection timeouts
- Previous issues mention "Model registration still failing" indicating service problems
- Health check failures would remove all targets from ALB

### How to Test/Validate
```bash
# Check ECS services status
aws ecs describe-services --cluster hokusai-development \
  --services hokusai-api-development hokusai-mlflow-development hokusai-auth-development \
  --query 'services[*].[serviceName,runningCount,desiredCount,status]'

# Check recent task failures
aws ecs list-tasks --cluster hokusai-development --desired-status STOPPED \
  --query 'taskArns[0:5]' | xargs -I {} aws ecs describe-tasks \
  --cluster hokusai-development --tasks {} \
  --query 'tasks[*].[taskDefinitionArn,stoppedReason,stopCode]'

# Check container health
aws logs tail /ecs/hokusai-api-development --since 30m | grep -i "error\|fail\|timeout"
```

### Expected Outcome if Correct
- Services showing 0 running tasks
- Multiple task failures with specific error reasons
- Health check failures in logs

## Hypothesis 3: ALB Routing Misconfiguration [MEDIUM PRIORITY]
### Proposed Root Cause
ALB listener rules are misconfigured, pointing to wrong target groups or missing path patterns.

### Why This Could Cause the Behavior
- Would cause 404 errors as ALB can't route requests
- Previous issues mention "Migrate the API endpoints" suggesting routing changes
- Authentication proxy implementation may have broken routing

### How to Test/Validate
```bash
# Check ALB listener rules
for alb in hokusai-main-development hokusai-registry-development hokusai-dp-development; do
  echo "=== $alb ==="
  aws elbv2 describe-listeners --load-balancer-arn \
    $(aws elbv2 describe-load-balancers --names $alb --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null) \
    --query 'Listeners[*].[Port,DefaultActions[0].TargetGroupArn]' 2>/dev/null
done

# Check listener rules for path routing
aws elbv2 describe-rules --listener-arn [LISTENER_ARN] \
  --query 'Rules[*].[Priority,Conditions,Actions[0].TargetGroupArn]'
```

### Expected Outcome if Correct
- Missing or incorrect path patterns in rules
- Wrong target group associations
- Default actions returning 404

## Hypothesis 4: Security Group/Network ACL Blocking [MEDIUM PRIORITY]
### Proposed Root Cause
Security groups or network ACLs are blocking inbound traffic to ALBs or between ALB and ECS tasks.

### Why This Could Cause the Behavior
- Would cause connection timeouts
- Previous issues mention "security group details" in debugging
- Could affect some endpoints but not others

### How to Test/Validate
```bash
# Check ALB security groups
aws elbv2 describe-load-balancers --names hokusai-main-development \
  --query 'LoadBalancers[0].SecurityGroups' | xargs -I {} \
  aws ec2 describe-security-groups --group-ids {} \
  --query 'SecurityGroups[*].[GroupId,IpPermissions[?FromPort==`443`]]'

# Check ECS service security groups
aws ecs describe-services --cluster hokusai-development \
  --services hokusai-api-development \
  --query 'services[0].networkConfiguration.awsvpcConfiguration.securityGroups'

# Test internal connectivity
aws ecs run-task --cluster hokusai-development \
  --task-definition debug-task \
  --network-configuration "awsvpcConfiguration={subnets=[],securityGroups=[]}"
```

### Expected Outcome if Correct
- Missing ingress rules for ports 80/443
- Blocked traffic between ALB and ECS tasks
- Network isolation preventing communication

## Hypothesis 5: Database/Redis Connection Issues [LOW PRIORITY]
### Proposed Root Cause
Backend services are failing health checks due to database or Redis connection problems.

### Why This Could Cause the Behavior
- Health check failures would mark targets unhealthy
- Previous issues show "Database authentication" and "Debug Redis connection" problems
- Could cause cascading failures across services

### How to Test/Validate
```bash
# Check RDS status
aws rds describe-db-instances --db-instance-identifier hokusai-mlflow-development \
  --query 'DBInstances[0].[DBInstanceStatus,Endpoint.Address,DBInstanceClass]'

# Check Redis status
aws elasticache describe-cache-clusters --cache-cluster-id hokusai-redis-development \
  --query 'CacheClusters[0].[CacheClusterStatus,ConfigurationEndpoint]'

# Check recent database errors
aws logs filter-log-events --log-group-name /ecs/hokusai-api-development \
  --filter-pattern "database OR postgres OR redis" --start-time $(date -u -d '1 hour ago' +%s)000
```

### Expected Outcome if Correct
- Database connection timeouts in logs
- Redis authentication failures
- Health check failures specifically mentioning data stores

## Hypothesis 6: Domain/DNS Misconfiguration [LOW PRIORITY]
### Proposed Root Cause
DNS records are pointing to wrong resources or certificates have expired.

### Why This Could Cause the Behavior
- Would cause connection failures or SSL errors
- Could affect all endpoints uniformly
- May have been changed during infrastructure migration

### How to Test/Validate
```bash
# Check DNS resolution
for domain in registry.hokus.ai api.hokus.ai mlflow.hokus.ai platform.hokus.ai; do
  echo "=== $domain ==="
  dig +short $domain
  dig +short CNAME $domain
done

# Check SSL certificates
for domain in registry.hokus.ai api.hokus.ai; do
  echo | openssl s_client -connect $domain:443 -servername $domain 2>/dev/null | \
    openssl x509 -noout -dates -subject
done

# Check Route53 hosted zone
aws route53 list-resource-record-sets --hosted-zone-id [ZONE_ID] \
  --query 'ResourceRecordSets[?contains(Name, `hokus.ai`)].[Name,Type,AliasTarget.DNSName]'
```

### Expected Outcome if Correct
- DNS not resolving or pointing to wrong IPs
- Expired SSL certificates
- Missing Route53 records

## Testing Order
1. **Start with Hypothesis 1** - Quick to verify infrastructure existence
2. **Then Hypothesis 2** - Check if services are running
3. **Follow with Hypothesis 3** - Verify routing configuration
4. **Continue with remaining** hypotheses based on findings

## Additional Considerations
- Check for recent AWS service outages in us-east-1
- Review any recent deployments or infrastructure changes
- Consider if this is environment-specific (development vs production)
- Check AWS billing/limits for any resource constraints