# Bug Investigation Plan: Endpoints Inaccessible

## Bug Summary
**Title:** Endpoints inaccessible  
**Severity:** CRITICAL  
**Date Reported:** August 2025  
**Status:** Platform completely inaccessible - all endpoints failing

### Impact Analysis
- **Business Impact:** Complete platform outage - no model registration, serving, or management possible
- **User Impact:** All users unable to access any Hokusai services
- **Technical Impact:** All external-facing endpoints returning connection timeouts or 404 errors
- **Data Impact:** Models can only be registered locally, not accessible via platform

## Affected Components/Services

### Primary Infrastructure
1. **Application Load Balancers (ALBs)**
   - hokusai-main-development
   - hokusai-registry-development  
   - hokusai-dp-development

2. **ECS Services**
   - hokusai-api-development
   - hokusai-mlflow-development
   - hokusai-auth-development

3. **DNS/Domain Configuration**
   - registry.hokus.ai
   - api.hokus.ai
   - mlflow.hokus.ai
   - platform.hokus.ai

4. **Target Groups**
   - ALB target group health checks
   - Service registration status

5. **Security Groups & Network ACLs**
   - Ingress/egress rules
   - Port accessibility (8001, 5000, 8000)

## Reproduction Steps

1. **Test External Endpoints**
   ```bash
   # Test each endpoint
   curl -I https://registry.hokus.ai/
   curl -I https://api.hokus.ai/
   curl -I https://mlflow.hokus.ai/
   curl -I https://platform.hokus.ai/
   ```

2. **Test Health Endpoints**
   ```bash
   curl https://registry.hokus.ai/health
   curl https://api.hokus.ai/health
   curl https://registry.hokus.ai/api/mlflow/health
   ```

3. **Test with Authentication**
   ```bash
   curl -H "Authorization: Bearer hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN" \
        https://api.hokus.ai/api/v1/models
   ```

## Initial Observations from Logs/Monitoring

### CloudWatch Logs to Check
```bash
# API Service Logs
aws logs tail /ecs/hokusai-api-development --follow --since 1h

# MLflow Service Logs  
aws logs tail /ecs/hokusai-mlflow-development --follow --since 1h

# Auth Service Logs
aws logs tail /ecs/hokusai-auth-development --follow --since 1h
```

### ECS Service Status
```bash
# Check service health
aws ecs describe-services --cluster hokusai-development \
  --services hokusai-api-development hokusai-mlflow-development hokusai-auth-development \
  --query 'services[*].[serviceName,runningCount,desiredCount,events[0]]'
```

### ALB Health Checks
```bash
# Check target health
aws elbv2 describe-target-health \
  --target-group-arn $(aws elbv2 describe-target-groups \
    --names hokusai-api-development --query 'TargetGroups[0].TargetGroupArn' --output text)
```

## Priority Investigation Areas

### Critical Priority
1. **DNS/Domain Configuration**
   - Verify Route53 records exist and point to correct ALBs
   - Check if ALBs have public IPs assigned
   - Validate SSL certificates

2. **ALB Configuration**
   - Listener rules and routing
   - Target group attachments
   - Health check configurations

### High Priority  
3. **ECS Service Health**
   - Task status and failures
   - Container health checks
   - Resource allocation (CPU/Memory)

4. **Network Configuration**
   - Security group rules
   - Network ACLs
   - VPC/Subnet configuration

### Medium Priority
5. **Application Configuration**
   - Environment variables
   - Database connectivity
   - Service discovery

6. **Infrastructure State**
   - Recent deployments or changes
   - Terraform state consistency
   - AWS resource limits

## Investigation Strategy

### Phase 1: Immediate Triage (0-30 minutes)
- Verify DNS resolution for all domains
- Check ALB status and public accessibility
- Review ECS service health and running tasks
- Examine recent CloudWatch alarms

### Phase 2: Deep Dive (30-90 minutes)
- Analyze ALB access logs for request patterns
- Review ECS task definitions for configuration issues
- Check security group and network ACL rules
- Investigate service discovery namespace

### Phase 3: Root Cause Analysis (90+ minutes)
- Compare current state with known-good configuration
- Review recent commits and deployments
- Check AWS service health dashboard
- Analyze infrastructure drift

## Success Criteria
- Identify specific component(s) causing the outage
- Document exact error conditions and failure points
- Provide clear path to resolution
- Establish timeline of when services became unavailable

## Risk Assessment
- **Data Loss Risk:** Low - local registration still works
- **Security Risk:** Medium - need to verify no compromise
- **Business Continuity:** High - complete platform outage
- **Recovery Time:** Unknown until root cause identified