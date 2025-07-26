---
id: mlflow-integration
title: MLflow Integration Guide
sidebar_label: MLflow Integration
sidebar_position: 4
---

# MLflow Integration Guide

Hokusai provides a fully integrated MLflow tracking server that allows you to use standard MLflow clients and APIs while leveraging Hokusai's authentication and model registry features.

## Overview

The MLflow integration in Hokusai provides:
- **Experiment Tracking**: Log parameters, metrics, and artifacts
- **Model Registry**: Version and manage your models
- **API Compatibility**: Use standard MLflow Python client
- **Secure Access**: Protected by Hokusai API key authentication
- **Artifact Storage**: S3-backed storage for model artifacts

## Configuration

### Setting Up MLflow Client

To use MLflow with Hokusai, configure your environment with the tracking URI and your API key:

```python
import os
import mlflow

# Set the tracking URI to Hokusai's MLflow endpoint
os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/api/mlflow"

# Use your Hokusai API key for authentication
os.environ["MLFLOW_TRACKING_TOKEN"] = "hk_live_your_api_key_here"

# For custom authentication headers (if needed)
import mlflow.tracking._tracking_service.utils
mlflow.tracking._tracking_service.utils._get_request_header_provider = \
    lambda: {"Authorization": f"Bearer {os.environ['MLFLOW_TRACKING_TOKEN']}"}
```

### Environment Variables

You can also set these as environment variables in your shell:

```bash
export MLFLOW_TRACKING_URI="https://registry.hokus.ai/api/mlflow"
export MLFLOW_TRACKING_TOKEN="hk_live_your_api_key_here"
```

## Common Operations

### Creating and Managing Experiments

```python
import mlflow

# Create a new experiment
experiment_id = mlflow.create_experiment("my-experiment")

# Set the active experiment
mlflow.set_experiment("my-experiment")

# Get experiment details
experiment = mlflow.get_experiment_by_name("my-experiment")
print(f"Experiment ID: {experiment.experiment_id}")

# List all experiments
experiments = mlflow.search_experiments()
for exp in experiments:
    print(f"{exp.name}: {exp.experiment_id}")
```

### Logging Runs

```python
import mlflow
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

# Start a new run
with mlflow.start_run() as run:
    # Log parameters
    mlflow.log_param("n_estimators", 100)
    mlflow.log_param("max_depth", 10)
    
    # Train your model
    model = RandomForestClassifier(n_estimators=100, max_depth=10)
    model.fit(X_train, y_train)
    
    # Make predictions and calculate metrics
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    
    # Log metrics
    mlflow.log_metric("accuracy", accuracy)
    mlflow.log_metric("training_samples", len(X_train))
    
    # Log the model
    mlflow.sklearn.log_model(model, "model")
    
    print(f"Run ID: {run.info.run_id}")
```

### Model Registration

```python
import mlflow

# Register a model from a run
model_name = "my-classifier"
model_version = mlflow.register_model(
    f"runs:/{run_id}/model",
    model_name
)

# Add model version tags
client = mlflow.tracking.MlflowClient()
client.set_model_version_tag(
    name=model_name,
    version=model_version.version,
    key="stage",
    value="staging"
)

# Transition model stage
client.transition_model_version_stage(
    name=model_name,
    version=model_version.version,
    stage="Production"
)
```

### Searching and Loading Models

```python
import mlflow

# Search for models
client = mlflow.tracking.MlflowClient()
models = client.search_registered_models(filter_string="name='my-classifier'")

for model in models:
    print(f"Model: {model.name}")
    for version in model.latest_versions:
        print(f"  Version {version.version}: {version.current_stage}")

# Load a specific model version
model = mlflow.pyfunc.load_model(
    model_uri=f"models:/{model_name}/{version}"
)

# Load the latest model version
model = mlflow.pyfunc.load_model(
    model_uri=f"models:/{model_name}/Production"
)

# Make predictions
predictions = model.predict(X_new)
```

## Artifact Storage

### Important Note on Artifact Endpoints

Due to the current proxy configuration, artifact operations require special handling. The standard MLflow client may encounter issues when uploading or downloading artifacts.

#### Workaround for Artifact Operations

If you encounter 404 errors when working with artifacts, you may need to use the alternative endpoint path:

