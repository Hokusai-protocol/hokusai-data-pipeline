# Step-by-Step Guide: Deploying Dedicated ALBs

This guide walks through deploying dedicated Application Load Balancers for auth.hokus.ai and registry.hokus.ai.

## Prerequisites

Before starting, ensure you have:
- [ ] AWS CLI configured with appropriate credentials
- [ ] Terraform installed (version 1.0+)
- [ ] Access to AWS Certificate Manager (ACM) certificate ARN
- [ ] Access to Route53 hosted zone (or external DNS provider)

## Step 1: Prepare the Environment

### 1.1 Navigate to Terraform Directory
```bash
cd infrastructure/terraform
```

### 1.2 Check Current State
```bash
# View current infrastructure
terraform state list | grep -E "aws_lb|listener|target_group"

# Backup current state (important!)
terraform state pull > backup/terraform.state.$(date +%Y%m%d_%H%M%S).json
```

### 1.3 Review Current Variables
```bash
# Check your terraform.tfvars file
cat terraform.tfvars

# Ensure these variables are set:
# - certificate_arn (your SSL certificate)
# - route53_zone_id (if using Route53)
# - project_name
# - environment
```

## Step 2: Add Missing Variables

### 2.1 Update variables.tf
Add these variables if they don't exist:

```hcl
variable "route53_zone_id" {
  description = "Route53 Hosted Zone ID for hokus.ai"
  type        = string
  default     = ""
}

variable "auth_service_port" {
  description = "Port for auth service"
  type        = number
  default     = 8000
}
```

### 2.2 Update terraform.tfvars
Add your Route53 zone ID:
```hcl
route53_zone_id = "Z1234567890ABC"  # Replace with your actual zone ID
```

To find your zone ID:
```bash
aws route53 list-hosted-zones --query "HostedZones[?Name=='hokus.ai.'].Id" --output text
```

## Step 3: Plan the Deployment

### 3.1 Validate Configuration
```bash
terraform validate
```

### 3.2 Review the Plan
```bash
# First, plan just the new resources
terraform plan -out=alb-plan.tfplan \
  -target=module.dedicated_albs \
  -target=aws_lb.auth \
  -target=aws_lb.registry \
  -target=aws_lb_target_group.auth
```

### 3.3 Review What Will Be Created
The plan should show:
- 2 new ALBs (auth and registry)
- 1 new target group (auth)
- 4 listeners (HTTP/HTTPS for each ALB)
- Multiple listener rules
- 2 Route53 records (if zone_id provided)

## Step 4: Deploy in Phases

### 4.1 Phase 1: Create Target Groups
```bash
# Create the auth target group first
terraform apply -target=aws_lb_target_group.auth

# Verify it was created
aws elbv2 describe-target-groups --names "hokusai-auth-production"
```

### 4.2 Phase 2: Create ALBs
```bash
# Create both ALBs
terraform apply \
  -target=aws_lb.auth \
  -target=aws_lb.registry

# Wait for ALBs to be active (takes 2-3 minutes)
aws elbv2 describe-load-balancers --query "LoadBalancers[?contains(LoadBalancerName, 'hokusai')].{Name:LoadBalancerName,State:State.Code}"
```

### 4.3 Phase 3: Add Listeners
```bash
# Add HTTP listeners (for redirect)
terraform apply \
  -target=aws_lb_listener.auth_http \
  -target=aws_lb_listener.registry_http

# Add HTTPS listeners
terraform apply \
  -target=aws_lb_listener.auth_https \
  -target=aws_lb_listener.registry_https
```

### 4.4 Phase 4: Add Routing Rules
```bash
# Apply all listener rules
terraform apply \
  -target=aws_lb_listener_rule.auth_api_v1 \
  -target=aws_lb_listener_rule.auth_health \
  -target=aws_lb_listener_rule.registry_mlflow \
  -target=aws_lb_listener_rule.registry_api_mlflow \
  -target=aws_lb_listener_rule.registry_api
```

## Step 5: Register ECS Services with New Target Groups

### 5.1 Update Auth Service
If using ECS, update the auth service to register with the new target group:

