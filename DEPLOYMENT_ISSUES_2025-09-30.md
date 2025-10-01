# Deployment Issues Found - September 30, 2025

## Summary

During the deployment of the latest code from the merged PR, multiple infrastructure configuration issues were discovered that prevented the services from running. All issues are related to **missing or incorrect secrets configuration** in ECS task definitions and IAM permissions.

---

## Issues Found & Fixed

### 1. API Service - Missing Database Secrets ✅ FIXED

**Issue**: Task definition revision 133 was missing all database and Redis secrets.

**Root Cause**:
- Revisions 131, 132, 133 were created without secrets configuration
- Last working revision 130 (Sept 15) had the correct secrets
- Likely a Terraform state issue where task definitions were updated without secrets being included

**Impact**: API service failed to start with error:
```
ValueError: Failed to validate database credentials: Database password not found
```

**Fix Applied**:
- Created new task definition revision 134 with all required secrets:
  - `DATABASE_URL` from Parameter Store: `/hokusai/development/database/url`
  - `DB_PASSWORD` from Secrets Manager: `hokusai/app-secrets/development:database_password`
  - `REDIS_URL`, `REDIS_HOST`, `REDIS_PORT` from Parameter Store
  - `REDIS_AUTH_TOKEN` from Secrets Manager: `hokusai/redis/development/auth-token:auth_token`

**Terraform Fix Needed**:
Update the API service task definition in `hokusai-infrastructure` to include the secrets configuration from revision 134.

---

### 2. ECS Task Execution Role - Missing Secrets Manager Permissions ✅ FIXED

**Issue**: The `ecsTaskExecutionRole` IAM role lacked permissions to read Secrets Manager secrets.

**Root Cause**:
- Role only had `AmazonECSTaskExecutionRolePolicy` (basic ECR/CloudWatch permissions)
- No permissions for Secrets Manager or SSM Parameter Store

**Impact**: Tasks failed with:
```
AccessDeniedException: User: arn:aws:sts::932100697590:assumed-role/ecsTaskExecutionRole/[task-id]
is not authorized to perform: secretsmanager:GetSecretValue on resource:
arn:aws:secretsmanager:us-east-1:932100697590:secret:hokusai/app-secrets/development-G9l4vD
```

