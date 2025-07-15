# Migration Guide: From Local to External Authentication Service

This guide helps you migrate from the local database-based API key authentication to the new external authentication service.

## Overview

Starting with version 2.0, Hokusai ML Platform uses a centralized authentication service (`auth.hokus.ai`) instead of local database-stored API keys. This provides:

- Centralized key management across all Hokusai services
- Better security and compliance
- Unified authentication experience
- Improved performance with distributed caching

## What's Changed

### Architecture Changes

**Before (Local Auth):**
- API keys stored in local PostgreSQL database
- Authentication handled by the ML platform directly
- Key management through local API endpoints

**After (External Auth Service):**
- API keys managed by dedicated auth service at `auth.hokus.ai`
- ML platform validates keys with auth service
- Key management through auth service API or CLI

### API Changes

The following endpoints have been removed from the ML platform:
- `POST /api/v1/auth/keys` - Create API key
- `GET /api/v1/auth/keys` - List API keys  
- `DELETE /api/v1/auth/keys/{key_id}` - Revoke key
- `POST /api/v1/auth/keys/{key_id}/rotate` - Rotate key

These are now available at `https://auth.hokus.ai/api/v1/keys/*`

## Migration Steps

### 1. Obtain New Credentials

Contact Hokusai support to:
1. Get an admin token for API key management
2. Migrate existing API keys (if applicable)

### 2. Update Environment Variables

Add the new configuration:

```bash
# Required for key management
export HOKUSAI_ADMIN_TOKEN=your_admin_token_here

# Optional - defaults to https://auth.hokus.ai
export HOKUSAI_AUTH_SERVICE_URL=https://auth.hokus.ai

# Your API key (same format as before)
export HOKUSAI_API_KEY=hk_live_your_key_here
```

### 3. Update CLI Configuration

If using the CLI config file at `~/.hokusai/config`:

```ini
[default]
api_key = hk_live_your_api_key_here
admin_token = your_admin_token_here
auth_service_url = https://auth.hokus.ai
```

### 4. Create New API Keys

Use the updated CLI to create new keys:

```bash
# Create a new key
hokusai auth create-key --name "Production Key"

# List your keys
hokusai auth list-keys

# Validate a key
hokusai auth validate
```

### 5. Update Your Applications

#### Python SDK

No code changes required if using environment variables. The SDK automatically uses the auth service.

If configuring manually, you can enable validation:

```python
from hokusai import setup

setup(
    api_key="hk_live_your_key",
    validate_with_auth_service=True  # Optional validation on setup
)
```

#### REST API

No changes required. Continue using the same headers:

```bash
# Still works exactly the same
curl https://api.hokus.ai/v1/models \
  -H "Authorization: Bearer hk_live_your_key"
```

### 6. Update API Key Management Code

If you were programmatically managing API keys:

**Before:**
```python
# Old way - direct API calls to ML platform
response = requests.post(
    "https://api.hokus.ai/v1/auth/keys",
    headers={"Authorization": f"Bearer {api_key}"},
    json={"name": "My Key"}
)
```

**After:**
```python
# New way - calls to auth service with admin token
response = requests.post(
    "https://auth.hokus.ai/api/v1/keys",
    headers={"Authorization": f"Bearer {admin_token}"},
    json={
        "name": "My Key",
        "service_id": "ml-platform"
    }
)
```

## Breaking Changes

1. **Database Schema**: The `api_keys` and `api_key_usage` tables are no longer used
2. **Local Auth Endpoints**: All `/api/v1/auth/*` endpoints removed from ML platform
3. **Admin Token Required**: Key management now requires an admin token
4. **Service ID**: When creating keys via API, must specify `"service_id": "ml-platform"`

## Benefits of Migration

1. **Unified Authentication**: Single sign-on across all Hokusai services
2. **Better Security**: Centralized security policies and monitoring
3. **Improved Performance**: Distributed caching reduces latency
4. **Enhanced Features**: 
   - Cross-service API keys
   - Granular scopes and permissions
   - Better usage analytics
   - Automated key rotation policies

## Troubleshooting

### "Authentication service unavailable"

If you see this error:
1. Check if `HOKUSAI_AUTH_SERVICE_URL` is set correctly
2. Verify network connectivity to `auth.hokus.ai`
3. Check service status at `status.hokus.ai`

### "Admin token required"

For key management operations:
1. Ensure `HOKUSAI_ADMIN_TOKEN` is set
2. Verify the token is valid with support

### Old Keys Not Working

Old database-stored keys will not work with the new system:
1. Create new keys using the auth service
2. Update your applications with new keys
3. Contact support if you need to migrate existing keys

## Support

For migration assistance:
- Email: support@hokus.ai
- Discord: [Join our community](https://discord.gg/hokusai)
- Documentation: https://docs.hokus.ai/authentication

## Timeline

- **Version 2.0**: External auth service support added
- **Version 2.1**: Local auth deprecated (with warnings)
- **Version 3.0**: Local auth removed completely

We recommend migrating as soon as possible to benefit from the improved authentication system.