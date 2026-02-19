---
id: authentication
title: Authentication
sidebar_label: Authentication
sidebar_position: 3
---

# Authentication

Hokusai uses API keys to authenticate requests. This guide covers how to create, manage, and use API keys for secure access to the Hokusai ML Platform.

## Overview

API keys are the primary method for authenticating with the Hokusai platform. Authentication is managed by the Hokusai Authentication Service at `auth.hokus.ai`. Each API key:

- Is associated with a specific user account
- Has configurable rate limits and IP restrictions
- Can be rotated or revoked at any time
- Supports different environments (production, test, development)
- Is validated by the central authentication service

## Prerequisites

To manage API keys, you'll need:

1. **Admin Token**: For creating and managing API keys
2. **API Key**: For regular API access

Set these as environment variables:
```bash
export HOKUSAI_ADMIN_TOKEN=your_admin_token_here
export HOKUSAI_API_KEY=your_api_key_here
```

## Creating API Keys

### Using the CLI

The easiest way to create an API key is through the Hokusai CLI:

```bash
# Create a production API key
hokusai auth create-key --name "Production Key"

# Create a test environment key with custom rate limit
hokusai auth create-key --name "Test Key" --environment test --rate-limit 100

# Create a key with IP restrictions
hokusai auth create-key --name "Restricted Key" --allowed-ip 192.168.1.100 --allowed-ip 10.0.0.1

# Create a key that expires in 30 days
hokusai auth create-key --name "Temporary Key" --expires-in-days 30

# Create a key with specific scopes
hokusai auth create-key --name "ML Platform Key" --scope model:read --scope model:write --scope mlflow:access
```

### Using the Authentication Service API

You can also create API keys programmatically via the Auth Service API:

```bash
curl -X POST https://auth.hokus.ai/api/v1/keys \
  -H "Authorization: Bearer $HOKUSAI_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My API Key",
    "service_id": "platform",
    "environment": "production",
    "rate_limit_per_hour": 1000,
    "scopes": ["model:read", "model:write", "mlflow:access"]
  }'
```

## Managing API Keys

### List Your Keys

```bash
# List all API keys
hokusai auth list-keys

# List in JSON format
hokusai auth list-keys --format json
```

### Revoke a Key

```bash
# Revoke a specific key
hokusai auth revoke-key KEY_ID

# Revoke without confirmation prompt
hokusai auth revoke-key KEY_ID --yes
```

### Rotate a Key

Key rotation creates a new key with the same settings and schedules the old one for revocation:

```bash
hokusai auth rotate-key KEY_ID
```

The old key remains valid for 24 hours to allow for migration.

### Validate a Key

Check if an API key is valid:

```bash
# Validate your configured key
hokusai auth validate

# Validate a specific key
hokusai auth validate --key hk_live_specific_key_here
```

## Using API Keys

### Python SDK

The Hokusai Python SDK supports multiple authentication methods:

#### Environment Variable (Recommended)

```python
# Set the environment variable
export HOKUSAI_API_KEY=hk_live_your_api_key_here

# Use the SDK - authentication is automatic
from hokusai import ModelRegistry

registry = ModelRegistry()
models = registry.list_models_by_type("lead_scoring")
```

#### Direct Initialization

```python
from hokusai import ModelRegistry

registry = ModelRegistry(api_key="hk_live_your_api_key_here")
```

#### Global Configuration with Auth Service Validation

```python
from hokusai import setup

# Configure with optional auth service validation
setup(
    api_key="hk_live_your_api_key_here",
    validate_with_auth_service=True  # Validates key on setup
)

# All subsequent SDK calls use this configuration
from hokusai import ModelRegistry
registry = ModelRegistry()
```

### REST API

Include your API key in the Authorization header:

```bash
curl https://api.hokus.ai/v1/models \
  -H "Authorization: Bearer hk_live_your_api_key_here"
```

Or use the X-API-Key header:

```bash
curl https://api.hokus.ai/v1/models \
  -H "X-API-Key: hk_live_your_api_key_here"
```

