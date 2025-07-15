# API Key Management Implementation Tasks

## 1. Database Schema and Setup
1. [ ] Create database migration for API keys table
   a. [ ] Define api_keys table schema with fields:
      - id (UUID primary key)
      - key_hash (varchar, indexed)
      - key_prefix (varchar for display)
      - user_id (foreign key)
      - name (varchar)
      - created_at (timestamp)
      - expires_at (timestamp, nullable)
      - last_used_at (timestamp, nullable)
      - is_active (boolean)
      - rate_limit_per_hour (integer)
      - allowed_ips (JSON array, nullable)
   b. [ ] Create api_key_usage table for analytics:
      - id (UUID primary key)
      - api_key_id (foreign key)
      - endpoint (varchar)
      - timestamp (timestamp)
      - response_time_ms (integer)
      - status_code (integer)
   c. [ ] Create indexes for performance
   d. [ ] Test migration up and down

## 2. Core Authentication Module
2. [ ] Implement API key generation service
   a. [ ] Create `src/auth/api_key_service.py`
   b. [ ] Implement secure key generation using `secrets` module
   c. [ ] Implement bcrypt hashing for key storage
   d. [ ] Create key prefix system (e.g., "hk_live_", "hk_test_")
   e. [ ] Add key metadata handling

## 3. Validation Middleware
3. [ ] Create API key validation middleware
   a. [ ] Create `src/middleware/auth.py`
   b. [ ] Extract API key from Authorization header or query param
   c. [ ] Implement key validation against database
   d. [ ] Add Redis caching for validated keys (5-minute TTL)
   e. [ ] Update last_used timestamp asynchronously
   f. [ ] Check expiration and active status

## 4. Rate Limiting Integration
4. [ ] Implement rate limiting per API key
   a. [ ] Create `src/middleware/rate_limiter.py`
   b. [ ] Integrate Redis for distributed rate tracking
   c. [ ] Implement sliding window rate limiting
   d. [ ] Return 429 responses with appropriate headers
   e. [ ] Add burst limit configuration

## 5. CLI Commands
5. [ ] Add auth commands to hokusai-ml-platform CLI
   a. [ ] Create `src/cli/auth.py` module
   b. [ ] Implement `hokusai auth create-key` command
   c. [ ] Implement `hokusai auth list-keys` command
   d. [ ] Implement `hokusai auth revoke-key` command
   e. [ ] Implement `hokusai auth rotate-key` command
   f. [ ] Add proper error handling and user feedback

## 6. REST API Endpoints
6. [ ] Implement API key management endpoints
   a. [ ] Create `src/api/auth.py` router
   b. [ ] POST /api/v1/auth/keys - Create new key
   c. [ ] GET /api/v1/auth/keys - List user's keys
   d. [ ] DELETE /api/v1/auth/keys/{key_id} - Revoke key
   e. [ ] POST /api/v1/auth/keys/{key_id}/rotate - Rotate key
   f. [ ] Add request/response validation with Pydantic

## 7. Usage Analytics (Dependent on Database Schema)
7. [ ] Implement usage tracking
   a. [ ] Create background task for async usage logging
   b. [ ] Track requests per key per time period
   c. [ ] Log endpoint usage patterns
   d. [ ] Calculate response time metrics
   e. [ ] Create usage summary endpoint

## 8. Security Hardening
8. [ ] Implement security measures
   a. [ ] Enforce HTTPS-only for API key endpoints
   b. [ ] Add IP allowlisting functionality
   c. [ ] Implement automated key expiration
   d. [ ] Create secure key transmission guidelines
   e. [ ] Add audit logging for all key operations

## 9. Testing (Dependent on all implementation tasks)
9. [ ] Write and implement tests
   a. [ ] Unit tests for key generation service
   b. [ ] Unit tests for validation middleware
   c. [ ] Integration tests for API endpoints
   d. [ ] Performance tests for key validation (<50ms)
   e. [ ] Security tests for key storage
   f. [ ] End-to-end tests for CLI commands

