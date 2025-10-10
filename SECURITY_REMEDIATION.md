# Security Remediation Guide - GitGuardian Alert

**Alert Date**: 2025-10-09
**Commit**: [c0e5fab](https://github.com/Hokusai-protocol/hokusai-data-pipeline/commit/c0e5fab09a33c4749028fcd4e4dad14ec9b53fa1)
**Status**: ✅ PRODUCTION SECRETS ROTATED | ⚠️ Local dev setup required

## Summary

Multiple files with credentials were exposed when the repository was made public:
1. `docker-compose.yml` - Local development credentials (low risk)
2. `infrastructure/terraform/terraform.tfvars` - **PRODUCTION SECRETS** (high risk) ✅ **ROTATED**

## Exposed Credentials

### 🟡 Docker Compose (Local Development - Low Risk)

1. **PostgreSQL Database**
   - Username: `mlflow`
   - Password: `mlflow_password`
   - Database: `mlflow_db`

2. **MinIO S3 Storage**
   - Username: `minioadmin`
   - Password: `minioadmin123`

3. **Grafana Dashboard**
   - Username: `admin`
   - Password: `admin123`

### 🔴 Terraform Variables (PRODUCTION - High Risk)

**File**: `infrastructure/terraform/terraform.tfvars` (commit c0e5fab)

4. **Database Password (PRODUCTION)**
   - Exposed Value: `YcAhadh5KTR/EuRta9Da3ddgplkvQ35X/1ICAurSr+k=`
   - **Status**: ✅ **ROTATED** (confirmed by user)
   - Used for: Production RDS PostgreSQL instance

5. **API Secret Key (PRODUCTION)**
   - Exposed Value: `A544iJ7a7GGy9x4fczYdzFrHM`
   - **Status**: ✅ **ROTATED** (confirmed by user)
   - Used for: FastAPI JWT token signing

## ✅ Completed Fixes

1. ✅ Removed all hardcoded secrets from `docker-compose.yml`
2. ✅ Updated `docker-compose.yml` to use environment variables
3. ✅ Updated `.env.example` with secure placeholder values
4. ✅ Enhanced `.gitignore` to prevent future `.env` file commits
5. ✅ Removed `terraform.tfvars` from Git tracking
6. ✅ Enhanced `.gitignore` to block all `*.tfvars` files (except `.example`)
7. ✅ Production secrets rotated in AWS (database password, API secret key)

## 🔴 IMMEDIATE ACTIONS REQUIRED

### Step 1: Create Your Local `.env` File

Copy the example and generate strong passwords:

```bash
cp .env.example .env
```

Then edit `.env` and replace ALL placeholder values with secure passwords:

```bash
# Generate secure passwords (macOS/Linux)
openssl rand -base64 32  # Use this for each password field

# Or use this one-liner to create .env with random passwords
cat > .env << 'EOF'
# PostgreSQL - CHANGE THESE
POSTGRES_USER=mlflow
POSTGRES_PASSWORD=$(openssl rand -base64 32)
POSTGRES_DB=mlflow_db
DB_PASSWORD=$(openssl rand -base64 32)

# MinIO - CHANGE THESE
MINIO_ROOT_USER=$(openssl rand -hex 16)
MINIO_ROOT_PASSWORD=$(openssl rand -base64 32)

# Grafana - CHANGE THESE
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 32)
EOF
```

### Step 2: Verify `.env` is Excluded from Git

```bash
# This should return nothing (file is ignored)
git status .env

# This should show ".env"
git check-ignore .env
```

### Step 3: Check Production Secrets

**Critical**: Determine if these credentials were EVER used in production:

```bash
# Check ECS task definitions
aws ecs describe-task-definition --task-definition hokusai-mlflow-development

# Check ECS services
aws ecs describe-services --cluster hokusai-development --services hokusai-mlflow-development

# Check Secrets Manager
aws secretsmanager list-secrets --filters Key=name,Values=hokusai
```

### Step 4: Rotate Production Secrets (if applicable)

If any of these credentials were used in production:

#### 4a. RDS PostgreSQL
```bash
# Change the master password
aws rds modify-db-instance \
  --db-instance-identifier hokusai-mlflow-production \
  --master-user-password "$(openssl rand -base64 32)" \
  --apply-immediately

# Update Secrets Manager
aws secretsmanager update-secret \
  --secret-id hokusai/database/credentials \
  --secret-string '{"password":"NEW_PASSWORD_HERE"}'
```

#### 4b. Update ECS Task Definitions
```bash
# Force new deployment with updated secrets
aws ecs update-service \
  --cluster hokusai-production \
  --service hokusai-mlflow-production \
  --force-new-deployment
```

### Step 5: History Rewrite - NOT RECOMMENDED ❌

**Should you rewrite Git history to remove the secrets?**

**NO - Here's why:**

1. **Repository is public** - Secrets already exposed to the world
2. **116 commits** made since exposure (massive disruption)
3. **57+ branches** contain the commit (would all break)
4. **GitHub caches commits** even after force-push
5. **GitGuardian/scanners** have already indexed the secrets
6. **Anyone who cloned** still has the full history with secrets
7. **Production secrets already rotated** ✅ - main risk mitigated

**What history rewrite CANNOT do:**
- Remove secrets from GitHub's cache
- Remove secrets from security scanner databases
- Remove secrets from existing clones/forks
- Undo the public exposure

**Correct approach:**
1. ✅ Rotate all exposed production secrets (DONE)
2. ✅ Remove files from future commits (DONE)
3. ✅ Update `.gitignore` (DONE)
4. ✅ Monitor for unauthorized access using rotated credentials
5. Accept that history is permanent - focus on prevention

## 🔒 AWS Secrets Manager Setup (Recommended for Production)

### Create Secrets in AWS

```bash
# Database credentials
aws secretsmanager create-secret \
  --name hokusai/database/mlflow \
  --description "MLflow PostgreSQL credentials" \
  --secret-string '{
    "username": "mlflow",
    "password": "GENERATED_SECURE_PASSWORD",
    "host": "hokusai-mlflow-production.xxxxx.rds.amazonaws.com",
    "port": 5432,
    "dbname": "mlflow_db"
  }'

# MinIO/S3 credentials (if used in production)
aws secretsmanager create-secret \
  --name hokusai/storage/s3 \
  --description "S3 storage credentials" \
  --secret-string '{
    "access_key_id": "GENERATED_ACCESS_KEY",
    "secret_access_key": "GENERATED_SECRET_KEY"
  }'

# Grafana admin credentials
aws secretsmanager create-secret \
  --name hokusai/monitoring/grafana \
  --description "Grafana admin credentials" \
  --secret-string '{
    "username": "admin",
    "password": "GENERATED_SECURE_PASSWORD"
  }'
```

### Update ECS Task Definitions

Modify your Terraform or ECS task definitions to pull from Secrets Manager:

```json
{
  "name": "POSTGRES_PASSWORD",
  "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:hokusai/database/mlflow:password::"
}
```

## 📋 Post-Remediation Checklist

- [ ] Created local `.env` file with secure passwords
- [ ] Verified `.env` is in `.gitignore` and not tracked by Git
- [ ] Tested local docker-compose setup with new credentials
- [ ] Checked if exposed credentials were used in production
- [ ] Rotated production RDS password (if applicable)
- [ ] Updated AWS Secrets Manager (if applicable)
- [ ] Forced new ECS deployments (if applicable)
- [ ] Revoked GitGuardian alert (after confirming rotation)
- [ ] Documented incident in security log
- [ ] Set up secret scanning in CI/CD pipeline

## 🛡️ Prevention Measures

### 1. Pre-commit Hook (Recommended)

Install `detect-secrets` pre-commit hook:

```bash
pip install detect-secrets pre-commit

# Create .pre-commit-config.yaml
cat > .pre-commit-config.yaml << 'EOF'
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
EOF

# Install the hook
pre-commit install
```

### 2. GitHub Secret Scanning

Already enabled on public repos. Consider GitHub Advanced Security for private repos.

### 3. Never Commit These Files

```
.env
.env.*
*.pem
*.key
credentials.json
secrets.yaml
config.prod.*
```

### 4. Use AWS Secrets Manager for ALL Production Secrets

Never store production credentials in:
- Docker Compose files
- Environment variables in code
- Configuration files
- Git repositories

## 📞 Support

If you need help with secret rotation:

1. Check AWS Secrets Manager documentation
2. Review ECS task definition secrets integration
3. Contact DevOps team for production access

## 📚 References

- [AWS Secrets Manager Best Practices](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html)
- [GitGuardian Documentation](https://docs.gitguardian.com/)
- [OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
