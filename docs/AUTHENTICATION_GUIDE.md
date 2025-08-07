# Hokusai API Authentication Guide

This guide provides comprehensive information about authentication requirements and methods for the Hokusai MLOps platform.

## Overview

The Hokusai API uses API key authentication for secure access to all endpoints. API keys are managed by an external authentication service and provide granular access control with rate limiting and IP restrictions.

## Authentication Methods

### 1. Authorization Header (Recommended)

The preferred method for API authentication:

```bash
# Bearer token format
curl -H "Authorization: Bearer hk_live_your_api_key_here" \
  https://registry.hokus.ai/api/models/

# ApiKey format (alternative)  
curl -H "Authorization: ApiKey hk_live_your_api_key_here" \
  https://registry.hokus.ai/api/models/
```

### 2. X-API-Key Header

Alternative header-based authentication:

```bash
curl -H "X-API-Key: hk_live_your_api_key_here" \
  https://registry.hokus.ai/api/models/
```

### 3. Query Parameter (Not Recommended)

For testing only - not recommended for production use:

```bash
curl "https://registry.hokus.ai/api/models/?api_key=hk_live_your_api_key_here"
```

## API Key Formats

Hokusai API keys follow a structured format:

- **Live Keys**: `hk_live_` + 32 character identifier
- **Test Keys**: `hk_test_` + 32 character identifier  
- **Development Keys**: `hk_dev_` + 32 character identifier

Example: `hk_live_abc123def456ghi789jkl012mno345pq`

## Authentication Requirements by Endpoint Category

### 🟢 No Authentication Required

These endpoints are publicly accessible for monitoring and documentation:

- **Health Checks**
  - `GET /health`
  - `GET /ready` 
  - `GET /live`
  - `GET /version`
  - `GET /metrics`

- **Documentation**
  - `GET /docs`
  - `GET /redoc`
  - `GET /openapi.json`
  - `GET /favicon.ico`

- **DSPy Health Check**
  - `GET /api/v1/dspy/health`

### 🔐 Authentication Required

All other endpoints require valid API key authentication:

#### Model Management (`/models/*`)

- **Purpose**: Access model registry and management operations
- **Scopes**: Requires `models:read`, `models:write` scopes
- **Rate Limits**: 
  - General operations: 1000/hour
  - Model registration: 20/minute
  - Model lineage: 100/minute

**Examples:**
```bash
# List models
curl -H "Authorization: Bearer hk_live_your_key" \
  https://registry.hokus.ai/api/models/

# Register model
curl -X POST -H "Authorization: Bearer hk_live_your_key" \
  -H "Content-Type: application/json" \
  -d '{"model_type": "classification"}' \
  https://registry.hokus.ai/api/models/register
```

#### MLflow Proxy (`/mlflow/*`)

- **Purpose**: Access MLflow tracking server through Hokusai proxy
- **Scopes**: Requires `mlflow:read`, `mlflow:write` scopes
- **Rate Limits**: 1000/hour per API key
- **Special Features**: 
  - Automatic path translation for internal/external MLflow
  - Circuit breaker protection
  - User context injection

**Examples:**
```bash
# List experiments
curl -H "Authorization: Bearer hk_live_your_key" \
  https://registry.hokus.ai/mlflow/api/2.0/mlflow/experiments/search

# Upload artifact
curl -X PUT -H "Authorization: Bearer hk_live_your_key" \
  --data-binary @model.pkl \
  https://registry.hokus.ai/mlflow/api/2.0/mlflow-artifacts/artifacts/model.pkl
```

#### DSPy Pipeline (`/api/v1/dspy/*`)

- **Purpose**: Execute DSPy programs and manage pipeline operations
- **Scopes**: Requires `dspy:execute` scope
- **Rate Limits**: 1000/hour per API key

