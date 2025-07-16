# HTTPS Deployment Quick Reference

## Quick Steps to Enable HTTPS

### 1. Request Certificate (5 minutes)
```bash
# Request wildcard certificate
aws acm request-certificate \
  --domain-name "*.hokus.ai" \
  --subject-alternative-names "hokus.ai" \
  --validation-method DNS \
  --region us-east-1

# Note the ARN: arn:aws:acm:us-east-1:123456789012:certificate/xxx
```

### 2. Validate Domain (5-30 minutes)
```bash
# Get validation CNAME records
aws acm describe-certificate \
  --certificate-arn <ARN> \
  --query 'Certificate.DomainValidationOptions[].ResourceRecord'

# Add CNAME records to Route53
# Wait for validation
aws acm wait certificate-validated --certificate-arn <ARN>
```

### 3. Deploy with Terraform (15 minutes)
```bash
cd infrastructure/terraform

# Update terraform.tfvars
echo 'certificate_arn = "arn:aws:acm:us-east-1:xxx"' >> terraform.tfvars

# Deploy
terraform plan
terraform apply
```

### 4. Verify HTTPS Works
```bash
# Test endpoints
curl -I https://api.hokus.ai/health
curl -I https://registry.hokus.ai/mlflow

# Check redirect
curl -I http://api.hokus.ai  # Should redirect to HTTPS
```

## Certificate ARN Format
```
arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012
```

## Rollback If Needed
```bash
# Remove HTTPS (keeps HTTP working)
terraform apply -var="certificate_arn="
```

## Common Issues

### Certificate Not Validating
- Check DNS records: `dig _validation.hokus.ai CNAME`
- Ensure records match exactly
- Wait up to 30 minutes

### HTTPS Not Working  
- Check security groups allow 443
- Verify certificate matches domain
- Review ALB listener rules

### Mixed Content Warnings
- Update all http:// URLs to https://
- Check environment variables
- Update client configurations