```bash
# Get current service configuration
aws ecs describe-services --cluster hokusai-cluster --services auth-service

# Update service with new target group
aws ecs update-service \
  --cluster hokusai-cluster \
  --service auth-service \
  --load-balancers targetGroupArn=<NEW_AUTH_TG_ARN>,containerName=auth,containerPort=8000
```

### 5.2 Wait for Healthy Targets
```bash
# Check target health
aws elbv2 describe-target-health \
  --target-group-arn <AUTH_TG_ARN>
```

## Step 6: Test ALBs Before DNS Switch

### 6.1 Get ALB DNS Names
```bash
# Get the DNS names
terraform output auth_alb_dns
terraform output registry_alb_dns
```

### 6.2 Test Using Host Headers
```bash
# Test auth ALB
AUTH_ALB_DNS=$(terraform output -raw auth_alb_dns)
curl -H "Host: auth.hokus.ai" https://${AUTH_ALB_DNS}/health -k

# Test registry ALB  
REGISTRY_ALB_DNS=$(terraform output -raw registry_alb_dns)
curl -H "Host: registry.hokus.ai" https://${REGISTRY_ALB_DNS}/health -k
```

## Step 7: Update DNS Records

### 7.1 Option A: Using Route53 (Automated)
```bash
# Apply Route53 records (only if using Route53)
terraform apply \
  -target=aws_route53_record.auth \
  -target=aws_route53_record.registry
```

### 7.2 Option B: Using Namecheap or Other DNS Providers
**See `NAMECHEAP_DNS_UPDATE_GUIDE.md` for detailed instructions**

Quick summary:
1. Get ALB DNS names from Terraform outputs
2. Log into Namecheap (or your DNS provider)
3. Update records:
   - `auth` → CNAME to Auth ALB DNS
   - `registry` → CNAME to Registry ALB DNS
4. Set TTL to 1 minute during migration
5. Monitor DNS propagation

### 7.3 Monitor DNS Propagation
```bash
# Check DNS resolution
while true; do
  echo "=== $(date) ==="
  dig +short auth.hokus.ai
  dig +short registry.hokus.ai
  sleep 30
done
```

## Step 8: Validate Everything Works

### 8.1 Run Test Script
```bash
export HOKUSAI_API_KEY="hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL"
python test_dedicated_albs.py
```

### 8.2 Test Model Registration
```bash
python test_real_registration.py
```

### 8.3 Monitor CloudWatch
Check for any errors:
```bash
# View target group health
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name UnHealthyHostCount \
  --dimensions Name=TargetGroup,Value=targetgroup/hokusai-auth-production/xxx \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average
```

## Step 9: Cleanup Old Resources (After Validation)

Once everything is working for 24-48 hours:

### 9.1 Remove Old Listener Rules
```bash
# List old rules
aws elbv2 describe-rules --listener-arn <OLD_LISTENER_ARN>

# Remove old routing rules from main.tf
# Comment out or delete the old shared ALB configuration
```

### 9.2 Update Terraform State
```bash
# Remove old resources from state
terraform state rm aws_lb_listener_rule.api
terraform state rm aws_lb_listener_rule.registry_mlflow
# ... etc for old rules
```

## Troubleshooting

### If Services Don't Register with Target Groups
```bash
# Force new deployment
aws ecs update-service --cluster hokusai-cluster --service auth-service --force-new-deployment
```

### If DNS Doesn't Resolve
```bash
# Flush DNS cache (macOS)
sudo dscacheutil -flushcache

# Check authoritative nameservers
dig auth.hokus.ai @8.8.8.8
```

### If Health Checks Fail
```bash
# Check security groups
aws ec2 describe-security-groups --group-ids <ALB_SG_ID>

# Ensure ECS tasks can receive traffic from ALB
```

## Success Criteria

- [ ] Both ALBs show as "active" in AWS console
- [ ] All target groups have healthy targets
- [ ] DNS resolves to new ALB IPs
- [ ] test_dedicated_albs.py passes all tests
- [ ] Model registration works with API key
- [ ] No errors in CloudWatch logs

## Rollback Procedure

If issues occur:
1. Update DNS records back to old ALB
2. Monitor services for stability
3. Debug issues with new ALBs offline
4. Retry deployment after fixes