# PRD: Implement mTLS for Internal MLflow Communication

## Objectives

Implement mutual TLS (mTLS) authentication for internal service-to-service communication between Hokusai services and MLflow. This will provide zero-trust security without relying on external auth service overhead for high-frequency internal calls.

Primary goals:
1. Secure internal communication between API service and MLflow service
2. Secure internal communication between data pipeline workers and MLflow tracking
3. Maintain separate authentication paths for external vs internal requests
4. Reduce Redis cache dependency for internal service calls
5. Improve performance for high-frequency internal MLflow operations

## Background

### Current State

The Hokusai data pipeline currently uses:
- External requests: API key authentication via external auth service (auth.hokus.ai)
- Internal requests: HTTP without TLS to mlflow.hokusai-development.local:5000
- Redis caching to reduce auth service calls
- Service discovery via AWS Cloud Map for internal service resolution

### Problem

1. Internal HTTP communication is unencrypted and unauthenticated
2. All requests (internal and external) go through the same auth middleware
3. High-frequency internal MLflow calls add unnecessary load to auth service and Redis
4. No way to verify that internal service-to-service calls are from trusted services

### Solution

MLflow 3.4 introduced native support for mTLS authentication. We will:
1. Implement certificate-based mutual authentication for internal services
2. Create a hybrid authentication strategy that dispatches based on request source
3. Bypass external auth service for verified internal mTLS requests
4. Maintain existing API key authentication for external requests

## Success Criteria

### Must Have
- mTLS certificates generated and stored in AWS Secrets Manager
- MLflow service configured to require client certificates for internal calls
- API service configured with client certificates for MLflow communication
- Authentication middleware enhanced to detect and validate mTLS connections
- Internal service requests bypass external auth service validation
- All existing external authentication flows continue to work unchanged
- Zero downtime deployment path

### Should Have
- Certificate rotation mechanism documented
- Monitoring for certificate expiration
- Health checks updated to verify mTLS connectivity
- Performance improvement metrics for internal calls

### Nice to Have
- Automatic certificate rotation via AWS Certificate Manager
- Certificate revocation list (CRL) support
- Metrics dashboard showing internal vs external auth paths

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│ External Clients (hokus.ai, registry.hokus.ai)          │
│ → Custom API Key Auth Middleware                        │
│   (scope validation, usage tracking, Redis cache)       │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│ Internal Services (ECS Service Discovery)                │
│ → mTLS (certificate-based mutual auth)                  │
│   (faster, no external dependency)                       │
└─────────────────────────────────────────────────────────┘
```

### Request Flow

#### External Request Flow (Unchanged)
1. Client sends request with API key to https://api.hokus.ai
2. ALB terminates TLS and forwards to ECS task
3. APIKeyAuthMiddleware extracts API key
4. Middleware validates with auth service (with Redis caching)
5. Request processed and response returned

#### Internal Request Flow (New)
1. API service initiates request to mlflow.hokusai-development.local:5000
2. Client presents mTLS certificate during TLS handshake
3. MLflow server verifies client certificate against CA
4. APIKeyAuthMiddleware detects mTLS verified connection
5. Middleware bypasses external auth service, trusts mTLS
6. Request processed and response returned

### Components

#### 1. Certificate Management
- AWS Secrets Manager stores:
  - CA certificate (mlflow-ca.crt)
  - Client certificate (hokusai-client.crt)
  - Client private key (hokusai-client.key)
  - Server certificate (mlflow-server.crt)
  - Server private key (mlflow-server.key)

#### 2. MLflow Service Configuration
- Environment variables for certificate paths
- MLflow server configured to require client certificates
- Certificate validation against CA

#### 3. API Service Configuration
- Client certificate loaded from Secrets Manager
- MLflow client configured to present certificates
- Connection pooling with mTLS support

#### 4. Authentication Middleware Enhancement
- Detect internal vs external requests
- Validate mTLS peer certificate
- Dispatch to appropriate auth path

## Technical Implementation

### 1. Certificate Generation (Development)

Location: `scripts/generate_mtls_certs.sh`

```bash
#!/bin/bash
# Generate CA, server, and client certificates for mTLS

# Generate CA
openssl req -x509 -newkey rsa:4096 -days 365 \
  -keyout ca-key.pem -out ca-cert.pem \
  -subj "/CN=Hokusai MLflow CA" -nodes

# Generate server certificate
openssl req -newkey rsa:4096 -keyout server-key.pem \
  -out server-req.pem -subj "/CN=mlflow.hokusai-development.local" -nodes
openssl x509 -req -in server-req.pem -days 365 \
  -CA ca-cert.pem -CAkey ca-key.pem -CAcreateserial \
  -out server-cert.pem

