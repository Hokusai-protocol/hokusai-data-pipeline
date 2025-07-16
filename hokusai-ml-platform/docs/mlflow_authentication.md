# MLflow Authentication Guide

This guide explains how to configure MLflow authentication for the Hokusai ML Platform SDK.

## Overview

The Hokusai SDK supports multiple MLflow authentication methods and can operate in optional mode when MLflow is unavailable.

## Authentication Methods

### 1. Basic Authentication

Set environment variables:
```bash
export MLFLOW_TRACKING_URI="https://mlflow.example.com"
export MLFLOW_TRACKING_USERNAME="your_username"
export MLFLOW_TRACKING_PASSWORD="your_password"
```

Or configure programmatically:
```python
from hokusai import setup_mlflow_auth

setup_mlflow_auth(
    tracking_uri="https://mlflow.example.com",
    username="your_username",
    password="your_password"
)
```

### 2. Token Authentication

Set environment variables:
```bash
export MLFLOW_TRACKING_URI="https://mlflow.example.com"
export MLFLOW_TRACKING_TOKEN="your_bearer_token"
```

Or configure programmatically:
```python
setup_mlflow_auth(
    tracking_uri="https://mlflow.example.com",
    token="your_bearer_token"
)
```

### 3. AWS Signature V4 Authentication

For AWS-hosted MLflow:
```bash
export MLFLOW_TRACKING_URI="https://mlflow.aws.example.com"
export MLFLOW_TRACKING_AWS_SIGV4="true"
# AWS credentials should be configured via AWS CLI or IAM role
```

### 4. Client Certificate (mTLS)

For mutual TLS authentication:
```bash
export MLFLOW_TRACKING_URI="https://mlflow.example.com"
export MLFLOW_TRACKING_CLIENT_CERT_PATH="/path/to/client.crt"
export MLFLOW_TRACKING_CLIENT_KEY_PATH="/path/to/client.key"
export MLFLOW_TRACKING_CA_BUNDLE_PATH="/path/to/ca-bundle.crt"  # Optional
```

## Optional MLflow Mode

The SDK can operate without MLflow when it's unavailable:

### Automatic Fallback
```bash
# Enable automatic fallback to mock mode
export HOKUSAI_OPTIONAL_MLFLOW="true"
```

### Manual Mock Mode
```bash
# Force mock mode (no MLflow connection attempts)
export HOKUSAI_MOCK_MODE="true"
```

## Error Handling

### Common Authentication Errors

#### HTTP 403 - Forbidden
```
MLflow authentication error (HTTP 403): Access forbidden
```

Solutions:
1. Check if your credentials have proper permissions
2. Verify the MLflow server configuration
3. Use `HOKUSAI_MOCK_MODE=true` for local development

#### HTTP 401 - Unauthorized
```
MLflow authentication error (HTTP 401): Invalid credentials
```

Solutions:
1. Verify username/password or token
2. Check if credentials have expired
3. Ensure proper authentication method is used

### Connection Errors

If MLflow is unreachable:
```python
try:
    setup_mlflow_auth(tracking_uri="https://mlflow.example.com", validate=True)
except Exception as e:
    print(f"MLflow unavailable: {e}")
    # Continue without MLflow
    os.environ["HOKUSAI_OPTIONAL_MLFLOW"] = "true"
```

## Complete Example

```python
import os
from hokusai import setup_mlflow_auth, ModelRegistry

# Configure authentication
try:
    # Try token auth first
    if os.getenv("MLFLOW_TRACKING_TOKEN"):
        setup_mlflow_auth(
            tracking_uri=os.getenv("MLFLOW_TRACKING_URI"),
            token=os.getenv("MLFLOW_TRACKING_TOKEN"),
            validate=True
        )
    # Fall back to basic auth
    elif os.getenv("MLFLOW_TRACKING_USERNAME"):
        setup_mlflow_auth(
            tracking_uri=os.getenv("MLFLOW_TRACKING_URI"),
            username=os.getenv("MLFLOW_TRACKING_USERNAME"),
            password=os.getenv("MLFLOW_TRACKING_PASSWORD"),
            validate=True
        )
    else:
        print("No MLflow authentication configured")
        os.environ["HOKUSAI_OPTIONAL_MLFLOW"] = "true"
        
except Exception as e:
    print(f"MLflow setup failed: {e}")
    print("Continuing in optional MLflow mode")
    os.environ["HOKUSAI_OPTIONAL_MLFLOW"] = "true"

# Use the SDK normally - it will handle MLflow availability
registry = ModelRegistry()
```

## Troubleshooting

### Check Authentication Status

```python
from hokusai.config import get_mlflow_auth_status

status = get_mlflow_auth_status()
print(f"MLflow tracking URI: {status['tracking_uri']}")
print(f"Authentication type: {status['auth_type']}")
print(f"Is configured: {status['is_configured']}")
print(f"Is remote: {status['is_remote']}")
```

### Debug Connection Issues

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Disable TLS Verification (Development Only)

⚠️ **Warning**: Only use in development environments
```bash
export MLFLOW_TRACKING_INSECURE_TLS="true"
```