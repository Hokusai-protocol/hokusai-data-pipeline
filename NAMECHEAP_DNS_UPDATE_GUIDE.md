# Namecheap DNS Update Guide for Dedicated ALBs

## Overview

Since you're using Namecheap for DNS management, you'll need to manually update DNS records after deploying the new ALBs. This guide walks through the process.

## Step 1: Deploy ALBs First

Before updating DNS, complete the ALB deployment:

```bash
cd infrastructure/terraform

# Deploy without Route53 records
terraform apply \
  -target=aws_lb.auth \
  -target=aws_lb.registry \
  -target=aws_lb_listener.auth_http \
  -target=aws_lb_listener.auth_https \
  -target=aws_lb_listener.registry_http \
  -target=aws_lb_listener.registry_https \
  -target=aws_lb_listener_rule.auth_api_v1 \
  -target=aws_lb_listener_rule.auth_health \
  -target=aws_lb_listener_rule.registry_mlflow \
  -target=aws_lb_listener_rule.registry_api_mlflow \
  -target=aws_lb_listener_rule.registry_api
```

## Step 2: Get ALB DNS Names

After deployment, get the DNS names for both ALBs:

```bash
# Get ALB DNS names
terraform output auth_alb_dns
terraform output registry_alb_dns

# Or use AWS CLI
aws elbv2 describe-load-balancers \
  --names "hokusai-auth-production" "hokusai-registry-production" \
  --query "LoadBalancers[].{Name:LoadBalancerName,DNS:DNSName}" \
  --output table
```

Example output:
- Auth ALB: `hokusai-auth-production-123456789.us-east-1.elb.amazonaws.com`
- Registry ALB: `hokusai-registry-production-987654321.us-east-1.elb.amazonaws.com`

## Step 3: Test ALBs Before DNS Switch

Test the ALBs using curl with Host headers:

```bash
# Test auth ALB
AUTH_ALB_DNS=$(terraform output -raw auth_alb_dns)
curl -H "Host: auth.hokus.ai" https://${AUTH_ALB_DNS}/health -k

# Test registry ALB  
REGISTRY_ALB_DNS=$(terraform output -raw registry_alb_dns)
curl -H "Host: registry.hokus.ai" https://${REGISTRY_ALB_DNS}/health -k
```

## Step 4: Update Namecheap DNS Records

### 4.1 Login to Namecheap
1. Go to https://www.namecheap.com
2. Sign in to your account
3. Navigate to **Domain List**
4. Find `hokus.ai` and click **Manage**

### 4.2 Update DNS Records

In the **Advanced DNS** tab, update these records:

#### For auth.hokus.ai:
1. Find existing `auth` A record or CNAME record
2. Click **Edit** (pencil icon)
3. Change Type to **CNAME Record**
4. Set:
   - **Host**: `auth`
   - **Value**: `hokusai-auth-production-123456789.us-east-1.elb.amazonaws.com` (your Auth ALB DNS)
   - **TTL**: `1 min` (for faster propagation during testing)

#### For registry.hokus.ai:
1. Find existing `registry` A record or CNAME record
2. Click **Edit** (pencil icon)
3. Change Type to **CNAME Record**
4. Set:
   - **Host**: `registry`
   - **Value**: `hokusai-registry-production-987654321.us-east-1.elb.amazonaws.com` (your Registry ALB DNS)
   - **TTL**: `1 min` (for faster propagation during testing)

### 4.3 Save Changes
Click the checkmark (✓) to save each record.

## Step 5: Monitor DNS Propagation

DNS changes can take 5-30 minutes to propagate. Monitor the progress:

```bash
# Check DNS resolution
while true; do
  echo "=== $(date) ==="
  echo "auth.hokus.ai:"
  dig +short auth.hokus.ai
  echo "registry.hokus.ai:"
  dig +short registry.hokus.ai
  echo ""
  sleep 60
done
```

You can also use online tools:
- https://www.whatsmydns.net/#CNAME/auth.hokus.ai
- https://www.whatsmydns.net/#CNAME/registry.hokus.ai

## Step 6: Validate Everything Works

Once DNS has propagated:

```bash
# Test auth service
curl https://auth.hokus.ai/health

# Test registry service
curl https://registry.hokus.ai/health

# Run comprehensive tests
export HOKUSAI_API_KEY="hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL"
python test_dedicated_albs.py
```

## Step 7: Update TTL

After confirming everything works:
1. Go back to Namecheap Advanced DNS
2. Update both records' TTL from `1 min` to `30 min` or `Automatic`
3. This reduces DNS query load

## Rollback Instructions

If you need to rollback:

### Option 1: Quick Rollback
1. Note down the OLD DNS values before making changes
2. In Namecheap, simply update the CNAME values back to the old values
3. DNS will propagate within minutes

### Option 2: Pre-staging Rollback
Before making changes, create backup records:
1. Create `auth-old` CNAME → current auth endpoint
2. Create `registry-old` CNAME → current registry endpoint
3. If rollback needed, just copy these values back

## Important Notes

### About CNAME vs A Records
- **A Records**: Point to IP addresses (e.g., 52.1.2.3)
- **CNAME Records**: Point to domain names (required for ALBs)
- ALBs can change IP addresses, so always use CNAME records

### TTL Considerations
- **Low TTL (1 min)**: Use during migration for quick changes
- **High TTL (30+ min)**: Use in production to reduce DNS queries
- Change to low TTL 24 hours before migration if possible

### Monitoring After Change
- Watch CloudWatch metrics for both ALBs
- Monitor application logs for any DNS-related errors
- Keep the old ALB running for at least 24-48 hours

## Terraform Configuration Update

Since you're using Namecheap, update your Terraform to skip Route53:

```hcl
# In terraform.tfvars
route53_zone_id = ""  # Leave empty to skip Route53 records
```

This will prevent Terraform from trying to create Route53 records.