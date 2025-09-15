# Hokusai Authentication Guide

## Overview

The Hokusai ML Platform requires proper authentication to access the model registry and MLflow services. This guide explains how to set up authentication correctly.

## Required Environment Variables

Both of these environment variables **MUST** be set:

1. **`HOKUSAI_API_KEY`** - Required for Hokusai SDK authentication
2. **`MLFLOW_TRACKING_TOKEN`** - Required for MLflow API access

Both should be set to the same API key value.

## Quick Start

```bash
# Set your API key (obtain from https://hokus.ai/settings/api-keys)
export HOKUSAI_API_KEY='hk_live_your_api_key_here'
export MLFLOW_TRACKING_TOKEN='hk_live_your_api_key_here'
export MLFLOW_TRACKING_URI='https://registry.hokus.ai/api/mlflow'
```

## Authentication Methods

### Method 1: Environment Variables (Recommended)

Set environment variables in your shell or `.env` file:

```bash
export HOKUSAI_API_KEY='hk_live_your_api_key_here'
export MLFLOW_TRACKING_TOKEN='hk_live_your_api_key_here'
export MLFLOW_TRACKING_URI='https://registry.hokus.ai/api/mlflow'
```

Then initialize the registry:

```python
from hokusai.core import ModelRegistry

registry = ModelRegistry()  # Automatically uses environment variables
```

### Method 2: Direct Parameter

Pass the API key directly to the ModelRegistry:

```python
from hokusai.core import ModelRegistry

registry = ModelRegistry(api_key='hk_live_your_api_key_here')

# Note: You still need to set MLFLOW_TRACKING_TOKEN for MLflow operations
import os
os.environ["MLFLOW_TRACKING_TOKEN"] = 'hk_live_your_api_key_here'
```

### Method 3: Configuration File

Create a configuration file at `~/.hokusai/config`:

```ini
[default]
api_key = hk_live_your_api_key_here
api_endpoint = https://registry.hokus.ai/api
```

### Method 4: Global Initialization

Initialize Hokusai globally in your application:

```python
import hokusai

hokusai.init(api_key='hk_live_your_api_key_here')

# Then use ModelRegistry without parameters
from hokusai.core import ModelRegistry
registry = ModelRegistry()
```

## Common Issues and Solutions

### Issue: "No API key found"

**Error:**
```
ValueError: No API key found. Set HOKUSAI_API_KEY environment variable
```

**Solution:**
Set the HOKUSAI_API_KEY environment variable:
```bash
export HOKUSAI_API_KEY='your_api_key_here'
```

### Issue: "Authentication failed: HOKUSAI_API_KEY is required"

**Error:**
```
ValueError: Authentication failed: HOKUSAI_API_KEY is required.
You have MLFLOW_TRACKING_TOKEN set, but Hokusai requires HOKUSAI_API_KEY.
```

**Solution:**
You've set MLFLOW_TRACKING_TOKEN but not HOKUSAI_API_KEY. Set both:
```bash
export HOKUSAI_API_KEY='your_api_key_here'
export MLFLOW_TRACKING_TOKEN='your_api_key_here'  # Same key
```

### Issue: MLflow 403 Forbidden

**Error:**
```
RestException: API request to endpoint /api/2.0/mlflow/runs/create failed with error code 403
```

**Solution:**
Ensure MLFLOW_TRACKING_TOKEN is set:
```bash
export MLFLOW_TRACKING_TOKEN='your_api_key_here'
```

### Issue: Cannot connect to MLflow

**Error:**
```
ConnectionError: Cannot connect to MLflow tracking server
```

**Solution:**
Set the correct MLflow tracking URI:
```bash
export MLFLOW_TRACKING_URI='https://registry.hokus.ai/api/mlflow'
```

## Complete Example

Here's a complete example showing proper authentication setup:

```python
import os
import mlflow
from sklearn.ensemble import RandomForestClassifier
from hokusai.core import ModelRegistry

# Step 1: Set up authentication
os.environ["HOKUSAI_API_KEY"] = "hk_live_your_api_key"
os.environ["MLFLOW_TRACKING_TOKEN"] = "hk_live_your_api_key"  # Same key
os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/api/mlflow"

# Step 2: Initialize registry
registry = ModelRegistry()

# Step 3: Train and register model
with mlflow.start_run() as run:
    # Train your model
    model = RandomForestClassifier()
    # ... training code ...

    # Log to MLflow
    mlflow.sklearn.log_model(model, "model")

    # Register with Hokusai
    model_uri = f"runs:/{run.info.run_id}/model"
    result = registry.register_tokenized_model(
        model_uri=model_uri,
        model_name="my-classifier",
        token_id="CLASS-001",
        metric_name="accuracy",
        baseline_value=0.92
    )

    print(f"Model registered: {result}")
```

## Security Best Practices

1. **Never hardcode API keys** in your source code
2. **Use environment variables** or secure secret management systems
3. **Rotate API keys regularly**
4. **Use different keys** for development and production
5. **Never commit** `.env` files containing keys to version control

## Getting an API Key

1. Sign up at https://hokus.ai
2. Navigate to Settings → API Keys
3. Generate a new API key
4. Copy the key (it won't be shown again)
5. Store it securely

## Verification

To verify your authentication is working:

```python
from hokusai.core import ModelRegistry

try:
    registry = ModelRegistry()
    print("✅ Authentication successful!")
except ValueError as e:
    print(f"❌ Authentication failed: {e}")
```

## Support

If you continue to experience authentication issues:

1. Verify your API key is valid at https://hokus.ai/settings/api-keys
2. Check that both required environment variables are set
3. Ensure you're using the correct API endpoint
4. Contact support at support@hokus.ai with your error message