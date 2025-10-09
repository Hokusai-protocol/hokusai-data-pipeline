# Security Remediation Guide - GitGuardian Alert

**Alert Date**: 2025-10-09
**Commit**: [c0e5fab](https://github.com/Hokusai-protocol/hokusai-data-pipeline/commit/c0e5fab09a33c4749028fcd4e4dad14ec9b53fa1)
**Status**: ⚠️ IMMEDIATE ACTION REQUIRED

## Summary

Hardcoded credentials were exposed in `docker-compose.yml` when the repository was made public. While these appear to be local development credentials only, they must be rotated immediately.

## Exposed Credentials

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

## ✅ Completed Fixes

1. ✅ Removed all hardcoded secrets from `docker-compose.yml`
2. ✅ Updated `docker-compose.yml` to use environment variables
3. ✅ Updated `.env.example` with secure placeholder values
4. ✅ Enhanced `.gitignore` to prevent future `.env` file commits

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

### Step 5: Revoke GitHub Commit (Advanced)

**WARNING**: This is destructive and should only be done if absolutely necessary.

If you MUST remove the secrets from Git history:

```bash
# Use BFG Repo-Cleaner (safer than git filter-branch)
# Install: brew install bfg

# Clone a fresh copy
git clone --mirror https://github.com/Hokusai-protocol/hokusai-data-pipeline.git

# Remove the passwords from all history
bfg --replace-text passwords.txt hokusai-data-pipeline.git

# Force push (requires force-push permissions)
cd hokusai-data-pipeline.git
git reflog expire --expire=now --all && git gc --prune=now --aggressive
git push --force
```

**Alternative**: Accept that the commit is public and focus on rotating all credentials.

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