# Generate client certificate
openssl req -newkey rsa:4096 -keyout client-key.pem \
  -out client-req.pem -subj "/CN=hokusai-api-client" -nodes
openssl x509 -req -in client-req.pem -days 365 \
  -CA ca-cert.pem -CAkey ca-key.pem -CAcreateserial \
  -out client-cert.pem
```

### 2. MLflow Configuration Module

Location: `src/utils/mlflow_config.py`

Add new function:

```python
def configure_internal_mtls():
    """Configure mTLS for internal MLflow communication.

    Only enabled in staging/production environments.
    Uses AWS Secrets Manager for certificate management.
    """
    environment = os.getenv("ENVIRONMENT", "development")

    if environment in ["staging", "production"]:
        # Load certificates from AWS Secrets Manager
        import boto3
        secrets_client = boto3.client('secretsmanager', region_name='us-east-1')

        # Retrieve certificates
        client_cert = secrets_client.get_secret_value(
            SecretId=f'hokusai/{environment}/mlflow/client-cert'
        )['SecretString']

        client_key = secrets_client.get_secret_value(
            SecretId=f'hokusai/{environment}/mlflow/client-key'
        )['SecretString']

        ca_cert = secrets_client.get_secret_value(
            SecretId=f'hokusai/{environment}/mlflow/ca-cert'
        )['SecretString']

        # Write to temporary files (ECS task has writable /tmp)
        cert_dir = "/tmp/mlflow-certs"
        os.makedirs(cert_dir, exist_ok=True)

        with open(f"{cert_dir}/client.crt", "w") as f:
            f.write(client_cert)
        with open(f"{cert_dir}/client.key", "w") as f:
            f.write(client_key)
        with open(f"{cert_dir}/ca.crt", "w") as f:
            f.write(ca_cert)

        # Set environment variables for MLflow client
        os.environ["MLFLOW_TRACKING_CLIENT_CERT_PATH"] = f"{cert_dir}/client.crt"
        os.environ["MLFLOW_TRACKING_CLIENT_KEY_PATH"] = f"{cert_dir}/client.key"
        os.environ["MLFLOW_TRACKING_SERVER_CERT_PATH"] = f"{cert_dir}/ca.crt"

        logger.info("Configured mTLS for internal MLflow communication")
    else:
        logger.info("mTLS not configured for development environment")
```

### 3. Authentication Middleware Enhancement

Location: `src/middleware/auth.py`

Add methods to `APIKeyAuthMiddleware` class:

```python
def _is_internal_request(self, client_ip: str) -> bool:
    """Detect if request is from internal service.

    Args:
        client_ip: Client IP address

    Returns:
        True if request is from internal ECS service
    """
    # Internal requests come from ECS private subnet
    # 10.0.0.0/8 is private IP range
    if client_ip.startswith("10."):
        return True

    # Check if request is from service discovery hostname
    # This would be set by internal service mesh
    return False

def _verify_mtls_certificate(self, request: Request) -> bool:
    """Verify mTLS client certificate from request.

    Args:
        request: The incoming request

    Returns:
        True if valid mTLS certificate is present
    """
    # Check if peer certificate was verified by TLS layer
    # This would be set by the ASGI server (uvicorn/gunicorn)
    if hasattr(request.state, 'peer_cert_verified'):
        return request.state.peer_cert_verified

    # Check for client certificate in connection info
    # The exact mechanism depends on the ASGI server
    return False

async def dispatch(self, request: Request, call_next):
    """Process the request and validate API key."""
    # Allow CORS preflight requests
    if request.method == "OPTIONS":
        response = await call_next(request)
        return response

    # Check if path is excluded
    if any(request.url.path.startswith(path) for path in self.excluded_paths):
        response = await call_next(request)
        return response

    # Extract client IP
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.client.host if request.client else None

    # NEW: Check if this is an internal mTLS request
    if self._is_internal_request(client_ip):
        if self._verify_mtls_certificate(request):
            # Trust mTLS, bypass external auth service
            request.state.user_id = "internal_service"
            request.state.api_key_id = "mtls_cert"
            request.state.service_id = "hokusai_internal"
            request.state.scopes = ["mlflow:write", "mlflow:read"]
            request.state.rate_limit_per_hour = None  # No rate limit for internal

            logger.debug("Internal mTLS request authenticated")
            response = await call_next(request)
            return response
        else:
            logger.warning(f"Internal request from {client_ip} without valid mTLS certificate")
            # Fall through to API key auth

    # EXISTING: External API key authentication flow
    api_key = get_api_key_from_request(request)

    if not api_key:
        return JSONResponse(status_code=401, content={"detail": "API key required"})

    # ... rest of existing validation code ...