Or as a query parameter (not recommended for security):

```bash
curl "https://api.hokus.ai/v1/models?api_key=hk_live_your_api_key_here"
```

## Authentication Flow

When you make a request to the Hokusai ML Platform:

1. The API key is extracted from your request
2. The platform validates the key with the authentication service
3. If valid, the request proceeds with user context
4. If invalid, a 401 Unauthorized response is returned

The validation results are cached for 5 minutes to improve performance.

## Security Best Practices

### 1. Environment-Specific Keys

Use different API keys for different environments:

- `hk_live_*` - Production keys for live systems
- `hk_test_*` - Test keys for development and testing
- `hk_dev_*` - Development keys for local development

### 2. Least Privilege

Create keys with the minimum required permissions:

- Set appropriate rate limits
- Restrict to specific IP addresses when possible
- Use expiring keys for temporary access
- Assign only necessary scopes

### 3. Key Storage

Never commit API keys to version control:

```bash
# Add to .gitignore
.env
*.key
config/secrets.yaml
.hokusai/config
```

Store keys securely:

- Use environment variables
- Use secret management services (AWS Secrets Manager, HashiCorp Vault)
- Encrypt configuration files

### 4. Regular Rotation

Rotate API keys regularly:

```bash
# Rotate all production keys quarterly
hokusai auth rotate-key $PRODUCTION_KEY_ID
```

### 5. Monitor Usage

The authentication service tracks usage for all API keys. Monitor for anomalies through the CLI or API.

## Rate Limiting

Each API key has configurable rate limits:

- Default: 1000 requests per hour
- Configurable from 10 to 100,000 requests per hour
- Rate limits are enforced by the authentication service
- Limits reset on the hour

When rate limited, you'll receive a 429 response:

```json
{
  "detail": "Rate limit exceeded"
}
```

## IP Restrictions

You can restrict API keys to specific IP addresses:

```bash
# Create key with IP restrictions
hokusai auth create-key --name "Office Key" \
  --allowed-ip 203.0.113.0 \
  --allowed-ip 198.51.100.42
```

Requests from unauthorized IPs will receive a 401 response.

## Configuration

### Authentication Service URL

By default, the SDK and CLI use `https://auth.hokus.ai`. You can override this:

```bash
# Set custom auth service URL
export HOKUSAI_AUTH_SERVICE_URL=https://auth.staging.hokus.ai

# Or in Python
from hokusai import setup
setup(
    api_key="your_key",
    auth_service_url="https://auth.staging.hokus.ai"
)
```

### Configuration File

The CLI supports a configuration file at `~/.hokusai/config`:

```ini
[default]
api_key = hk_live_your_api_key_here
admin_token = your_admin_token_here
auth_service_url = https://auth.hokus.ai
```

## Troubleshooting

### Authentication Failed

If you receive a 401 Unauthorized error:

1. Check that your API key is correct
2. Ensure the key hasn't expired
3. Verify the key is active (not revoked)
4. Check that you're using the correct header format
5. Validate the key using `hokusai auth validate`

### Rate Limit Exceeded

If you're hitting rate limits:

1. Check your current usage with `hokusai auth list-keys`
2. Consider requesting a higher rate limit
3. Implement exponential backoff
4. Use caching to reduce API calls

### Authentication Service Unavailable

If the authentication service is unavailable:

1. Check the service status at status.hokus.ai
2. Cached validations will continue to work for 5 minutes
3. Contact support if the issue persists

### IP Address Not Allowed

If you receive a 401 error with IP restriction message:

1. Check your current IP address
2. Verify the key's IP restrictions
3. Update allowed IPs or use a different key

## Migration from Local Authentication

If you were using an earlier version with local authentication:

1. Request an admin token from Hokusai support
2. Create new API keys using the auth service
3. Update your applications to use the new keys
4. The old database-based keys will no longer work

## Next Steps

- Learn about [Model Registry](./core-features/model-registry) authentication
- Explore [SDK Configuration](./getting-started/configuration) options
- Read about [Security Best Practices](./guides/security)