```python
import requests
import os

# For direct artifact API calls, use the ajax-api path
artifact_base_url = "https://registry.hokus.ai/api/mlflow/ajax-api/2.0/mlflow-artifacts/artifacts"

# Example: List artifacts for a run
headers = {"Authorization": f"Bearer {os.environ['MLFLOW_TRACKING_TOKEN']}"}
response = requests.get(
    f"{artifact_base_url}?run_id={run_id}",
    headers=headers
)
```

#### Working Around Artifact Upload Issues

If automatic artifact logging fails, you can manually upload artifacts after the run:

```python
import mlflow
import tempfile
import os

# Option 1: Log artifacts to a temporary directory first
with mlflow.start_run() as run:
    # ... your model training code ...
    
    # Save model locally first
    with tempfile.TemporaryDirectory() as tmp_dir:
        model_path = os.path.join(tmp_dir, "model.pkl")
        joblib.dump(model, model_path)
        
        # Try to log the artifact
        try:
            mlflow.log_artifact(model_path, "model")
        except Exception as e:
            print(f"Note: Artifact upload encountered an issue: {e}")
            # Model training and metrics are still logged successfully
```

## Hokusai-Specific Features

### Token-Aware Model Registration

When registering models for Hokusai tokens, include the required metadata:

```python
# Register model with token metadata
client = mlflow.tracking.MlflowClient()

# Create model
model_name = "token-aware-model"
mlflow.register_model(f"runs:/{run_id}/model", model_name)

# Add Hokusai token tags
client.set_model_version_tag(
    name=model_name,
    version="1",
    key="hokusai_token_id",
    value="my-token"
)
client.set_model_version_tag(
    name=model_name,
    version="1",
    key="benchmark_metric",
    value="accuracy"
)
client.set_model_version_tag(
    name=model_name,
    version="1",
    key="benchmark_value",
    value="0.85"
)
```

### Integration with Hokusai SDK

You can use MLflow alongside the Hokusai SDK:

```python
from hokusai.core import ModelRegistry
import mlflow

# Use MLflow for experiment tracking
mlflow.set_experiment("hokusai-experiment")
with mlflow.start_run() as run:
    # Train and log with MLflow
    mlflow.log_metric("accuracy", 0.92)
    mlflow.sklearn.log_model(model, "model")
    
    # Register with Hokusai
    registry = ModelRegistry()
    result = registry.register_tokenized_model(
        model_uri=f"runs:/{run.info.run_id}/model",
        model_name="my-model",
        token_id="my-token",
        metric_name="accuracy",
        baseline_value=0.85
    )
```

## API Endpoints

All MLflow API endpoints are available under `/api/mlflow/*`:

### Experiments
- `GET /api/mlflow/api/2.0/mlflow/experiments/search`
- `POST /api/mlflow/api/2.0/mlflow/experiments/create`
- `GET /api/mlflow/api/2.0/mlflow/experiments/get`
- `POST /api/mlflow/api/2.0/mlflow/experiments/update`
- `POST /api/mlflow/api/2.0/mlflow/experiments/delete`

### Runs
- `POST /api/mlflow/api/2.0/mlflow/runs/create`
- `GET /api/mlflow/api/2.0/mlflow/runs/get`
- `POST /api/mlflow/api/2.0/mlflow/runs/update`
- `POST /api/mlflow/api/2.0/mlflow/runs/log-metric`
- `POST /api/mlflow/api/2.0/mlflow/runs/log-parameter`
- `POST /api/mlflow/api/2.0/mlflow/runs/log-batch`
- `GET /api/mlflow/api/2.0/mlflow/runs/search`

### Models
- `POST /api/mlflow/api/2.0/mlflow/registered-models/create`
- `GET /api/mlflow/api/2.0/mlflow/registered-models/get`
- `GET /api/mlflow/api/2.0/mlflow/registered-models/search`
- `POST /api/mlflow/api/2.0/mlflow/registered-models/update`
- `POST /api/mlflow/api/2.0/mlflow/registered-models/delete`

### Model Versions
- `POST /api/mlflow/api/2.0/mlflow/model-versions/create`
- `GET /api/mlflow/api/2.0/mlflow/model-versions/get`
- `POST /api/mlflow/api/2.0/mlflow/model-versions/update`
- `POST /api/mlflow/api/2.0/mlflow/model-versions/transition-stage`
- `GET /api/mlflow/api/2.0/mlflow/model-versions/search`