## 10. Documentation (Dependent on implementation)
10. [ ] Create comprehensive documentation
    a. [ ] Write API key authentication guide in `/documentation/getting-started/authentication.md`
    b. [ ] Document security best practices in `/documentation/security/api-keys.md`
    c. [ ] Create code examples (Python, JavaScript, curl) in `/documentation/examples/`
    d. [ ] Write troubleshooting guide in `/documentation/troubleshooting/api-keys.md`
    e. [ ] Create migration guide for existing users
    f. [ ] Update main README.md with authentication section

---

# Implementation Tasks: MLflow Server Connection Error Fix

## 1. Fix Authentication Middleware
- [x] a. Locate the authentication middleware file (src/middleware/auth.py)
- [x] b. Add /mlflow/* to the list of excluded paths
- [x] c. Test that MLflow endpoints bypass authentication
- [x] d. Verify other endpoints still require authentication

## 2. Implement MLflow Proxy Router (Dependent on Task 1)
- [x] a. Create new file src/api/routes/mlflow_proxy.py
- [x] b. Implement reverse proxy logic to forward requests to MLflow server
- [x] c. Add header stripping for authentication tokens
- [x] d. Handle all HTTP methods (GET, POST, PUT, DELETE)
- [x] e. Preserve request body and query parameters

## 3. Update Main Application (Dependent on Task 2)
- [x] a. Import MLflow proxy router in src/api/main.py
- [x] b. Include the router with prefix="/mlflow"
- [x] c. Test that routes are correctly registered

## 4. Update SDK Configuration
- [x] a. Locate ExperimentManager class in hokusai-ml-platform package
- [x] b. Update default MLflow tracking URI to use registry.hokus.ai/mlflow
- [x] c. Add MLFLOW_TRACKING_URI environment variable support
- [x] d. Implement configuration validation
- [x] e. Add logging for configuration details

## 5. Add Local/Mock Mode (Dependent on Task 4)
- [x] a. Create MockExperimentManager class for local testing
- [x] b. Implement mock methods for all ExperimentManager operations
- [x] c. Add HOKUSAI_MOCK_MODE environment variable
- [x] d. Update ExperimentManager factory to return mock when enabled
- [x] e. Document mock mode limitations

## 6. Error Handling Improvements
- [x] a. Add try-catch blocks around MLflow API calls
- [x] b. Create custom exceptions for MLflow connection errors
- [x] c. Implement exponential backoff retry logic
- [x] d. Add detailed error messages with troubleshooting steps
- [x] e. Log all MLflow connection attempts and failures

## 7. Update Documentation
- [x] a. Update documentation/getting-started/mlflow-access.md with configuration guide
- [x] b. Add MLflow setup instructions to documentation/cli/model-registration.md
- [ ] c. Create troubleshooting section in documentation/troubleshooting/mlflow-errors.md
- [ ] d. Update API reference with MLflow proxy endpoints
- [ ] e. Add environment variable reference to documentation/reference/configuration.md

## 8. Write and Implement Tests
- [x] a. Write unit tests for authentication middleware exclusion
- [x] b. Create integration tests for MLflow proxy router
- [x] c. Test mock mode functionality
- [ ] d. Add end-to-end test for model registration flow
- [x] e. Create test script scripts/test_mlflow_connection.py
- [x] f. Add tests for error handling and retry logic

## 9. Testing and Verification (Dependent on all above tasks)
- [ ] a. Run all unit tests
- [ ] b. Run integration tests
- [ ] c. Test with actual MLflow server
- [ ] d. Test in mock mode without MLflow
- [ ] e. Verify documentation accuracy
- [ ] f. Test third-party SDK integration

## 10. Documentation Review
- [ ] a. Review all documentation changes for accuracy
- [ ] b. Ensure code examples work correctly
- [ ] c. Verify environment variable names are consistent
- [ ] d. Check that troubleshooting steps are clear

## 11. Deployment Preparation
- [ ] a. Update deployment configuration with new environment variables
- [ ] b. Document any infrastructure changes needed
- [ ] c. Create migration guide for existing users
- [ ] d. Prepare release notes