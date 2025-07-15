# API Key Management System PRD

## Objectives

Implement a secure and scalable API key management system for the Hokusai data pipeline that enables users to authenticate and access platform services. The system must support key generation, validation, rotation, and revocation while maintaining security best practices.

## Personas

**Data Scientists**
- Need API keys to integrate Hokusai ML platform into their workflows
- Require simple key generation and management through CLI or web interface
- Want to manage multiple keys for different environments (dev, staging, prod)

**Platform Administrators**
- Need to monitor API key usage and enforce rate limits
- Require ability to revoke compromised keys immediately
- Want audit logs of all key operations

**Third-party Developers**
- Need programmatic access to Hokusai services via API keys
- Require clear documentation on key usage and permissions
- Want to rotate keys periodically for security

## Success Criteria

1. Users can generate, list, and revoke API keys through CLI and REST API
2. API keys are securely stored using encryption at rest
3. Key validation adds minimal latency (<50ms) to API requests
4. System supports key rotation without service interruption
5. Comprehensive audit logging of all key operations
6. Rate limiting and usage tracking per API key
7. Integration with existing authentication system

## Implementation Tasks

### Database Schema Design
Design and implement database tables for storing API keys, including:
- Key identifier, hashed key value, user association
- Creation/expiration timestamps, last used timestamp
- Permissions/scopes, rate limit configuration
- Status flags (active, revoked, expired)

### API Key Generation Service
Create service for generating cryptographically secure API keys:
- Generate 32-byte random keys using secure random generator
- Hash keys using bcrypt before storage
- Return unhashed key only once during creation
- Support optional expiration dates

### Key Validation Middleware
Implement middleware for validating API keys on incoming requests:
- Extract API key from Authorization header or query parameter
- Validate key against hashed values in database
- Cache validation results for performance
- Update last_used timestamp asynchronously
- Check expiration and revocation status

### CLI Commands Implementation
Add commands to hokusai-ml-platform CLI:
- `hokusai auth create-key` - Generate new API key
- `hokusai auth list-keys` - List user's API keys
- `hokusai auth revoke-key` - Revoke specific key
- `hokusai auth rotate-key` - Rotate existing key

### REST API Endpoints
Implement RESTful endpoints for key management:
- POST /api/v1/auth/keys - Create new API key
- GET /api/v1/auth/keys - List user's keys
- DELETE /api/v1/auth/keys/{key_id} - Revoke key
- POST /api/v1/auth/keys/{key_id}/rotate - Rotate key

### Rate Limiting Integration
Implement rate limiting per API key:
- Configure limits in database per key
- Use Redis for distributed rate limit tracking
- Return appropriate 429 responses when exceeded
- Allow configuration of burst limits

### Usage Analytics
Track and store API key usage metrics:
- Request count per key per time period
- Endpoint usage breakdown
- Response time metrics
- Error rates by key

### Security Hardening
Implement security best practices:
- Enforce HTTPS for all API key operations
- Implement key prefix for easy identification (e.g., "hk_live_")
- Add option for IP allowlisting per key
- Implement automated key expiration policies
- Secure key transmission guidelines

### Documentation
Create comprehensive documentation:
- API key authentication guide
- Security best practices
- Code examples in Python, JavaScript, and curl
- Troubleshooting common issues
- Migration guide for existing users

### Testing
Implement comprehensive test coverage:
- Unit tests for key generation and validation
- Integration tests for API endpoints
- Performance tests for validation middleware
- Security tests for key storage and transmission

---

# Product Requirements Document: MLflow Server Connection Error Fix

## Objectives

The primary objective is to resolve the MLflow server connection error (HTTP 403 Forbidden) that prevents the Hokusai ML platform's ExperimentManager from connecting to the MLflow tracking server. This fix will enable third-party developers to successfully use the Hokusai SDK for model registration and experiment tracking.

## Personas

1. **Third-Party Developers**: External developers integrating Hokusai SDK into their ML projects who need reliable MLflow connectivity for experiment tracking and model registration.

2. **Data Scientists**: Users who need to track experiments, register models, and monitor performance metrics through the Hokusai platform.

3. **DevOps Engineers**: Team members responsible for deploying and maintaining the Hokusai infrastructure, including MLflow server configuration.

## Success Criteria

1. ExperimentManager successfully connects to MLflow server without authentication errors
2. All MLflow API endpoints are accessible through the platform
3. Local development mode works without requiring MLflow server connection
4. Clear documentation exists for MLflow configuration
5. Automated tests verify MLflow connectivity and error handling

## Implementation Tasks

### 1. Fix Authentication Middleware
- Modify the authentication middleware to exclude MLflow endpoints from API key authentication
- Ensure MLflow paths (/mlflow/*) bypass the standard authentication flow
- Maintain security for other API endpoints

### 2. Implement MLflow Proxy Router
- Create a reverse proxy to forward MLflow requests from registry.hokus.ai to the internal MLflow server
- Strip authentication headers before forwarding to MLflow
- Preserve all MLflow functionality (UI, API, SDK integration)

### 3. Update SDK Configuration
- Modify ExperimentManager to use the correct MLflow tracking URI
- Add environment variable support for MLflow configuration
- Implement fallback mechanism for local development

### 4. Add Local/Mock Mode
- Create a local mode that doesn't require MLflow server connection
- Implement mock tracking functionality for testing
- Allow developers to disable MLflow integration via configuration

### 5. Update Documentation
- Document MLflow configuration requirements
- Create setup guide for third-party developers
- Add troubleshooting section for common connection issues
- Update API reference with MLflow endpoints

### 6. Implement Comprehensive Tests
- Write unit tests for authentication middleware changes
- Create integration tests for MLflow connectivity
- Add test script for verifying MLflow server access
- Test both authenticated and unauthenticated paths

### 7. Error Handling Improvements
- Implement graceful error handling for MLflow connection failures
- Provide clear error messages with troubleshooting steps
- Add retry logic for transient connection issues