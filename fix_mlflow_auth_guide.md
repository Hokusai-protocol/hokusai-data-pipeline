# MLFlow 403 Authentication Error - Root Cause and Solutions

## Root Cause Analysis

The 403 error occurs because:

1. **MLFlow Server Authentication**: The MLFlow server at `registry.hokus.ai/mlflow` requires authentication
2. **Missing MLFlow Credentials**: The SDK is not automatically passing MLFlow authentication when using the Hokusai API key
3. **Authentication Separation**: Hokusai API authentication (via `HOKUSAI_API_KEY`) is separate from MLFlow server authentication

## Architecture Overview

```
Third Party App → Hokusai SDK → Hokusai API → MLFlow Server
                      ↓              ↓              ↓
                 HOKUSAI_API_KEY  (strips auth)  Requires Auth
```

The Hokusai API proxy (`mlflow_proxy.py`) intentionally strips authentication headers before forwarding to MLFlow, expecting the MLFlow server to be internal. However, the production MLFlow server requires its own authentication.

## Solutions (Prioritized)

### Solution 1: Configure MLFlow Authentication (Recommended)

Third parties need to set MLFlow authentication in addition to their Hokusai API key:

```python
import os
from hokusai import setup, ModelRegistry
from hokusai.config import setup_mlflow_auth

# Set both Hokusai and MLFlow authentication
os.environ["HOKUSAI_API_KEY"] = "your_hokusai_api_key"
os.environ["MLFLOW_TRACKING_TOKEN"] = "your_mlflow_token"  # Or use username/password

# Initialize with MLFlow auth
setup(api_key=os.environ["HOKUSAI_API_KEY"])
setup_mlflow_auth(validate=True)

# Now register models
registry = ModelRegistry()
result = registry.register_tokenized_model(
    model_uri="runs:/abc123/model",
    model_name="your-model",
    token_id="your-token",
    metric_name="accuracy",
    baseline_value=0.93
)
```

### Solution 2: Use Mock Mode for Local Development

For development without MLFlow access:

```python
import os
os.environ["HOKUSAI_MOCK_MODE"] = "true"  # Bypass MLFlow entirely

from hokusai import ModelRegistry
registry = ModelRegistry(api_key="your_api_key")
# All operations will be simulated locally
```

### Solution 3: Use Optional MLFlow Mode

Auto-fallback to mock mode when MLFlow is unavailable:

```python
import os
os.environ["HOKUSAI_OPTIONAL_MLFLOW"] = "true"  # Auto-fallback on errors

from hokusai import ModelRegistry
registry = ModelRegistry(api_key="your_api_key")
# Will try MLFlow, fallback to mock if it fails
```

### Solution 4: Update SDK to Auto-Configure MLFlow Auth

We should update the SDK to automatically use the Hokusai API key for MLFlow authentication:

```python
# In hokusai/core/registry.py ModelRegistry.__init__
if not os.getenv("MLFLOW_TRACKING_TOKEN") and self._auth.api_key:
    # Use Hokusai API key as MLFlow token
    os.environ["MLFLOW_TRACKING_TOKEN"] = self._auth.api_key
```

### Solution 5: Use API-Based Registration

Register models through the Hokusai API instead of directly to MLFlow:

```python
registry = ModelRegistry(api_key="your_api_key")
result = registry.register_baseline_via_api(
    model_type="your_model_type",
    mlflow_run_id="your_run_id",
    metadata={"key": "value"}
)
```

## Quick Fix for Third Parties

Add this before model registration:

```python
import os

# Option 1: Use Hokusai API key as MLFlow token
if os.getenv("HOKUSAI_API_KEY") and not os.getenv("MLFLOW_TRACKING_TOKEN"):
    os.environ["MLFLOW_TRACKING_TOKEN"] = os.getenv("HOKUSAI_API_KEY")

# Option 2: Enable optional MLFlow mode
os.environ["HOKUSAI_OPTIONAL_MLFLOW"] = "true"
```

## Testing the Fix

```python
# Test script for third parties
import os
from hokusai import setup, ModelRegistry
from hokusai.config import setup_mlflow_auth, get_mlflow_auth_status

# Check current auth status
print("MLFlow auth status:", get_mlflow_auth_status())

# Setup authentication
os.environ["MLFLOW_TRACKING_TOKEN"] = os.environ.get("HOKUSAI_API_KEY", "")
setup_mlflow_auth(validate=True)

# Test connection
registry = ModelRegistry()
print("Connection successful!")
```

## Long-term Recommendations

1. **Documentation Update**: Add MLFlow authentication requirements to the quickstart guide
2. **SDK Enhancement**: Auto-configure MLFlow auth when Hokusai API key is provided
3. **Error Messages**: Improve error messages to guide users to set MLFlow credentials
4. **Unified Auth**: Consider providing MLFlow tokens through Hokusai API
5. **Environment Templates**: Provide `.env.example` with all required variables