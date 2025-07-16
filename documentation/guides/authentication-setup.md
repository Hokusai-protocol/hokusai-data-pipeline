---
id: authentication-setup
title: Authentication Setup
sidebar_label: Authentication Setup
sidebar_position: 3
---

# Authentication Setup for Hokusai ML Platform

This guide explains how to configure authentication for the Hokusai ML Platform, particularly for third-party developers registering models.

## Overview

The Hokusai ML Platform uses API key authentication for both the Hokusai API and MLflow tracking server. The SDK automatically handles authentication configuration with intelligent fallback mechanisms.

## Quick Start

For most users, simply set your Hokusai API key:

```bash
export HOKUSAI_API_KEY="your-api-key-here"
```

Then use the SDK normally:

```python
from hokusai import setup
from hokusai.core import ModelRegistry

# Initialize with your API key
setup(api_key=os.environ["HOKUSAI_API_KEY"])

# Create registry - authentication is handled automatically
registry = ModelRegistry()

# Register your model
result = registry.register_baseline(
    model=your_model,
    model_type="sklearn"
)
```

## How Authentication Works

### 1. Automatic Configuration

When you initialize the ModelRegistry, the SDK:

1. **Attempts Remote Connection**: First tries to connect to the production MLflow server using your Hokusai API key
2. **Automatic Token Setup**: Uses your `HOKUSAI_API_KEY` as the MLflow authentication token
3. **Fallback to Local**: If production MLflow is unavailable, automatically falls back to local MLflow server
4. **Clear Error Messages**: Provides helpful error messages if authentication fails

### 2. Authentication Flow

```
Your Application
      ↓
Hokusai SDK (with HOKUSAI_API_KEY)
      ↓
Automatic Configuration:
- Sets MLFLOW_TRACKING_TOKEN = HOKUSAI_API_KEY
- Tests connection to production MLflow
- Falls back to local if needed
      ↓
Successful Model Registration
```

## Configuration Options

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `HOKUSAI_API_KEY` | Your Hokusai API key | Yes |
| `MLFLOW_TRACKING_URI` | Override MLflow server URL | No |
| `HOKUSAI_MOCK_MODE` | Enable mock mode for testing | No |
| `HOKUSAI_OPTIONAL_MLFLOW` | Continue even if MLflow fails | No |

### Programmatic Configuration

```python
from hokusai.core import ModelRegistry

# Option 1: Pass API key directly
registry = ModelRegistry(api_key="your-api-key")

# Option 2: Use environment variable (recommended)
os.environ["HOKUSAI_API_KEY"] = "your-api-key"
registry = ModelRegistry()

# Option 3: Force specific MLflow URI
registry = ModelRegistry(
    api_key="your-api-key",
    tracking_uri="https://your-mlflow-server.com"
)
```

## Development Scenarios

### Local Development

For local development without access to production MLflow:

```python
# The SDK automatically falls back to local MLflow
# No additional configuration needed!
registry = ModelRegistry(api_key="your-api-key")
```

### Testing Without MLflow

For unit tests or development without any MLflow server:

```python
# Enable mock mode
os.environ["HOKUSAI_MOCK_MODE"] = "true"
registry = ModelRegistry(api_key="your-api-key")
# All operations will be simulated
```

### Production with Fallback

For production environments where MLflow might be temporarily unavailable:

```python
# Enable optional MLflow mode
os.environ["HOKUSAI_OPTIONAL_MLFLOW"] = "true"
registry = ModelRegistry(api_key="your-api-key")
# Operations continue even if MLflow is down
```

## Troubleshooting

### Common Issues

1. **403 Authentication Error**
   - **Cause**: MLflow server rejecting authentication
   - **Solution**: SDK automatically handles this by falling back to local MLflow
   - **Check**: Verify your API key is valid

2. **404 Not Found Error**
   - **Cause**: MLflow endpoint doesn't exist at the specified URL
   - **Solution**: SDK automatically falls back to local MLflow
   - **Check**: Production MLflow deployment status

3. **Connection Refused**
   - **Cause**: No MLflow server running locally
   - **Solution**: Start local MLflow with `mlflow server` or enable mock mode
   - **Check**: `docker ps` to see if MLflow container is running

### Debugging Authentication

Check the current authentication status:

```python
from hokusai.config import get_mlflow_status

# After initializing registry
status = get_mlflow_status()
print(f"MLflow Status: {status}")

# Output will show:
# - configured: True/False
# - tracking_uri: Current MLflow URI
# - is_local: Whether using local MLflow
# - auth_method: Authentication method in use
```

### Verification Script

Use this script to verify your authentication setup:

```python
import os
from hokusai import setup
from hokusai.core import ModelRegistry
from hokusai.config import get_mlflow_status

# Set your API key
os.environ["HOKUSAI_API_KEY"] = "your-api-key"

# Initialize
setup(api_key=os.environ["HOKUSAI_API_KEY"])
registry = ModelRegistry()

# Check status
print(f"Authentication Status: {get_mlflow_status()}")
print(f"Registry configured: {registry.tracking_uri}")
```

## Best Practices

1. **Use Environment Variables**: Store API keys in environment variables, not in code
2. **Let SDK Handle Fallback**: Don't manually configure MLflow unless necessary
3. **Check Status in Production**: Monitor MLflow connection status in production logs
4. **Enable Optional Mode**: For production, consider `HOKUSAI_OPTIONAL_MLFLOW=true`

## Security Notes

- Never commit API keys to version control
- Use different API keys for development and production
- Rotate API keys regularly
- Monitor API key usage through the Hokusai dashboard

## Next Steps

- [Register Your First Model](./model-registration.md)
- [MLflow Integration Guide](./mlflow-integration.md)
- [API Reference](../api/authentication.md)