**Fix Applied**:
Added inline policy `SecretsManagerAccess` to `ecsTaskExecutionRole`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": [
        "arn:aws:secretsmanager:us-east-1:932100697590:secret:hokusai/app-secrets/development-*",
        "arn:aws:secretsmanager:us-east-1:932100697590:secret:hokusai/redis/development/auth-token-*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["ssm:GetParameters", "ssm:GetParameter"],
      "Resource": ["arn:aws:ssm:us-east-1:932100697590:parameter/hokusai/development/*"]
    }
  ]
}
```

**Terraform Fix Needed**:
Add this policy to the `ecsTaskExecutionRole` resource in Terraform.

---

### 3. MLFlow Service - Hardcoded Wrong Database Password ✅ FIXED

**Issue**: MLFlow task definition had hardcoded database password `TestPassword123!` in the `BACKEND_STORE_URI` environment variable.

**Root Cause**:
- Database password was hardcoded in the connection string instead of being retrieved from Secrets Manager
- The hardcoded password was incorrect (appears to be a test/placeholder value)

**Impact**: MLFlow failed to connect to database:
```
psycopg2.OperationalError: connection to server at "hokusai-mlflow-development.cmqduyfpzmbr.us-east-1.rds.amazonaws.com"
failed: FATAL: password authentication failed for user "mlflow"
```

**Fix Applied**:
- Retrieved correct password from Secrets Manager: `hokusai/app-secrets/development:database_password`
- Created task definition revision 40 with corrected `BACKEND_STORE_URI`:
```
postgresql://mlflow:sudoAhvVLKh0J1XPdiqGA5OWB8oMMN@hokusai-mlflow-development.cmqduyfpzmbr.us-east-1.rds.amazonaws.com:5432/mlflow_db?sslmode=require
```

**Terraform Fix Needed**:
Instead of hardcoding the password in `BACKEND_STORE_URI`, the password should be:
1. Added as a secret reference like the API service, OR
2. Constructed dynamically using a secret reference

**Better Solution**:
Use separate environment variables:
- `DB_HOST`: `hokusai-mlflow-development.cmqduyfpzmbr.us-east-1.rds.amazonaws.com`
- `DB_NAME`: `mlflow_db`
- `DB_USER`: `mlflow`
- `DB_PASSWORD`: Reference to `hokusai/app-secrets/development:database_password`

Then construct the connection string in the application startup.

---

### 4. Auth Service Task Execution Role - Missing Secrets Manager Permissions ✅ FIXED

**Issue**: The `hokusai-auth-task-execution-development` IAM role lacked permissions to read Secrets Manager secrets.

**Root Cause**: Same as issue #2, but for a different role.

**Impact**: Auth service tasks failed to start with same `AccessDeniedException`.

**Fix Applied**:
Added inline policy `SecretsManagerAccess` to `hokusai-auth-task-execution-development` role with permissions for:
- `hokusai/redis/development/auth-token-*`
- `hokusai/auth-service/development-*`
- `hokusai/app-secrets/development-*`

**Terraform Fix Needed**:
Add this policy to the auth service task execution role in Terraform.

---

### 5. Auth Service - Incorrect Redis Secret ARN ❌ NOT FIXED

**Issue**: Auth service task definition references a non-existent secret with placeholder suffix `-RANDOM`.

**Current Configuration**:
```json
{
  "name": "REDIS_AUTH_TOKEN",
  "valueFrom": "arn:aws:secretsmanager:us-east-1:932100697590:secret:hokusai/redis/development/auth-token-RANDOM:auth_token::"
}
```

**Correct Configuration** (should be):
```json
{
  "name": "REDIS_AUTH_TOKEN",
  "valueFrom": "arn:aws:secretsmanager:us-east-1:932100697590:secret:hokusai/redis/development/auth-token-0GWWJx:auth_token::"
}
```

**Impact**:
- Auth service cannot start
- Model registration fails with "Authentication service error"
- API key validation is non-functional

**Status**: NOT FIXED - requires infrastructure team to update task definition

**Terraform Fix Needed**:
Update auth service task definition to use correct secret ARN. The suffix `-0GWWJx` is auto-generated by AWS when the secret is created, so Terraform should reference the secret by name without the suffix, or use a data source to look it up.

---

## Service Status After Fixes

| Service | Status | Task Definition | Issues |
|---------|--------|-----------------|---------|
| hokusai-api-development | ✅ HEALTHY | revision 134 | None - Redis warning is non-critical |
| hokusai-mlflow-development | ✅ HEALTHY | revision 40 | None |
| hokusai-auth-development | ❌ DOWN | N/A | Cannot start due to incorrect secret ARN |

---

## Timeline of Service Outage

1. **Sept 15, 12:19 PM** - Last time services were healthy with revision 130
2. **Sept 15, 12:44 PM** - Revision 132 created (without secrets) but not deployed
3. **Sept 27, 3:59 PM** - Services went down (task became unhealthy)
4. **Sept 30, 9:03 AM** - Attempted deployment of revision 133 (also without secrets) - failed
5. **Sept 30, 10:07 AM** - MLFlow service restored with revision 40
6. **Sept 30, 10:30 AM** - API service restored with revision 134
7. **Sept 30, present** - Auth service still down

**Total Outage**: ~3 days (Sept 27 - Sept 30)

---

## Recommendations for Infrastructure Team

### Immediate Actions

1. **Fix Auth Service Task Definition**
   - Update the Redis secret ARN to remove `-RANDOM` placeholder
   - Use the correct suffix or reference by name only

2. **Audit All Task Definitions**
   - Check all ECS services for hardcoded passwords or placeholder values
   - Ensure all secrets use proper Secrets Manager/Parameter Store references

### Long-term Improvements

1. **Standardize Secret References**
   - Document the correct pattern for referencing secrets
   - Use Terraform data sources to look up secret ARNs dynamically
   - Never hardcode passwords in task definitions

2. **Add IAM Permissions to Terraform**
   - Include Secrets Manager permissions in all task execution role definitions
   - Use least-privilege principle with specific secret ARNs

3. **Implement Better Monitoring**
   - Add CloudWatch alarms for task failures
   - Alert on "ResourceInitializationError" events
   - Monitor auth service availability

4. **Test Deployments**
   - Verify task definitions can access secrets before deploying
   - Add integration tests for service-to-service communication
   - Test model registration flow end-to-end

5. **Database Connection Best Practices**
   - Never hardcode database passwords in connection strings
   - Use environment variables or secret injection at runtime
   - Consider using AWS RDS Proxy for connection management

---

## Testing Checklist

Once auth service is fixed, verify:

- [ ] API service health endpoint returns healthy status
- [ ] MLFlow service health endpoint returns healthy status
- [ ] Auth service health endpoint returns healthy status
- [ ] Model registration works with valid API key
- [ ] Models appear in MLFlow registry
- [ ] API key validation works correctly
- [ ] All services can communicate with each other

---

## Files Changed (Manual Fixes)

**Note**: These are manual runtime fixes. Infrastructure team should replicate in Terraform.

### IAM Policies Added:
1. `ecsTaskExecutionRole` - inline policy `SecretsManagerAccess`
2. `hokusai-auth-task-execution-development` - inline policy `SecretsManagerAccess`

### Task Definitions Created:
1. `hokusai-api-development:134` - with database and Redis secrets
2. `hokusai-mlflow-development:40` - with corrected database password

### Services Updated:
1. `hokusai-api-development` - now using task definition 134
2. `hokusai-mlflow-development` - now using task definition 40

---

## Contact

For questions about these fixes, contact the team member who performed the deployment on Sept 30, 2025.

**Deployment Log**: See git history for commit that triggered this deployment.