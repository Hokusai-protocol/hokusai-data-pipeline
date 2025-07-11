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