```

### 4. MLflow Server Configuration

Location: `Dockerfile.mlflow`

Add certificate loading and MLflow configuration:

```dockerfile
# Copy certificate loading script
COPY scripts/load_mlflow_certs.sh /app/scripts/

# Run at container startup
CMD ["/bin/bash", "-c", "/app/scripts/load_mlflow_certs.sh && mlflow server --host 0.0.0.0 --port 5000 ..."]
```

Location: `scripts/load_mlflow_certs.sh`

```bash
#!/bin/bash
# Load MLflow server certificates from AWS Secrets Manager

if [ "$ENVIRONMENT" = "staging" ] || [ "$ENVIRONMENT" = "production" ]; then
  echo "Loading MLflow mTLS certificates from Secrets Manager..."

  # Create cert directory
  mkdir -p /etc/mlflow/certs

  # Retrieve and save certificates
  aws secretsmanager get-secret-value \
    --secret-id "hokusai/${ENVIRONMENT}/mlflow/server-cert" \
    --query SecretString --output text > /etc/mlflow/certs/server.crt

  aws secretsmanager get-secret-value \
    --secret-id "hokusai/${ENVIRONMENT}/mlflow/server-key" \
    --query SecretString --output text > /etc/mlflow/certs/server.key

  aws secretsmanager get-secret-value \
    --secret-id "hokusai/${ENVIRONMENT}/mlflow/ca-cert" \
    --query SecretString --output text > /etc/mlflow/certs/ca.crt

  # Set environment variables
  export MLFLOW_SERVER_CERT_PATH="/etc/mlflow/certs/server.crt"
  export MLFLOW_SERVER_KEY_PATH="/etc/mlflow/certs/server.key"
  export MLFLOW_CLIENT_CERT_PATH="/etc/mlflow/certs/ca.crt"

  echo "mTLS certificates loaded successfully"
fi
```

### 5. Infrastructure Updates

Location: `../hokusai-infrastructure/environments/development/main.tf`

Add AWS Secrets Manager resources:

```hcl
# CA Certificate
resource "aws_secretsmanager_secret" "mlflow_ca_cert" {
  name        = "hokusai/development/mlflow/ca-cert"
  description = "MLflow CA certificate for mTLS"
}

resource "aws_secretsmanager_secret_version" "mlflow_ca_cert" {
  secret_id     = aws_secretsmanager_secret.mlflow_ca_cert.id
  secret_string = file("${path.module}/certs/ca-cert.pem")
}

# Client Certificate
resource "aws_secretsmanager_secret" "mlflow_client_cert" {
  name        = "hokusai/development/mlflow/client-cert"
  description = "MLflow client certificate for mTLS"
}

resource "aws_secretsmanager_secret_version" "mlflow_client_cert" {
  secret_id     = aws_secretsmanager_secret.mlflow_client_cert.id
  secret_string = file("${path.module}/certs/client-cert.pem")
}

# Client Key
resource "aws_secretsmanager_secret" "mlflow_client_key" {
  name        = "hokusai/development/mlflow/client-key"
  description = "MLflow client private key for mTLS"
}

resource "aws_secretsmanager_secret_version" "mlflow_client_key" {
  secret_id     = aws_secretsmanager_secret.mlflow_client_key.id
  secret_string = file("${path.module}/certs/client-key.pem")
}

# Server Certificate
resource "aws_secretsmanager_secret" "mlflow_server_cert" {
  name        = "hokusai/development/mlflow/server-cert"
  description = "MLflow server certificate for mTLS"
}

resource "aws_secretsmanager_secret_version" "mlflow_server_cert" {
  secret_id     = aws_secretsmanager_secret.mlflow_server_cert.id
  secret_string = file("${path.module}/certs/server-cert.pem")
}

# Server Key
resource "aws_secretsmanager_secret" "mlflow_server_key" {
  name        = "hokusai/development/mlflow/server-key"
  description = "MLflow server private key for mTLS"
}

resource "aws_secretsmanager_secret_version" "mlflow_server_key" {
  secret_id     = aws_secretsmanager_secret.mlflow_server_key.id
  secret_string = file("${path.module}/certs/server-key.pem")
}