### Artifacts
- **Standard Path**: `/api/mlflow/api/2.0/mlflow-artifacts/artifacts/*` (may return 404)
- **Alternative Path**: `/api/mlflow/ajax-api/2.0/mlflow-artifacts/artifacts/*` (use if standard path fails)

## Troubleshooting

### Authentication Errors

If you receive 401 or 403 errors:
1. Verify your API key is valid and active
2. Ensure the API key is correctly set in `MLFLOW_TRACKING_TOKEN`
3. Check that the Authorization header is being sent

### Connection Issues

If you cannot connect to the MLflow server:
1. Verify the tracking URI is correct: `https://registry.hokus.ai/api/mlflow`
2. Check your network connectivity
3. Ensure your API key has the necessary permissions

### Model Registration Failures

If model registration fails:
1. Ensure the run has completed successfully
2. Verify the model artifact was logged
3. Check that the model name follows naming conventions
4. Ensure you have the required permissions

### Artifact Storage Issues

If you encounter 404 errors when uploading or downloading artifacts:
1. This is a known issue with the current proxy configuration
2. Model training and metrics logging will still work correctly
3. Use the alternative ajax-api endpoint path for direct artifact API calls
4. Consider storing large artifacts externally and logging their location as a parameter

### Common Error Messages

- **"API request failed with error code 404"**: 
  - For general endpoints: Ensure you're using `/api/mlflow/*` paths
  - For artifact endpoints: Try using the ajax-api alternative path
- **"Failed to authenticate"**: Your API key is invalid or not properly configured
- **"Model not found"**: The model or version specified doesn't exist
- **"Artifact upload failed"**: Known issue - see Artifact Storage section for workarounds

## Best Practices

1. **Use Experiments**: Organize your runs into experiments for better tracking
2. **Log Everything**: Log all parameters, metrics, and artifacts for reproducibility
3. **Version Your Models**: Use model versioning to track improvements
4. **Tag Appropriately**: Use tags to add metadata for filtering and organization
5. **Handle Errors**: Implement proper error handling for API calls
6. **Clean Up**: Delete old experiments and models you no longer need
7. **Artifact Strategy**: Be aware of artifact limitations and have a backup strategy

## Example: Complete Workflow

Here's a complete example of training, logging, and registering a model:

```python
import os
import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.datasets import make_classification
from sklearn.metrics import accuracy_score, precision_score, recall_score

# Configure MLflow
os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/api/mlflow"
os.environ["MLFLOW_TRACKING_TOKEN"] = "hk_live_your_api_key_here"

# Generate sample data
X, y = make_classification(n_samples=1000, n_features=20, n_classes=2)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

# Set experiment
mlflow.set_experiment("classification-experiment")

# Start run
with mlflow.start_run() as run:
    # Log parameters
    n_estimators = 100
    max_depth = 10
    mlflow.log_param("n_estimators", n_estimators)
    mlflow.log_param("max_depth", max_depth)
    mlflow.log_param("dataset_size", len(X))
    
    # Train model
    model = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=42
    )
    model.fit(X_train, y_train)
    
    # Evaluate model
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    precision = precision_score(y_test, predictions)
    recall = recall_score(y_test, predictions)
    
    # Log metrics
    mlflow.log_metric("accuracy", accuracy)
    mlflow.log_metric("precision", precision)
    mlflow.log_metric("recall", recall)
    
    # Log model (artifact upload may fail but model will still be registered)
    try:
        mlflow.sklearn.log_model(
            model, 
            "model",
            registered_model_name="rf-classifier"
        )
    except Exception as e:
        print(f"Note: Artifact upload issue: {e}")
        # Model registration may still succeed
    
    print(f"Run completed! ID: {run.info.run_id}")
    print(f"Accuracy: {accuracy:.3f}")

# Add model metadata
client = mlflow.tracking.MlflowClient()
try:
    model_version = client.get_latest_versions("rf-classifier")[0]
    
    client.set_model_version_tag(
        name="rf-classifier",
        version=model_version.version,
        key="algorithm",
        value="random_forest"
    )
except Exception as e:
    print(f"Model version tagging note: {e}")
```

## Additional Resources

- [MLflow Documentation](https://mlflow.org/docs/latest/index.html)
- [Hokusai API Reference](/api/reference)
- [Authentication Guide](/authentication)
- [Model Registry Guide](/ml-platform/model-registry)