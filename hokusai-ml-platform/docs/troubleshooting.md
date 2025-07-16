# Troubleshooting Guide

This guide helps resolve common issues when using the Hokusai ML Platform SDK.

## Common Issues and Solutions

### 1. MLflow Authentication Errors

#### Error: HTTP 403 Forbidden
```
MLflow authentication error (HTTP 403): Access forbidden
```

**Solutions:**
1. Set `HOKUSAI_MOCK_MODE=true` for local development without MLflow
2. Configure MLflow authentication:
   ```bash
   export MLFLOW_TRACKING_USERNAME="your_username"
   export MLFLOW_TRACKING_PASSWORD="your_password"
   ```
3. Use token authentication:
   ```bash
   export MLFLOW_TRACKING_TOKEN="your_token"
   ```
4. Enable optional MLflow mode:
   ```bash
   export HOKUSAI_OPTIONAL_MLFLOW=true
   ```

#### Error: HTTP 401 Unauthorized
```
MLflow authentication error (HTTP 401): Invalid credentials
```

**Solutions:**
- Verify your credentials are correct
- Check if credentials have expired
- Ensure you're using the correct authentication method

### 2. API Method Issues

#### Error: register_baseline() got an unexpected keyword argument 'model_name'
This has been fixed in the latest version. The method now accepts both signatures:

```python
# Both work now:
registry.register_baseline(model=model, model_type="type")
registry.register_baseline(model_name="name", model=model)
```

#### Error: ModelVersionManager missing methods
The following methods have been added:
- `get_latest_version(model_name)`
- `list_versions(model_name)`

Example usage:
```python
version_manager = ModelVersionManager(registry)
latest = version_manager.get_latest_version("my_model")
all_versions = version_manager.list_versions("my_model")
```

### 3. Connection Issues

#### Error: Failed to connect to MLflow server
```python
# Enable optional MLflow mode
os.environ["HOKUSAI_OPTIONAL_MLFLOW"] = "true"

# Or use mock mode for testing
os.environ["HOKUSAI_MOCK_MODE"] = "true"
```

#### Error: Connection timeout
The SDK includes automatic retry logic with exponential backoff. If issues persist:
1. Check network connectivity
2. Verify MLflow server is running
3. Increase timeout settings

### 4. Missing Methods

#### Error: PerformanceTracker.track_inference() not found
This method has been added. Usage:
```python
tracker = PerformanceTracker()
tracker.track_inference({
    "model_id": "model-001",
    "model_version": "1.0.0",
    "latency_ms": 45.2,
    "confidence": 0.89
})
```

#### Error: HokusaiInferencePipeline.predict_batch() signature mismatch
The method now supports the expected signature:
```python
pipeline = HokusaiInferencePipeline(registry, version_manager, traffic_router)
predictions = pipeline.predict_batch(
    data=[item1, item2, item3],
    model_name="my_model",
    model_version="1.0.0"  # Optional
)
```

### 5. Environment Setup

#### Missing Environment Variables
Required:
```bash
export HOKUSAI_API_KEY="your_api_key"
```

Optional but recommended:
```bash
export HOKUSAI_API_ENDPOINT="https://api.hokus.ai"
export MLFLOW_TRACKING_URI="https://mlflow.hokus.ai"
export HOKUSAI_OPTIONAL_MLFLOW="true"  # For resilience
```

### 6. Debugging Tips

#### Enable Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### Check MLflow Status
```python
from hokusai.config import get_mlflow_auth_status
status = get_mlflow_auth_status()
print(status)
```

#### Verify API Key
```python
from hokusai import configure

try:
    configure(api_key="your_key", validate_with_auth_service=True)
    print("API key is valid")
except Exception as e:
    print(f"API key validation failed: {e}")
```

### 7. Migration from Previous Versions

If upgrading from an older version:

1. Update import statements:
   ```python
   # Old
   from hokusai_ml_platform import ModelRegistry
   
   # New
   from hokusai import ModelRegistry
   ```

2. Update ExperimentManager initialization:
   ```python
   # Both old and new styles work:
   exp_manager = ExperimentManager("experiment_name")  # New
   exp_manager = ExperimentManager(registry)  # Old (still works)
   ```

3. Update error handling:
   ```python
   from hokusai import MLflowConnectionError, MLflowAuthenticationError
   
   try:
       # Your code
   except MLflowAuthenticationError:
       # Handle auth errors
   except MLflowConnectionError:
       # Handle connection errors
   ```

## Getting Help

If you continue to experience issues:

1. Check the [examples directory](../examples/) for working code samples
2. Review the [API documentation](../docs/)
3. Enable debug logging to see detailed error messages
4. Report issues with full error messages and environment details