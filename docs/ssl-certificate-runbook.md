# SSL Certificate Management Runbook

## Overview

This runbook provides procedures for managing SSL certificates for the Hokusai platform, including creation, renewal, troubleshooting, and emergency response procedures.

## Certificate Inventory

| Domain | Type | Certificate ARN | Expiration | Auto-Renewal |
|--------|------|----------------|-------------|--------------|
| *.hokus.ai | Wildcard | arn:aws:acm:us-east-1:... | [Date] | Yes |
| api.hokus.ai | Individual | arn:aws:acm:us-east-1:... | [Date] | Yes |
| www.hokus.ai | Individual | arn:aws:acm:us-east-1:... | [Date] | Yes |
| auth.hokus.ai | Individual | arn:aws:acm:us-east-1:... | [Date] | Yes |

## Regular Maintenance Tasks

### Weekly Checks

1. **Certificate Status Verification**:
   ```bash
   # Check all certificates in ACM
   aws acm list-certificates --region us-east-1 \
     --certificate-statuses ISSUED \
     --query 'CertificateSummaryList[?contains(DomainName, `hokus.ai`)]'
   ```

2. **Expiration Monitoring**:
   ```bash
   # Check days until expiration
   for cert in $(aws acm list-certificates --region us-east-1 --query 'CertificateSummaryList[].CertificateArn' --output text); do
     echo "Certificate: $cert"
     aws acm describe-certificate --certificate-arn $cert \
       --query 'Certificate.NotAfter' --output text
   done
   ```

### Monthly Tasks

1. **SSL Configuration Audit**:
   ```bash
   # Test SSL configuration
   ./scripts/ssl-audit.sh api.hokus.ai
   ./scripts/ssl-audit.sh www.hokus.ai
   ./scripts/ssl-audit.sh auth.hokus.ai
   ```

2. **Update Documentation**:
   - Review and update certificate inventory
   - Verify contact information is current
   - Update runbook with any new procedures

## Certificate Renewal Procedures

### Automatic Renewal (Normal Process)

ACM automatically renews certificates 30-60 days before expiration. Monitor the process:

1. **Check Renewal Status**:
   ```bash
   aws acm describe-certificate \
     --certificate-arn <CERTIFICATE_ARN> \
     --query 'Certificate.RenewalSummary'
   ```

2. **Verify DNS Validation Records**:
   ```bash
   # Ensure validation CNAME records still exist
   aws route53 list-resource-record-sets \
     --hosted-zone-id <ZONE_ID> \
     --query "ResourceRecordSets[?Type=='CNAME' && contains(Name, '_')]"
   ```

### Manual Renewal (If Automatic Fails)

1. **Request New Certificate**:
   ```bash
   aws acm request-certificate \
     --domain-name "*.hokus.ai" \
     --subject-alternative-names "hokus.ai" \
     --validation-method DNS \
     --region us-east-1
   ```

2. **Update Infrastructure**:
   ```bash
   # Update Terraform variables
   cd infrastructure/terraform
   vim terraform.tfvars  # Update certificate_arn
   terraform plan
   terraform apply
   ```

3. **Verify New Certificate**:
   ```bash
   curl -vI https://api.hokus.ai 2>&1 | grep -A 5 "SSL certificate"
   ```

## Troubleshooting Guide

### Issue: Certificate Validation Pending

**Symptoms**: Certificate stuck in "Pending Validation" status

**Resolution**:
1. Check DNS validation records:
   ```bash
   aws acm describe-certificate --certificate-arn <ARN> \
     --query 'Certificate.DomainValidationOptions[].ResourceRecord'
   ```

2. Verify DNS propagation:
   ```bash
   dig _<validation-string>.hokus.ai CNAME +short
   ```

3. Re-add validation records if missing:
   ```bash
   aws route53 change-resource-record-sets \
     --hosted-zone-id <ZONE_ID> \
     --change-batch file://validation-cname.json
   ```

### Issue: Certificate Not Auto-Renewing

**Symptoms**: Certificate approaching expiration without renewal

**Resolution**:
1. Check renewal eligibility:
   ```bash
   aws acm describe-certificate --certificate-arn <ARN> \
     --query 'Certificate.RenewalEligibility'
   ```

2. Common causes:
   - DNS validation records removed
   - Certificate not in use by any AWS service
   - Account/payment issues

3. Force renewal by requesting new certificate

### Issue: Mixed Content Warnings

**Symptoms**: Browser shows security warnings about mixed content

**Resolution**:
1. Identify mixed content:
   ```bash
   # Use browser developer tools or
   curl https://api.hokus.ai | grep -i "http://"
   ```

2. Update application configuration:
   - Environment variables
   - Database stored URLs
   - Frontend asset references

### Issue: SSL Handshake Failures

**Symptoms**: SSL connection errors, timeouts

**Resolution**:
1. Test SSL handshake:
   ```bash
   openssl s_client -connect api.hokus.ai:443 -servername api.hokus.ai
   ```