# Grant ECS task roles access to secrets
resource "aws_iam_role_policy" "mlflow_secrets_access" {
  name = "mlflow-secrets-access"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          aws_secretsmanager_secret.mlflow_ca_cert.arn,
          aws_secretsmanager_secret.mlflow_client_cert.arn,
          aws_secretsmanager_secret.mlflow_client_key.arn,
          aws_secretsmanager_secret.mlflow_server_cert.arn,
          aws_secretsmanager_secret.mlflow_server_key.arn
        ]
      }
    ]
  })
}
```

## Testing Requirements

### Unit Tests

1. **Certificate Loading** (`tests/unit/test_mtls_config.py`)
   - Test certificate loading from Secrets Manager
   - Test certificate validation
   - Test error handling for missing certificates

2. **Middleware Detection** (`tests/unit/test_auth_middleware_mtls.py`)
   - Test internal request detection
   - Test mTLS certificate verification
   - Test fallback to API key auth

### Integration Tests

1. **mTLS Connection** (`tests/integration/test_mtls_connection.py`)
   - Test successful mTLS handshake
   - Test client certificate presentation
   - Test server certificate validation
   - Test connection failure without certificates

2. **Auth Middleware** (`tests/integration/test_auth_mtls_dispatch.py`)
   - Test internal request with valid mTLS bypasses auth service
   - Test external request uses API key auth
   - Test internal request without mTLS falls back to API key

3. **MLflow Operations** (`tests/integration/test_mlflow_mtls_operations.py`)
   - Test model registration via mTLS
   - Test experiment creation via mTLS
   - Test artifact upload via mTLS

### Manual Testing Checklist

- [ ] Generate certificates using script
- [ ] Upload certificates to Secrets Manager
- [ ] Deploy MLflow service with mTLS enabled
- [ ] Deploy API service with client certificates
- [ ] Verify internal requests succeed
- [ ] Verify external requests still work
- [ ] Check CloudWatch logs for mTLS authentication
- [ ] Verify auth service is not called for internal requests
- [ ] Test certificate rotation

## Deployment Plan

### Phase 1: Development Environment (Week 1)
1. Generate test certificates
2. Store certificates in Secrets Manager
3. Update MLflow service configuration
4. Update API service configuration
5. Deploy and test

### Phase 2: Staging Environment (Week 2)
1. Generate staging certificates
2. Deploy to staging
3. Run integration tests
4. Monitor for issues
5. Gather performance metrics

### Phase 3: Production Rollout (Week 3)
1. Generate production certificates
2. Deploy during low-traffic window
3. Monitor error rates and latency
4. Verify auth service load reduction
5. Document any issues

## Monitoring

### Metrics to Track
- mTLS connection success rate
- mTLS connection failures by reason
- Auth service call volume (should decrease)
- Internal request latency (should decrease)
- Certificate expiration warnings

### Alerts
- Certificate expiring in < 30 days
- mTLS connection failure rate > 1%
- Fallback to API key auth for internal requests

### Dashboards
- Internal vs external auth path distribution
- mTLS certificate health
- Performance comparison (before/after mTLS)

## Rollback Plan

### Immediate Rollback
If critical issues occur:
1. Remove mTLS certificate environment variables from ECS task definitions
2. Restart services
3. All requests will fall back to API key authentication
4. No data loss or service interruption

### Gradual Rollback
If performance issues detected:
1. Set feature flag `ENABLE_MTLS_AUTH=false`
2. Monitor for improvement
3. Investigate root cause
4. Re-enable with fixes

## Security Considerations

### Certificate Management
- Certificates stored in AWS Secrets Manager with encryption at rest
- IAM policies restrict access to ECS task roles only
- Certificate rotation documented and planned
- Private keys never logged or exposed

### Attack Surface
- mTLS only enabled for internal private subnet traffic
- External traffic still requires API key
- Certificate validation prevents man-in-the-middle attacks
- Expired certificates automatically rejected

### Compliance
- Meets zero-trust security requirements
- Compliant with internal security policies
- Audit trail via CloudWatch logs
- Certificate lifecycle documented

## Documentation Updates

### User-Facing Documentation
- No changes required (internal implementation only)

### Internal Documentation
- Update architecture diagrams to show mTLS
- Document certificate generation process
- Document certificate rotation procedure
- Update deployment runbooks
- Update troubleshooting guides

## Open Questions

1. **Certificate Rotation**: Should we use AWS Certificate Manager (ACM) for automatic rotation or manual rotation?
   - Recommendation: Start with manual, move to ACM in future iteration

2. **Certificate Expiration**: What's the appropriate certificate lifetime?
   - Recommendation: 1 year for development, 90 days for production

3. **Performance Metrics**: What baseline should we establish?
   - Action: Collect 1 week of metrics before implementation

4. **Backward Compatibility**: How long should we support non-mTLS internal calls?
   - Recommendation: Support both paths for 1 release cycle, then deprecate

## Success Metrics

### Performance
- Internal MLflow request latency reduced by > 20%
- Auth service request volume reduced by > 50%
- Redis cache hit rate improvement not required

### Security
- 100% of internal service communication encrypted
- Zero unauthorized internal access attempts
- Certificate validation success rate > 99.9%

### Reliability
- No increase in error rates
- Zero downtime deployment
- Rollback capability verified
