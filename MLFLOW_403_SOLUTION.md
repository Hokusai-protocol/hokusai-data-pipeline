# MLFlow 403 Authentication Error - Complete Solution Guide

## Problem Summary

Third parties are experiencing 403 errors when trying to register models because:

1. **Production API Not Deployed**: The SDK defaults to `https://api.hokus.ai` which doesn't exist yet
2. **MLFlow Server Issues**: `registry.hokus.ai` exists but refuses connections on port 443
3. **Missing Configuration**: Third parties aren't told how to configure the SDK for their environment

## Root Cause

The SDK's default configuration points to production endpoints that aren't deployed:
- `https://api.hokus.ai` - DNS doesn't resolve
- `http://registry.hokus.ai/mlflow` - Server exists but port 443 is closed

## Immediate Solutions for Third Parties

### Solution 1: Local Development Setup

If you have the Hokusai services running locally via Docker:

```python
import os
from hokusai import setup, ModelRegistry

# Configure for local development
os.environ["HOKUSAI_API_KEY"] = "your_api_key"
os.environ["MLFLOW_TRACKING_URI"] = "http://localhost:5001"  # Local MLFlow
os.environ["HOKUSAI_API_ENDPOINT"] = "http://localhost:8001"  # Local API

# Initialize
setup(api_key=os.environ["HOKUSAI_API_KEY"])
registry = ModelRegistry()

# Now register your model
# First create an MLFlow run
import mlflow
mlflow.set_tracking_uri("http://localhost:5001")

with mlflow.start_run() as run:
    # Log your model
    mlflow.sklearn.log_model(your_model, "model")
    run_id = run.info.run_id

# Register with Hokusai
result = registry.register_tokenized_model(
    model_uri=f"runs:/{run_id}/model",
    model_name="your-model",
    token_id="your-token",
    metric_name="accuracy",
    baseline_value=0.93
)
```

### Solution 2: Use Environment Variables

Set these before running your script:

```bash
# For local development
export HOKUSAI_API_KEY="your_api_key"
export HOKUSAI_API_ENDPOINT="http://localhost:8001"
export MLFLOW_TRACKING_URI="http://localhost:5001"

# For production (when available)
# export HOKUSAI_API_ENDPOINT="https://api.hokus.ai"
# export MLFLOW_TRACKING_URI="https://mlflow.hokus.ai"
# export MLFLOW_TRACKING_TOKEN="your_mlflow_token"
```

### Solution 3: Programmatic Configuration

```python
from hokusai import ModelRegistry
from hokusai.config import setup_mlflow_auth

# Configure explicitly
registry = ModelRegistry(
    api_key="your_api_key",
    api_endpoint="http://localhost:8001",  # or production URL when available
    tracking_uri="http://localhost:5001"    # or production MLFlow when available
)

# If MLFlow requires auth
setup_mlflow_auth(
    tracking_uri="http://localhost:5001",
    token="your_mlflow_token",  # if needed
    validate=True
)
```

### Solution 4: Development Mode (No MLFlow Required)

For testing without MLFlow:

```python
import os
os.environ["HOKUSAI_OPTIONAL_MLFLOW"] = "true"  # Auto-fallback to mock mode

from hokusai import ModelRegistry
registry = ModelRegistry(api_key="your_api_key")

# Operations will work but won't persist to MLFlow
```

## SDK Improvements Needed

### 1. Better Default Handling

Update `hokusai/auth/config.py` to check endpoint availability:

```python
def _get_api_endpoint(self) -> str:
    """Get API endpoint with fallback."""
    # Check environment
    endpoint = os.environ.get("HOKUSAI_API_ENDPOINT")
    if endpoint:
        return endpoint
    
    # Check if production is available
    import socket
    try:
        socket.gethostbyname("api.hokus.ai")
        return "https://api.hokus.ai"
    except socket.gaierror:
        # Production not available, suggest local
        logger.warning(
            "Production API not available. "
            "Set HOKUSAI_API_ENDPOINT or use local endpoint: http://localhost:8001"
        )
        return "http://localhost:8001"  # Default to local
```

### 2. Clear Error Messages

When connection fails, provide actionable guidance:

```python
except ConnectionError as e:
    if "api.hokus.ai" in str(e):
        raise ConnectionError(
            "Cannot connect to Hokusai API. The production API is not yet deployed.\n"
            "Please use one of these solutions:\n"
            "1. Set HOKUSAI_API_ENDPOINT=http://localhost:8001 for local development\n"
            "2. Set HOKUSAI_OPTIONAL_MLFLOW=true to work without MLFlow\n"
            "3. See documentation at: https://docs.hokus.ai/troubleshooting"
        )
```

### 3. Auto-Configuration

The SDK should detect the environment and configure accordingly:

```python
class ModelRegistry:
    def __init__(self, ...):
        # Auto-detect environment
        if not self._check_endpoint_available(self.api_endpoint):
            logger.warning(f"Endpoint {self.api_endpoint} not available")
            
            # Try local endpoint
            if self._check_endpoint_available("http://localhost:8001"):
                logger.info("Using local development endpoint")
                self.api_endpoint = "http://localhost:8001"
                self.tracking_uri = "http://localhost:5001"
```

## Documentation Updates Needed

### 1. Quickstart Guide

Add environment setup section:

```markdown
## Environment Setup

Before using the SDK, configure your environment:

### Local Development
```bash
export HOKUSAI_API_KEY="your_api_key"
export HOKUSAI_API_ENDPOINT="http://localhost:8001"
export MLFLOW_TRACKING_URI="http://localhost:5001"
```

### Production (Coming Soon)
```bash
export HOKUSAI_API_KEY="your_api_key"
# Production endpoints will be available soon
```
```

### 2. Troubleshooting Guide

Add specific 403 error section with solutions.

### 3. Installation Guide

Include docker-compose setup for local development:

```markdown
## Local Development Setup

1. Clone the repository
2. Start services:
   ```bash
   docker-compose up -d
   ```
3. Configure SDK to use local endpoints (see Environment Setup)
```

## Testing Instructions

To verify the fix works:

```bash
# 1. Set up environment
export HOKUSAI_API_KEY="test_key"
export HOKUSAI_API_ENDPOINT="http://localhost:8001"
export MLFLOW_TRACKING_URI="http://localhost:5001"

# 2. Run test script
python test_real_registration.py

# 3. Check results
# Should see: "✓ Registration succeeded!"
```

## Summary

The 403 error is caused by the SDK trying to use production endpoints that don't exist yet. Third parties need to:

1. Configure the SDK to use local endpoints for now
2. Set appropriate environment variables
3. Wait for production deployment

The SDK should be updated to:
1. Provide better error messages
2. Auto-detect available endpoints
3. Default to local development when production is unavailable