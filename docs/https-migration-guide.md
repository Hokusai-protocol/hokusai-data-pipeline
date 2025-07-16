# HTTPS Migration Guide for Hokusai Platform

## Overview

This guide provides step-by-step instructions for enabling HTTPS across all Hokusai domains. The infrastructure is already configured to support HTTPS; only SSL certificates need to be provisioned and configured.

## Prerequisites

- AWS account access with permissions for:
  - AWS Certificate Manager (ACM)
  - Route53
  - EC2/ALB management
  - IAM role management
- Access to DNS management for hokus.ai domain
- Terraform installed locally
- AWS CLI configured

## Step 1: Request SSL Certificates

### Option A: Wildcard Certificate (Recommended)

1. Access AWS Certificate Manager in the deployment region (us-east-1):
   ```bash
   aws acm request-certificate \
     --domain-name "*.hokus.ai" \
     --subject-alternative-names "hokus.ai" \
     --validation-method DNS \
     --region us-east-1
   ```

2. Note the Certificate ARN returned

### Option B: Individual Certificates

If wildcard certificates are not permitted, request individual certificates:

```bash
# API certificate
aws acm request-certificate \
  --domain-name "api.hokus.ai" \
  --validation-method DNS \
  --region us-east-1

# WWW certificate  
aws acm request-certificate \
  --domain-name "www.hokus.ai" \
  --validation-method DNS \
  --region us-east-1

# Auth certificate (for other repository)
aws acm request-certificate \
  --domain-name "auth.hokus.ai" \
  --validation-method DNS \
  --region us-east-1
```

## Step 2: Validate Domain Ownership

1. For each certificate request, ACM will provide CNAME records to add to your DNS:
   ```bash
   aws acm describe-certificate \
     --certificate-arn <CERTIFICATE_ARN> \
     --region us-east-1
   ```

2. Add the validation CNAME records to Route53:
   ```bash
   aws route53 change-resource-record-sets \
     --hosted-zone-id <ZONE_ID> \
     --change-batch file://validation-records.json
   ```

   Example validation-records.json:
   ```json
   {
     "Changes": [{
       "Action": "CREATE",
       "ResourceRecordSet": {
         "Name": "_<VALIDATION_ID>.hokus.ai",
         "Type": "CNAME",
         "TTL": 300,
         "ResourceRecords": [{
           "Value": "_<VALIDATION_VALUE>.acm-validations.aws."
         }]
       }
     }]
   }
   ```

3. Wait for certificate validation (typically 5-30 minutes):
   ```bash
   aws acm wait certificate-validated \
     --certificate-arn <CERTIFICATE_ARN> \
     --region us-east-1
   ```

## Step 3: Update Terraform Configuration

1. Create or update `terraform.tfvars`:
   ```hcl
   certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012"
   domain_name = "hokus.ai"
   ```

2. If using multiple certificates, update the Terraform configuration to support multiple ARNs:
   ```hcl
   # In variables.tf
   variable "certificate_arns" {
     description = "Map of domain names to certificate ARNs"
     type        = map(string)
     default     = {}
   }
   
   # In terraform.tfvars
   certificate_arns = {
     "api.hokus.ai" = "arn:aws:acm:us-east-1:..."
     "www.hokus.ai" = "arn:aws:acm:us-east-1:..."
   }
   ```

## Step 4: Update Load Balancer Configuration

The Terraform configuration already includes HTTPS listener setup. To enable it:

1. Run Terraform plan to preview changes:
   ```bash
   cd infrastructure/terraform
   terraform plan
   ```

2. Review the changes carefully, ensuring:
   - HTTPS listener will be created on port 443
   - HTTP to HTTPS redirect is configured
   - Security groups allow port 443

3. Apply the changes:
   ```bash
   terraform apply
   ```

## Step 5: Configure HTTP to HTTPS Redirect

Add a redirect rule to the HTTP listener (this is already in the Terraform but needs to be updated):

```hcl
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"
  
  default_action {
    type = "redirect"
    
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}
```

## Step 6: Update DNS Records

No DNS changes should be needed if the load balancer DNS name remains the same. However, verify:

1. Check current DNS records:
   ```bash
   aws route53 list-resource-record-sets \
     --hosted-zone-id <ZONE_ID> \
     --query "ResourceRecordSets[?Name=='api.hokus.ai.']"
   ```

2. Ensure they point to the load balancer:
   - Type: A (Alias)
   - Alias Target: Load Balancer DNS name

## Step 7: Testing and Validation

1. Test HTTPS access:
   ```bash
   # Test API endpoint
   curl -I https://api.hokus.ai/health
   
   # Test redirect
   curl -I http://api.hokus.ai/health
   ```

2. Validate SSL certificate:
   ```bash
   openssl s_client -connect api.hokus.ai:443 -servername api.hokus.ai < /dev/null
   ```

3. Use online SSL checkers:
   - https://www.ssllabs.com/ssltest/
   - https://www.sslshopper.com/ssl-checker.html

## Step 8: Update Application Configuration

1. Update environment variables in ECS task definitions:
   - Change any hardcoded HTTP URLs to HTTPS
   - Update API_URL, CALLBACK_URL, etc.

2. Update application code if needed:
   - Search for hardcoded "http://" references
   - Update configuration files

## Rollback Plan

If issues occur:

1. Remove the HTTPS listener:
   ```bash
   terraform apply -var="certificate_arn="
   ```

2. This will disable HTTPS but keep HTTP working

3. Investigate issues before re-attempting

## Monitoring and Alerts

Configure CloudWatch alarms for:
- Certificate expiration (ACM handles auto-renewal, but monitor)
- HTTPS endpoint availability
- SSL handshake errors

Example alarm:
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "hokusai-cert-expiry" \
  --alarm-description "Alert when certificate expires in 30 days" \
  --metric-name DaysToExpiry \
  --namespace AWS/CertificateManager \
  --statistic Average \
  --period 86400 \
  --threshold 30 \
  --comparison-operator LessThanThreshold
```

## Certificate Renewal

ACM automatically renews certificates 30 days before expiration. However:
1. Ensure DNS validation records remain in place
2. Monitor renewal status in ACM console
3. Set up SNS notifications for renewal events

## Troubleshooting

### Certificate Not Validating
- Check DNS propagation: `dig _<validation>.hokus.ai CNAME`
- Ensure validation records are exact matches
- Check Route53 hosted zone is authoritative

### HTTPS Not Working
- Verify security groups allow port 443
- Check listener rules in ALB
- Ensure certificate matches domain name
- Review ALB access logs

### Mixed Content Warnings
- Update all resource URLs to HTTPS
- Check for hardcoded HTTP links in:
  - Frontend code
  - API responses
  - Configuration files