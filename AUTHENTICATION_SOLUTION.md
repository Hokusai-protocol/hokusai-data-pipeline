# MLflow Authentication Solution

## Current Architecture

After thorough investigation, here's the current MLflow deployment architecture:

### Endpoints

1. **Direct MLflow Access**: `https://registry.hokus.ai/mlflow`
   - Uses `/ajax-api/2.0/mlflow/` paths (not standard `/api/2.0/mlflow/`)
   - **No authentication required for read operations**
   - May require auth for write operations
   - Accessible to anyone for reading experiments, models, etc.

2. **Via Hokusai API Proxy**: `https://registry.hokus.ai/api/mlflow`
   - Uses standard `/api/2.0/mlflow/` paths
   - **Requires X-API-Key header** (not Authorization header)
   - Validates Hokusai API keys
   - Strips auth headers before forwarding to MLflow

### The Authentication Challenge

The MLflow Python client has these limitations:
- Only supports standard auth headers (Authorization: Bearer/Basic)
- Cannot send custom headers like X-API-Key
- Hardcoded to use `/api/2.0/mlflow/` paths

This creates a mismatch:
- Direct MLflow uses `/ajax-api/` paths (client expects `/api/`)
- Hokusai proxy needs X-API-Key (client sends Authorization)

## Recommended Solution

### For Third-Party Developers

Until the infrastructure is updated, use this approach:

```python
import os
from hokusai import setup
from hokusai.core import ModelRegistry

# Set your API key
os.environ["HOKUSAI_API_KEY"] = "your-api-key"

# Use direct MLflow for reads (no auth needed)
os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/mlflow"

# Initialize Hokusai
setup(api_key=os.environ["HOKUSAI_API_KEY"])

# Create registry - it will fall back to local MLflow if needed
registry = ModelRegistry()

# For model registration, use the Hokusai API directly
result = registry.register_baseline_via_api(
    model_id="your-model",
    model_type="sklearn",
    version="v1.0.0",
    metrics={"accuracy": 0.95}
)
```

### Why This Works

1. **Read operations** (listing experiments, models) work without auth
2. **Write operations** use the Hokusai API's `register_baseline_via_api` method
3. **Fallback to local** MLflow for development

## Infrastructure Fixes Needed

To properly fix this, one of these changes is needed:

### Option 1: Update Hokusai API Proxy (Recommended)
- Accept Authorization: Bearer header with Hokusai API key
- Validate the bearer token as an API key
- Forward requests to MLflow without auth

### Option 2: Configure MLflow for Direct Access
- Set up MLflow to use standard `/api/2.0/mlflow/` paths
- Configure MLflow authentication to accept Hokusai API keys
- Allow direct access with proper auth

### Option 3: Custom MLflow Client
- Create a custom MLflow REST store that sends X-API-Key
- Integrate into the SDK
- Handle path differences

## Temporary Workarounds

### 1. Local Development
```bash
# Use local MLflow server
export MLFLOW_TRACKING_URI=http://localhost:5001
```

### 2. Mock Mode
```bash
# Bypass MLflow entirely
export HOKUSAI_MOCK_MODE=true
```

### 3. Optional MLflow
```bash
# Continue even if MLflow fails
export HOKUSAI_OPTIONAL_MLFLOW=true
```

## Status

- ✅ Direct MLflow access works (read-only)
- ✅ Hokusai API validates keys correctly
- ✅ SDK falls back to local MLflow
- ✅ API-based registration works
- ❌ MLflow Python client auth with proxy
- ❌ Write operations to MLflow require auth

The current SDK implementation correctly handles the fallback scenarios and provides a working solution for third-party developers.