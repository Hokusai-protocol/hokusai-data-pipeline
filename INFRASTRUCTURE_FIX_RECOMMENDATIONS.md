# Infrastructure Fix Recommendations

## Immediate Action Taken ✅

**Deployed workaround using direct IP (10.0.1.88:5000) for MLflow**
- This bypasses service discovery DNS issues
- Services should start working within 5-10 minutes after deployment
- This is a TEMPORARY fix but gets services operational NOW

## Root Problem Summary

The API service was recreated WITHOUT service discovery registration:
- `serviceRegistries: []` (empty)
- Cannot resolve `mlflow.hokusai-development.local`
- Not part of the service mesh

## Recommended Long-Term Solution

### Move ALL Infrastructure to Centralized Repo

**Why:**
1. **State Consistency**: Current issue caused by Terraform state mismatches
2. **Single Source of Truth**: Avoid resource conflicts between repos
3. **Proper Dependencies**: Service discovery must be created before services
4. **Prevent Future Issues**: Centralized management prevents recreation without proper config

### Implementation Plan for Infrastructure Team

#### Phase 1: Import Existing Resources (1-2 hours)
```bash
# Import service discovery namespace
terraform import aws_service_discovery_dns_namespace.internal ns-xxxxx

# Import service discovery services
terraform import aws_service_discovery_service.mlflow srv-xxxxx
terraform import aws_service_discovery_service.api srv-xxxxx

# Import ECS services with proper configuration
terraform import aws_ecs_service.api hokusai-development/hokusai-api-development
```

#### Phase 2: Update Terraform Configuration (2-3 hours)
```hcl
# environments/data-pipeline-ecs-services.tf

resource "aws_ecs_service" "api" {
  name            = "hokusai-api-development"
  cluster         = data.aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  
  # CRITICAL: Add service registry
  service_registries {
    registry_arn = aws_service_discovery_service.api.arn
    port         = 8001
  }
  
  network_configuration {
    subnets         = data.aws_subnets.private.ids
    security_groups = [data.aws_security_group.ecs_tasks.id]
  }
  
  # Health check grace period for startup
  health_check_grace_period_seconds = 120
  
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "hokusai-api"
    container_port   = 8001
  }
}

resource "aws_service_discovery_service" "api" {
  name = "api"
  
  dns_config {
    namespace_id = data.aws_service_discovery_dns_namespace.internal.id
    
    dns_records {
      ttl  = 10
      type = "A"
    }
    
    routing_policy = "MULTIVALUE"
  }
  
  health_check_custom_config {
    failure_threshold = 1
  }
}
```

#### Phase 3: Update Task Definitions (1 hour)
```hcl
# Use environment variables for service endpoints
environment = [
  {
    name  = "MLFLOW_SERVER_URL"
    value = "http://mlflow.hokusai-development.local:5000"
  },
  {
    name      = "REDIS_HOST"
    valueFrom = "/hokusai/development/redis/endpoint"
  }
]
```

## Why NOT to Use Quick Fixes

### ❌ Don't Do Option 1 (Update Service via CLI)
- Would be overwritten by next Terraform apply
- Doesn't fix root cause
- Creates more state drift

### ❌ Don't Do Option 2 (Recreate Service via CLI)
- Already tried this - caused current problem
- Manual changes create Terraform conflicts
- Risk of extended downtime

### ✅ Current Workaround (Direct IP) is Best for Now
- Gets services working immediately
- No infrastructure changes needed
- Easy to revert once properly fixed

## Migration Timeline

### Week 1: Stabilize with Workaround
- [x] Deploy direct IP fix (DONE)
- [ ] Monitor service health
- [ ] Validate all endpoints working

### Week 2: Centralize Infrastructure
- [ ] Import all resources to central repo
- [ ] Create proper service discovery config
- [ ] Test in staging environment

### Week 3: Deploy Permanent Fix
- [ ] Apply Terraform with service discovery
- [ ] Revert direct IP workaround
- [ ] Validate DNS resolution working

## Testing After Each Phase

### After Workaround (Now):
```bash
# Should work with direct IP
curl https://registry.hokus.ai/health
curl https://registry.hokus.ai/api/mlflow/version
```

### After Permanent Fix:
```bash
# Test from within VPC/container
nslookup mlflow.hokusai-development.local
nslookup api.hokusai-development.local

# Verify service registry
aws ecs describe-services --cluster hokusai-development \
  --services hokusai-api-development \
  | jq '.services[0].serviceRegistries'
```

## Critical Success Factors

1. **DO NOT** make manual AWS changes - use Terraform only
2. **DO NOT** delete/recreate services without service discovery
3. **DO** test all changes in staging first
4. **DO** maintain backwards compatibility during migration

## Rollback Plan

If issues occur after permanent fix:
```bash
# Quick revert to direct IP
python fix_mlflow_ip.py
git commit -am "Revert to direct IP"
git push

# Services back online in ~10 minutes
```

## Contact for Issues

If deployment fails or services remain down:
1. Check CloudWatch logs for hokusai-api-development
2. Verify ECS task is running
3. Check ALB target health
4. Use direct IP workaround if needed

## Summary

**Immediate**: Direct IP workaround is deployed and should restore service
**Short-term**: Continue using workaround while planning proper fix
**Long-term**: Centralize all infrastructure with proper service discovery

The key lesson: Infrastructure as Code only works when there's ONE source of truth. The current split between repos caused this issue and will cause more unless consolidated.