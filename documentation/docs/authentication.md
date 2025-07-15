---
id: authentication
title: Authentication
sidebar_label: Authentication
sidebar_position: 3
---

# Authentication

Hokusai uses API keys to authenticate requests. This guide covers how to create, manage, and use API keys for secure access to the Hokusai ML Platform.

## Overview

API keys are the primary method for authenticating with the Hokusai platform. Each API key:

- Is associated with a specific user account
- Has configurable rate limits and IP restrictions
- Can be rotated or revoked at any time
- Supports different environments (production, test, development)

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
```

### Using the API

You can also create API keys programmatically via the REST API:

```bash
curl -X POST https://api.hokus.ai/v1/api-keys \
  -H "Authorization: Bearer $EXISTING_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My API Key",
    "environment": "production",
    "rate_limit_per_hour": 1000
  }'
```

## Managing API Keys

### List Your Keys

```bash
# List all API keys
hokusai auth list-keys

# List only active keys
hokusai auth list-keys --active-only
```

### Revoke a Key

```bash
# Revoke a specific key
hokusai auth revoke-key KEY_ID

# Force revoke without confirmation
hokusai auth revoke-key KEY_ID --force
```

### Rotate a Key

Key rotation creates a new key with the same settings and revokes the old one:

```bash
hokusai auth rotate-key KEY_ID
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

#### Global Configuration

```python
from hokusai import setup

# Configure once at the start
setup(api_key="hk_live_your_api_key_here")

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

Or as a query parameter:

```bash
curl "https://api.hokus.ai/v1/models?api_key=hk_live_your_api_key_here"
```

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

### 3. Key Storage

Never commit API keys to version control:

```bash
# Add to .gitignore
.env
*.key
config/secrets.yaml
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

Monitor API key usage for anomalies:

```python
# Check usage via SDK
from hokusai.auth import get_api_key_usage

usage = get_api_key_usage(key_id="key123")
print(f"Requests today: {usage.requests_today}")
print(f"Rate limit: {usage.rate_limit_per_hour}")
```

## Rate Limiting

Each API key has configurable rate limits:

- Default: 1000 requests per hour
- Configurable from 10 to 10,000 requests per hour
- Rate limits reset on the hour

When rate limited, you'll receive a 429 response:

```json
{
  "error": "Rate limit exceeded",
  "retry_after": 3600
}
```

## IP Restrictions

You can restrict API keys to specific IP addresses:

```bash
# Create key with IP restrictions
hokusai auth create-key --name "Office Key" \
  --allowed-ip 203.0.113.0/24 \
  --allowed-ip 198.51.100.42
```

Requests from unauthorized IPs will receive a 403 response.

## Troubleshooting

### Authentication Failed

If you receive a 401 Unauthorized error:

1. Check that your API key is correct
2. Ensure the key hasn't expired
3. Verify the key is active (not revoked)
4. Check that you're using the correct header format

### Rate Limit Exceeded

If you're hitting rate limits:

1. Check your current usage with `list-keys`
2. Consider upgrading your rate limit
3. Implement exponential backoff
4. Use caching to reduce API calls

### IP Address Not Allowed

If you receive a 403 Forbidden error:

1. Check your current IP address
2. Verify the key's IP restrictions
3. Update allowed IPs if needed

## API Reference

### Create API Key

```http
POST /v1/api-keys
```

**Request Body:**
```json
{
  "name": "string",
  "environment": "production|test|development",
  "rate_limit_per_hour": 1000,
  "expires_in_days": 30,
  "allowed_ips": ["192.168.1.1"]
}
```

### List API Keys

```http
GET /v1/api-keys
```

### Revoke API Key

```http
DELETE /v1/api-keys/{key_id}
```

### Rotate API Key

```http
POST /v1/api-keys/{key_id}/rotate
```

## Next Steps

- Learn about [Model Registry](./model-registry) authentication
- Explore [SDK Configuration](./sdk-configuration) options
- Read about [Security Best Practices](./security)