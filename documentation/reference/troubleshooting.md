---
id: troubleshooting
title: Troubleshooting Guide
sidebar_label: Troubleshooting
sidebar_position: 10
---

# Troubleshooting Guide

Common issues and solutions when using the Hokusai ML Platform.

## MLflow Authentication Error (403)

**Error Message:**
```
RegistryException: Failed to register baseline model: API request to endpoint /api/2.0/mlflow/model-versions/create failed with error code 403 != 200
```

**Solution:**

1. **Set MLflow authentication token**:
   ```bash
   export MLFLOW_TRACKING_TOKEN="your-mlflow-token"
   ```

2. **Use mock mode for local development**:
   ```bash
   export HOKUSAI_MOCK_MODE=true
   ```

3. **Enable automatic fallback** (default):
   ```bash
   export HOKUSAI_OPTIONAL_MLFLOW=true
   ```

See the [MLflow Authentication Guide](../guides/mlflow-authentication.md) for detailed setup instructions.

## Installation Issues

**Error:** `setuptools.errors.InvalidConfigError: License classifiers have been superseded`

**Solution:** Install from GitHub:
```bash
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform
```

## Environment Variables

Essential environment variables:

- `HOKUSAI_API_KEY`: Your Hokusai API key
- `MLFLOW_TRACKING_TOKEN`: MLflow authentication token
- `MLFLOW_TRACKING_URI`: MLflow server URL (default: http://registry.hokus.ai/mlflow)
- `HOKUSAI_MOCK_MODE`: Enable mock mode (true/false)
- `HOKUSAI_OPTIONAL_MLFLOW`: Allow fallback to mock mode (true/false, default: true)