**Examples:**
```bash
# Execute DSPy program
curl -X POST -H "Authorization: Bearer hk_live_your_key" \
  -H "Content-Type: application/json" \
  -d '{"program_id": "email-assistant", "inputs": {"context": "meeting follow-up"}}' \
  https://registry.hokus.ai/api/v1/dspy/execute
```

#### Contributor Analytics (`/models/contributors/*`)

- **Purpose**: Access contributor impact data and analytics
- **Scopes**: Requires `analytics:read` scope
- **Rate Limits**: 100/minute per API key

**Examples:**
```bash
# Get contributor impact
curl -H "Authorization: Bearer hk_live_your_key" \
  https://registry.hokus.ai/api/models/contributors/0x1234567890123456789012345678901234567890/impact
```

## Authentication Flow

### 1. API Key Validation

When a request is made with an API key:

1. **Extraction**: API key is extracted from headers or query parameters
2. **Cache Check**: System checks Redis cache for recent validation
3. **External Validation**: If not cached, validates with auth service
4. **Response Caching**: Valid results are cached for 5 minutes
5. **Request Processing**: Validated requests proceed with user context

### 2. Request Context

After successful authentication, the following information is available to endpoints:

- `request.state.user_id`: Authenticated user identifier
- `request.state.api_key_id`: API key identifier for logging
- `request.state.service_id`: Service identifier
- `request.state.scopes`: List of granted permissions
- `request.state.rate_limit_per_hour`: Rate limit for this key

### 3. Usage Logging

All authenticated requests are logged asynchronously to the auth service for:
- Usage analytics
- Rate limiting calculations
- Billing and quota tracking
- Security monitoring

## Error Responses

### Missing Authentication

**HTTP 401 Unauthorized:**
```json
{
  "detail": "API key required"
}
```

### Invalid API Key

**HTTP 401 Unauthorized:**
```json
{
  "detail": "Invalid or expired API key"
}
```

### Rate Limit Exceeded

**HTTP 429 Too Many Requests:**
```json
{
  "detail": "Rate limit exceeded"
}
```

### Insufficient Permissions

**HTTP 403 Forbidden:**
```json
{
  "detail": "Insufficient permissions for this operation"
}
```

### Authentication Service Unavailable

**HTTP 503 Service Unavailable:**
```json
{
  "detail": "Authentication service timeout"
}
```

## SDK Integration

### Python SDK

The Python SDK handles authentication automatically:

```python
from hokusai import setup, ModelRegistry

# Configure authentication
setup(api_key="hk_live_your_api_key_here")

# SDK automatically includes authentication in all requests
registry = ModelRegistry()
models = registry.list_models()
```

### Environment Variables

Set your API key as an environment variable:

```bash
export HOKUSAI_API_KEY="hk_live_your_api_key_here"
```

### MLflow Integration

When using MLflow directly with Hokusai:

```python
import mlflow
import os

# Configure MLflow to use Hokusai proxy
os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/mlflow"
os.environ["MLFLOW_TRACKING_TOKEN"] = "hk_live_your_api_key_here"

# Use standard MLflow operations
with mlflow.start_run():
    mlflow.log_metric("accuracy", 0.95)
```

## Security Best Practices

### 1. API Key Storage

- ✅ **Do**: Store API keys in environment variables or secure vaults
- ✅ **Do**: Use different keys for different environments (dev, staging, prod)
- ❌ **Don't**: Hardcode API keys in source code
- ❌ **Don't**: Share API keys in chat or email
- ❌ **Don't**: Use production keys in development

### 2. Key Rotation

- Rotate API keys regularly (recommended: every 90 days)
- Use key rotation during security incidents
- Monitor key usage for unusual activity

### 3. IP Restrictions

Configure IP allowlists for production API keys:

```bash
# Only allow specific IP addresses
allowed_ips: ["203.0.113.0/24", "198.51.100.42"]
```

### 4. Scope Limitations

Use principle of least privilege:

```bash
# Only grant necessary scopes
scopes: ["models:read", "mlflow:read"]  # Read-only access
scopes: ["models:write", "mlflow:write"]  # Full access
```

## Rate Limiting

### Default Limits

- **Standard Operations**: 1000 requests/hour per API key
- **Model Registration**: 20 requests/minute per API key
- **Analytics Queries**: 100 requests/minute per API key

### Custom Limits

Rate limits can be customized per API key during creation:

```bash
curl -X POST -H "Authorization: Bearer admin_key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production API Key",
    "rate_limit_per_hour": 5000,
    "environment": "production"
  }' \
  https://auth.hokus.ai/api/v1/keys
```

### Rate Limit Headers

Responses include rate limit information:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1641824400
```

## Troubleshooting

### Common Issues

#### 1. "API key required" Error

**Cause**: No authentication provided
**Solution**: Add Authorization header or X-API-Key header

```bash
# Wrong
curl https://registry.hokus.ai/api/models/

# Right  
curl -H "Authorization: Bearer hk_live_your_key" \
  https://registry.hokus.ai/api/models/
```

#### 2. "Invalid or expired API key" Error

**Causes**: 
- API key is malformed
- API key has expired
- API key has been revoked

**Solution**: Verify key format and expiration, or generate a new key

#### 3. "Authentication service timeout" Error

**Cause**: External auth service is unavailable
**Solution**: Retry request after a short delay (auth service has retry logic)

#### 4. Rate Limit Exceeded

**Cause**: Too many requests in the time window
**Solution**: Implement backoff strategy or request rate limit increase

### Debug Authentication

Enable debug logging to troubleshoot authentication issues:

```bash
# Set debug environment variable
export HOKUSAI_DEBUG=true

# Check authentication service status
curl https://auth.hokus.ai/health

# Validate API key manually
curl -X POST -H "Authorization: Bearer your_key" \
  -H "Content-Type: application/json" \
  -d '{"service_id": "hokusai-registry"}' \
  https://auth.hokus.ai/api/v1/keys/validate
```

### Support

If you encounter authentication issues:

1. Check the [troubleshooting section](#troubleshooting) above
2. Verify your API key in the auth service dashboard
3. Contact support with request ID for investigation

## Advanced Features

### 1. Service-to-Service Authentication

For internal service communication, use service tokens:

```python
# Service authentication (internal use)
headers = {
    "Authorization": f"Bearer {service_token}",
    "X-Service-ID": "hokusai-pipeline"
}
```

### 2. Scoped Access

API keys support fine-grained permissions:

- `models:read` - Read model information
- `models:write` - Create and modify models
- `models:delete` - Delete models
- `mlflow:read` - Read MLflow data
- `mlflow:write` - Write MLflow data
- `dspy:execute` - Execute DSPy programs
- `analytics:read` - Read analytics data

### 3. IP-based Restrictions

Configure IP allowlists for enhanced security:

```json
{
  "allowed_ips": [
    "203.0.113.0/24",
    "198.51.100.42"
  ]
}
```

### 4. Audit Logging

All authenticated requests are logged with:
- User ID and API key ID
- Endpoint accessed
- Response status and time
- Client IP address
- Request timestamp

## Migration Guide

### From Previous Authentication

If migrating from a previous authentication system:

1. **Obtain New API Keys**: Contact support to generate new Hokusai API keys
2. **Update Environment Variables**: Replace old keys with new format
3. **Test Authentication**: Verify new keys work with health check endpoints
4. **Update Applications**: Deploy updated authentication configuration
5. **Monitor Usage**: Check that requests are being authenticated properly

### Example Migration

```bash
# Old format (if applicable)
export OLD_API_KEY="legacy_key_format"

# New format
export HOKUSAI_API_KEY="hk_live_new_key_format"

# Test new authentication
curl -H "Authorization: Bearer $HOKUSAI_API_KEY" \
  https://registry.hokus.ai/health
```