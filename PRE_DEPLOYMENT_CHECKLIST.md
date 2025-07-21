# Pre-Deployment Checklist for Dedicated ALBs

## Before You Start

### 1. AWS Access Verification
```bash
# Verify AWS credentials
aws sts get-caller-identity

# Check you have permissions for:
aws elbv2 describe-load-balancers --max-items 1
aws route53 list-hosted-zones --max-items 1
aws acm list-certificates --max-items 1
```

### 2. Required Information
Gather these values:

- [ ] **Certificate ARN**: 
  ```bash
  aws acm list-certificates --query "CertificateSummaryList[?DomainName=='*.hokus.ai'].CertificateArn" --output text
  ```

- [ ] **Route53 Zone ID**: 
  ```bash
  aws route53 list-hosted-zones --query "HostedZones[?Name=='hokus.ai.'].Id" --output text
  ```

- [ ] **VPC ID**: 
  ```bash
  aws ec2 describe-vpcs --query "Vpcs[?IsDefault==true].VpcId" --output text
  ```

- [ ] **Public Subnet IDs**: 
  ```bash
  aws ec2 describe-subnets --query "Subnets[?MapPublicIpOnLaunch==true].SubnetId" --output text
  ```

### 3. Current Infrastructure Check
```bash
# Check existing ALBs
aws elbv2 describe-load-balancers --query "LoadBalancers[].LoadBalancerName"

# Check existing target groups
aws elbv2 describe-target-groups --query "TargetGroups[].TargetGroupName"

# Note any that contain "auth" or "registry" to avoid naming conflicts
```

### 4. Service Information
Document current service details:

- [ ] Auth service port: _______ (typically 8000)
- [ ] Auth service health check path: _______ (typically /health)
- [ ] Number of auth service instances: _______
- [ ] Current auth service endpoint: _______

### 5. Terraform Preparation
```bash
cd infrastructure/terraform

# Install providers
terraform init

# Format check
terraform fmt -check

# Validate syntax
terraform validate
```

### 6. Communication Plan
- [ ] Notify team of upcoming changes
- [ ] Schedule deployment window (recommend low-traffic period)
- [ ] Prepare rollback communication

## Quick Start Commands

Once you have all the information above:

```bash
# 1. Export variables
export TF_VAR_certificate_arn="arn:aws:acm:region:account:certificate/xxx"
export TF_VAR_route53_zone_id="Z1234567890ABC"

# 2. Create a deployment plan
terraform plan -out=dedicated-albs.tfplan

# 3. Review the plan
terraform show dedicated-albs.tfplan

# 4. If everything looks good, proceed with the deployment guide
```

## Emergency Contacts

Document these before starting:
- AWS Support Case URL: _______
- Team Slack Channel: _______
- On-call Engineer: _______