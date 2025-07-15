---
id: mlflow-access
title: MLflow Access and Configuration
sidebar_label: MLflow Access
sidebar_position: 4
---

# MLflow Access and Configuration

The Hokusai ML platform uses MLflow for experiment tracking, model registry, and performance monitoring. This guide explains how to configure and access MLflow in your applications.

## MLflow Server Location

The MLflow tracking server is hosted at:
```
http://registry.hokus.ai/mlflow
```

This server provides:
- Web UI for experiment visualization
- REST API for programmatic access
- Model registry for versioned model storage
- Artifact storage for model files and metadata

## Configuration Methods

### 1. Environment Variable (Recommended)

Set the `MLFLOW_TRACKING_URI` environment variable:

```bash
export MLFLOW_TRACKING_URI="http://registry.hokus.ai/mlflow"
```

Add this to your `.env` file or shell configuration:
```bash
# .env
MLFLOW_TRACKING_URI=http://registry.hokus.ai/mlflow
```

### 2. SDK Configuration

When using the Hokusai SDK, MLflow is automatically configured:

```python
from hokusai.tracking import ExperimentManager

# MLflow URI is automatically set to registry.hokus.ai/mlflow
experiment_manager = ExperimentManager()

# Or explicitly specify a custom URI
experiment_manager = ExperimentManager(
    mlflow_tracking_uri="http://your-custom-mlflow-server.com"
)
```

### 3. Direct MLflow Configuration

For direct MLflow usage:

```python
import mlflow

# Set tracking URI
mlflow.set_tracking_uri("http://registry.hokus.ai/mlflow")

# Now you can use MLflow normally
with mlflow.start_run():
    mlflow.log_metric("accuracy", 0.95)
```

## Local Development Mode

For local development without MLflow server access, enable mock mode:

```bash
export HOKUSAI_MOCK_MODE=true
```

In mock mode:
- All MLflow operations are simulated
- No actual connection to MLflow server
- Useful for testing and development
- Returns realistic mock data

Example:
```python
import os
os.environ["HOKUSAI_MOCK_MODE"] = "true"

from hokusai.tracking import ExperimentManager

# This will run in mock mode
experiment_manager = ExperimentManager()
```

## Authentication

The MLflow server at `registry.hokus.ai/mlflow` **does not require authentication**. All MLflow endpoints are publicly accessible to simplify integration.

Note: While MLflow doesn't require authentication, other Hokusai API endpoints still require valid API keys.

## Common Operations

### View Experiments in Web UI

Navigate to: http://registry.hokus.ai/mlflow

### List Experiments via API

```bash
curl http://registry.hokus.ai/mlflow/api/2.0/mlflow/experiments/list
```

### Get Experiment by Name

```python
import mlflow
mlflow.set_tracking_uri("http://registry.hokus.ai/mlflow")

experiment = mlflow.get_experiment_by_name("hokusai_model_improvements")
print(f"Experiment ID: {experiment.experiment_id}")
```

### Log Metrics

```python
with mlflow.start_run():
    mlflow.log_metric("accuracy", 0.95)
    mlflow.log_metric("loss", 0.05)
    mlflow.log_param("model_type", "xgboost")
```

## Troubleshooting

### Connection Errors

If you encounter connection errors:

1. **Check the MLflow server status:**
   ```bash
   curl http://registry.hokus.ai/mlflow/health/mlflow
   ```

2. **Verify your network connection:**
   ```bash
   ping registry.hokus.ai
   ```

3. **Enable mock mode for local development:**
   ```bash
   export HOKUSAI_MOCK_MODE=true
   ```

### HTTP 403 Forbidden Errors

This error should not occur with the current configuration. If you see it:

1. Ensure you're using the correct URL: `http://registry.hokus.ai/mlflow`
2. Check that you're not sending authentication headers to MLflow endpoints
3. Verify the SDK is up to date: `pip install --upgrade hokusai-ml-platform`

### Timeout Errors

If requests are timing out:

1. Check your internet connection
2. Try increasing timeout in your code:
   ```python
   import mlflow
   mlflow.set_tracking_uri("http://registry.hokus.ai/mlflow")
   # MLflow will use default timeouts
   ```

## Best Practices

1. **Always set tracking URI**: Either via environment variable or in code
2. **Use mock mode for tests**: Prevents test dependencies on external services
3. **Log comprehensive metrics**: Track all relevant model performance metrics
4. **Version your models**: Use MLflow model registry for version control
5. **Tag experiments**: Add meaningful tags for easier searching

## Example: Complete Workflow

```python
import os
import mlflow
from hokusai.tracking import ExperimentManager

# Configure MLflow (automatic with SDK)
experiment_manager = ExperimentManager()

# Start an experiment
with experiment_manager.start_experiment("my_model_v2"):
    # Train your model
    model = train_model(data)
    
    # Log metrics
    mlflow.log_metrics({
        "accuracy": 0.95,
        "f1_score": 0.93,
        "auroc": 0.97
    })
    
    # Log model
    mlflow.sklearn.log_model(model, "model")
    
    # Tag the run
    mlflow.set_tag("model_type", "gradient_boosting")
    mlflow.set_tag("dataset_version", "v3")
```

## Next Steps

- [Model Registration Guide](../cli/model-registration.md)
- [Experiment Tracking Tutorial](../tutorials/experiment-tracking.md)
- [MLflow API Reference](https://mlflow.org/docs/latest/rest-api.html)