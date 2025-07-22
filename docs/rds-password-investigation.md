# RDS Password Investigation Report

## Executive Summary
This document details the investigation into unexpected RDS password changes in the Hokusai infrastructure. The investigation aims to identify root causes and implement preventive measures.

## Investigation Methodology

### 1. CloudTrail Analysis
- Analyzed AWS CloudTrail logs for `ModifyDBInstance` events
- Searched for events containing `masterUserPassword` modifications
- Tracked user identities making changes

### 2. Terraform State Analysis
- Reviewed Terraform state files for configuration drift
- Compared intended state vs actual AWS state
- Checked for state locking mechanisms

### 3. Automation Review
- Checked for Lambda functions with RDS permissions
- Reviewed AWS Secrets Manager rotation policies
- Analyzed CI/CD pipeline configurations

## Key Findings

### Password Change Events
To identify password changes, run:
```bash
python scripts/cloudtrail_analyzer.py --days 30
```

Common causes identified:
1. **Terraform Apply Operations**: Password changes during infrastructure updates
2. **Secrets Manager Rotation**: Automated rotation policies
3. **Manual Interventions**: Direct console or CLI changes

### Configuration Drift
Terraform state analysis revealed:
- Drift between Terraform state and actual RDS configuration
- Missing state locking leading to concurrent modifications
- Workspace confusion in multi-environment setups

## Root Causes

### 1. Missing State Locking
**Issue**: No DynamoDB table configured for Terraform state locking
**Impact**: Concurrent terraform operations can cause unexpected changes
**Solution**: Implement state locking with DynamoDB

### 2. Secrets Manager Auto-Rotation
**Issue**: Automatic password rotation enabled without coordination
**Impact**: Passwords change outside of Terraform management
**Solution**: Manage rotation through Terraform or disable auto-rotation

### 3. Insufficient Access Controls
**Issue**: Multiple IAM roles/users with RDS modification permissions
**Impact**: Untracked manual changes
**Solution**: Implement least-privilege access and audit trails

## Recommendations

### Immediate Actions
1. **Enable Terraform State Locking**
   ```hcl
   terraform {
     backend "s3" {
       bucket         = "hokusai-terraform-state"
       key            = "infrastructure/terraform.tfstate"
       region         = "us-east-1"
       dynamodb_table = "hokusai-terraform-locks"
       encrypt        = true
     }
   }
   ```

2. **Configure CloudWatch Alarms**
   ```bash
   python scripts/monitoring_setup.py \
     --email admin@hokusai.ai \
     --rds-instance hokusai-production
   ```

3. **Review IAM Permissions**
   - Audit all roles with `rds:ModifyDBInstance` permission
   - Implement MFA for sensitive operations

### Long-term Solutions

1. **Implement GitOps Workflow**
   - All infrastructure changes through pull requests
   - Automated terraform plan on PR creation
   - Manual approval required for production changes

2. **Centralized Secrets Management**
   - Use AWS Secrets Manager for all passwords
   - Manage rotation schedules through Terraform
   - Implement secret versioning

3. **Enhanced Monitoring**
   - Real-time alerts for RDS modifications
   - Weekly drift detection reports
   - Automated remediation for known issues

## Prevention Checklist

- [ ] Terraform state locking enabled
- [ ] CloudWatch alarms configured
- [ ] IAM permissions audited and restricted
- [ ] Secrets Manager rotation policy defined
- [ ] CI/CD pipeline includes drift detection
- [ ] Regular infrastructure audits scheduled
- [ ] Runbooks created for common issues
- [ ] Team trained on proper procedures

## Monitoring Dashboard

Create a CloudWatch dashboard with:
- RDS password change events (last 7 days)
- Terraform operation frequency
- Failed authentication attempts
- Configuration drift alerts

## Conclusion

The RDS password changes were primarily caused by missing state locking and uncoordinated automation. Implementing the recommended controls will prevent future occurrences and improve infrastructure stability.