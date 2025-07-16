---
id: mlflow-authentication
title: MLflow Authentication Setup
sidebar_label: MLflow Authentication
sidebar_position: 5
---

# MLflow Authentication Setup

This guide explains how to configure authentication for MLflow when using the Hokusai ML Platform.

## Quick Fix for 403 Errors

If you're encountering MLflow 403 authentication errors:

```bash
# Option 1: Use token authentication
export MLFLOW_TRACKING_TOKEN="your-mlflow-token"

# Option 2: Use mock mode for local development
export HOKUSAI_MOCK_MODE=true

# Option 3: Allow fallback to mock mode when MLflow is unavailable
export HOKUSAI_OPTIONAL_MLFLOW=true  # (default)
```

## Authentication Methods

### 1. Token Authentication (Recommended)

Most MLflow deployments use bearer token authentication:

```bash
export MLFLOW_TRACKING_TOKEN="your-mlflow-api-token"
export MLFLOW_TRACKING_URI="https://your-mlflow-server.com"
```

### 2. Basic Authentication

For MLflow servers with username/password authentication:

```bash
export MLFLOW_TRACKING_USERNAME="your-username"
export MLFLOW_TRACKING_PASSWORD="your-password"
export MLFLOW_TRACKING_URI="https://your-mlflow-server.com"
```

### 3. AWS Signature Authentication

For MLflow on AWS with IAM authentication:

```bash
export MLFLOW_TRACKING_AWS_SIGV4=true
export MLFLOW_TRACKING_URI="https://your-mlflow-server.amazonaws.com"
```

### 4. Databricks Authentication

For Databricks-hosted MLflow:

```bash
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="your-databricks-token"
```

## Development Options

### Mock Mode

For local development without MLflow:

```bash
export HOKUSAI_MOCK_MODE=true
```

This will simulate all MLflow operations locally without requiring a server.

### Optional MLflow

Allow the SDK to work even when MLflow is unavailable:

```bash
export HOKUSAI_OPTIONAL_MLFLOW=true  # (default)
```

This automatically switches to mock mode if MLflow connection fails.

## Troubleshooting

### Error: API request failed with error code 403

This indicates missing or incorrect authentication. Solutions:

1. **Set authentication token**:
   ```bash
   export MLFLOW_TRACKING_TOKEN="your-token"
   ```

2. **Use mock mode for development**:
   ```bash
   export HOKUSAI_MOCK_MODE=true
   ```

3. **Check MLflow server requirements**:
   - Contact your MLflow administrator for the correct authentication method
   - Verify the tracking URI is correct
   - Ensure your token/credentials are valid

### Verifying Configuration

```python
from hokusai.config import get_mlflow_config

# Check current configuration
config = get_mlflow_config()
print(f"Tracking URI: {config['tracking_uri']}")
print(f"Has token: {config['has_token']}")
print(f"Mock mode: {config['mock_mode']}")
```

## Example Usage

```python
import os
from hokusai.tracking import ExperimentManager

# Set authentication
os.environ["MLFLOW_TRACKING_TOKEN"] = "your-token"

# Initialize - will now work with authentication
experiment_manager = ExperimentManager("my_experiment")

# Or use mock mode for local development
os.environ["HOKUSAI_MOCK_MODE"] = "true"
experiment_manager = ExperimentManager("my_experiment")
```