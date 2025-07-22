# Dedicated ALB Migration Plan

## Overview

This plan outlines the migration from a single shared ALB to dedicated ALBs for auth.hokus.ai and registry.hokus.ai services, eliminating routing conflicts and improving service isolation.

## Benefits of Dedicated ALBs

1. **Eliminates Routing Conflicts**: No more priority juggling or path conflicts
2. **Improved Security**: Better isolation between auth and registry services
3. **Independent Scaling**: Each service can scale independently
4. **Simplified Debugging**: Clear separation of concerns
5. **Better Performance**: Dedicated resources for each service

## Migration Steps

### Phase 1: Preparation (Day 1)

1. **Review Current Configuration**
   ```bash
   cd infrastructure/terraform
   terraform plan
   ```

2. **Backup Current State**
   ```bash
   terraform state pull > terraform.state.backup.json
   ```

3. **Verify Certificate ARN**
   - Ensure the SSL certificate covers both auth.hokus.ai and registry.hokus.ai
   - Or create separate certificates for each subdomain

### Phase 2: Deploy New ALBs (Day 1)

1. **Add Required Variables** (if not present)
   ```hcl
   # In variables.tf
   variable "route53_zone_id" {
     description = "Route53 Hosted Zone ID for hokus.ai"
     type        = string
     default     = ""
   }
   ```

2. **Apply Dedicated ALB Configuration**
   ```bash
   # First, review the plan
   terraform plan -target=aws_lb.auth -target=aws_lb.registry
   
   # Apply the new ALBs
   terraform apply -target=aws_lb.auth -target=aws_lb.registry
   ```

3. **Deploy Listeners and Rules**
   ```bash
   terraform apply -target=aws_lb_listener.auth_http \
                   -target=aws_lb_listener.auth_https \
                   -target=aws_lb_listener.registry_http \
                   -target=aws_lb_listener.registry_https \
                   -target=aws_lb_listener_rule.auth_api_v1 \
                   -target=aws_lb_listener_rule.registry_mlflow
   ```

### Phase 3: DNS Migration (Day 2)

1. **Test New ALBs Directly**
   ```bash
   # Get ALB DNS names
   terraform output auth_alb_dns
   terraform output registry_alb_dns
   
   # Test auth ALB
   curl -H "Host: auth.hokus.ai" https://<auth-alb-dns>/health
   
   # Test registry ALB
   curl -H "Host: registry.hokus.ai" https://<registry-alb-dns>/health
   ```

2. **Update DNS Records**
   - If using Route53 and provided zone_id:
     ```bash
     terraform apply -target=aws_route53_record.auth \
                     -target=aws_route53_record.registry
     ```
   - If using external DNS provider:
     - Update A records for auth.hokus.ai → Auth ALB DNS
     - Update A records for registry.hokus.ai → Registry ALB DNS

3. **Monitor DNS Propagation**
   ```bash
   # Check DNS resolution
   dig auth.hokus.ai
   dig registry.hokus.ai
   ```

### Phase 4: Validation (Day 2)

1. **Run Comprehensive Tests**
   ```bash
   # Test auth service
   export HOKUSAI_API_KEY="your-api-key"
   python test_auth_service.py
   
   # Test registry API
   python verify_api_proxy.py
   
   # Test MLflow registration
   python test_real_registration.py
   ```

2. **Monitor CloudWatch Metrics**
   - Check target health for both ALBs
   - Monitor request counts and latency
   - Watch for any 4xx/5xx errors

### Phase 5: Cleanup (Day 3)

1. **Remove Old ALB Configuration**
   - Comment out or remove the shared ALB configuration from main.tf
   - Remove old listener rules

2. **Update Documentation**
   - Update README with new architecture
   - Update API documentation with correct endpoints
   - Update deployment guides

## Rollback Plan

If issues arise during migration:

1. **Quick DNS Rollback**
   - Revert DNS records to point to old ALB
   - DNS changes propagate within minutes

2. **Keep Old ALB Running**
   - Don't delete the old ALB until migration is verified
   - Maintain it for at least 1 week after migration

3. **State Recovery**
   ```bash
   # If needed, restore from backup
   terraform state push terraform.state.backup.json
   ```

## Testing Checklist

- [ ] Auth service health endpoint responds
- [ ] API key validation works
- [ ] Registry API health endpoint responds
- [ ] MLflow UI is accessible
- [ ] Model registration completes successfully
- [ ] All authentication flows work
- [ ] No 404 or routing errors
- [ ] Performance metrics are acceptable

## Cost Considerations

- Each ALB costs approximately $20-30/month
- Total additional cost: ~$40-60/month
- Benefits outweigh costs for production stability

## Next Steps

1. Get approval for additional infrastructure costs
2. Schedule migration window (recommend low-traffic period)
3. Notify team of planned changes
4. Execute migration plan
5. Monitor for 24-48 hours post-migration