2. Check cipher suites:
   ```bash
   nmap --script ssl-enum-ciphers -p 443 api.hokus.ai
   ```

3. Verify ALB SSL policy in Terraform

## Emergency Procedures

### Certificate Expired

**CRITICAL - Immediate Action Required**

1. **Request Emergency Certificate**:
   ```bash
   # Request with email validation for faster processing
   aws acm request-certificate \
     --domain-name "api.hokus.ai" \
     --validation-method EMAIL \
     --region us-east-1
   ```

2. **Temporary Mitigation**:
   ```bash
   # Revert to HTTP (emergency only)
   cd infrastructure/terraform
   terraform apply -var="certificate_arn="
   ```

3. **Fast-Track Deployment**:
   ```bash
   # Once certificate issued
   export CERT_ARN=$(aws acm list-certificates --query "CertificateSummaryList[?DomainName=='api.hokus.ai'].CertificateArn" --output text)
   terraform apply -var="certificate_arn=$CERT_ARN" -auto-approve
   ```

### Certificate Compromised

1. **Immediate Revocation**:
   ```bash
   # ACM doesn't support revocation - must delete
   aws acm delete-certificate --certificate-arn <COMPROMISED_ARN>
   ```

2. **Request Replacement**:
   ```bash
   aws acm request-certificate \
     --domain-name "*.hokus.ai" \
     --validation-method DNS \
     --region us-east-1
   ```

3. **Update All Services**:
   - Update Terraform with new ARN
   - Redeploy all services
   - Audit for any unauthorized access

## Monitoring and Alerts

### CloudWatch Alarms

1. **Certificate Expiration Alert**:
   ```json
   {
     "AlarmName": "hokusai-cert-expiry-warning",
     "MetricName": "DaysToExpiry",
     "Namespace": "AWS/CertificateManager",
     "Statistic": "Average",
     "Period": 86400,
     "EvaluationPeriods": 1,
     "Threshold": 30,
     "ComparisonOperator": "LessThanThreshold"
   }
   ```

2. **SSL Endpoint Health**:
   ```json
   {
     "AlarmName": "hokusai-https-health",
     "MetricName": "TargetResponseTime",
     "Namespace": "AWS/ApplicationELB",
     "Dimensions": [{
       "Name": "LoadBalancer",
       "Value": "app/hokusai-production/*"
     }],
     "Statistic": "Average",
     "Period": 300,
     "Threshold": 1000
   }
   ```

### Notification Channels

1. **Primary**: PagerDuty integration for critical alerts
2. **Secondary**: Email to ops@hokus.ai
3. **Escalation**: SMS to on-call engineer

## Scripts and Tools

### SSL Audit Script

Create `scripts/ssl-audit.sh`:
```bash
#!/bin/bash
DOMAIN=$1

echo "=== SSL Audit for $DOMAIN ==="
echo ""

# Check certificate details
echo "Certificate Information:"
echo | openssl s_client -servername $DOMAIN -connect $DOMAIN:443 2>/dev/null | openssl x509 -noout -text | grep -E "(Subject:|Issuer:|Not Before|Not After)"

echo ""
echo "SSL Labs Grade:"
curl -s "https://api.ssllabs.com/api/v3/analyze?host=$DOMAIN&publish=off&ignoreMismatch=on&all=done" | jq -r '.endpoints[0].grade'

echo ""
echo "Supported Protocols:"
nmap --script ssl-enum-ciphers -p 443 $DOMAIN | grep -E "TLSv|SSLv" | head -5

echo ""
echo "Certificate Chain:"
echo | openssl s_client -servername $DOMAIN -connect $DOMAIN:443 -showcerts 2>/dev/null | grep -E "s:|i:"
```

### Quick Certificate Check

Create `scripts/cert-check.sh`:
```bash
#!/bin/bash
# Quick certificate expiration check

DOMAINS=("api.hokus.ai" "www.hokus.ai" "auth.hokus.ai")

for domain in "${DOMAINS[@]}"; do
  echo -n "$domain expires: "
  echo | openssl s_client -servername $domain -connect $domain:443 2>/dev/null | openssl x509 -noout -enddate | cut -d= -f2
done
```

## Best Practices

1. **Always use DNS validation** for certificates (more reliable than email)
2. **Request certificates in us-east-1** for CloudFront compatibility
3. **Use wildcard certificates** to reduce management overhead
4. **Tag certificates** with environment and purpose
5. **Document all certificate changes** in deployment logs
6. **Test in staging** before production certificate changes
7. **Keep validation records** even after certificate is issued
8. **Monitor expiration** at 60, 30, and 7 days
9. **Have emergency contacts** for DNS and AWS account access
10. **Practice renewal procedures** quarterly in non-production

## Contact Information

- **AWS Support**: [Support case URL]
- **DNS Management**: dns-admin@hokus.ai
- **Security Team**: security@hokus.ai
- **On-Call**: [PagerDuty integration]