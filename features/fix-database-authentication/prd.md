# Product Requirements Document: Fix Database Authentication

## Objectives

Resolve the database authentication failure in the Hokusai API service by ensuring the application correctly uses the "mlflow" database user with credentials retrieved from AWS Secrets Manager instead of hardcoded passwords.

## Personas

**DevOps Engineer**: Needs to ensure proper secret management and deployment configuration for database credentials.

**API Developer**: Requires reliable database connectivity for the API service to function properly.

**MLflow Administrator**: Depends on correct database authentication for MLflow backend store operations.

## Success Criteria

1. API service successfully authenticates to PostgreSQL database using "mlflow" user
2. Database password is retrieved from AWS Secrets Manager, not hardcoded
3. Health check endpoints report database as "healthy"
4. No authentication failures in CloudWatch logs
5. Service passes all health checks and runs stably in ECS

## Tasks

### Configuration Updates

Update the application configuration to properly handle database credentials from environment variables and remove hardcoded fallbacks. The Settings class in src/api/utils/config.py needs modification to ensure passwords are never hardcoded and proper error handling exists when credentials are missing.

### Environment Variable Integration

Ensure the ECS task definition properly injects the DATABASE_PASSWORD environment variable from AWS Secrets Manager. Verify that both DB_PASSWORD and DATABASE_PASSWORD environment variables are supported for backward compatibility.

### Health Check Validation

Verify the health check implementation in src/api/routes/health.py uses the correct database configuration properties (effective_database_user, effective_database_password) and doesn't bypass the configuration system.

### AWS Secrets Manager Integration

Implement proper AWS Secrets Manager integration if environment variable injection is insufficient. Add boto3 client code to retrieve secrets directly when running in AWS environment.

### Connection String Verification

Ensure the postgres_uri property in the configuration correctly builds the connection string using the effective database credentials rather than default values.

### Testing and Validation

Create test scripts to verify database connectivity with the correct credentials. Test both local development with .env files and production deployment with AWS Secrets Manager.

### Deployment Configuration

Update deployment scripts and terraform configurations to ensure proper secret injection into the ECS task definition. Verify the APP_SECRETS_ARN is correctly referenced.

### Error Handling and Logging

Implement proper error handling for missing credentials with clear error messages. Add logging to track credential source (environment variable vs default) without exposing sensitive information.

### Documentation

Update deployment documentation to explain the credential flow from AWS Secrets Manager to the application. Document the environment variables required for database connectivity.