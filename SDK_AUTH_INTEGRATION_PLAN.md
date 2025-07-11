# SDK Authentication Integration Plan

## Overview

This document outlines how API key authentication will be integrated into the Hokusai Python SDK to ensure seamless usage for SDK users.

## Current Architecture Issues

1. **Separation**: API key management is in the main pipeline, not the SDK package
2. **Missing Integration**: SDK components don't have authentication built-in
3. **User Experience**: SDK users need a simple way to authenticate

## Proposed Solution

### 1. Add Authentication Module to SDK

```
hokusai-ml-platform/
├── src/
│   └── hokusai/
│       ├── __init__.py
│       ├── auth/                    # NEW: Authentication module
│       │   ├── __init__.py
│       │   ├── client.py           # API client with auth
│       │   ├── config.py           # Auth configuration
│       │   └── exceptions.py       # Auth exceptions
│       ├── core/                   # Existing
│       └── utils/                  # Existing
```

### 2. SDK Authentication Methods

#### Method 1: Environment Variable (Simplest)
```python
# User sets environment variable
export HOKUSAI_API_KEY="hk_live_user_key_123"

# SDK automatically uses it
from hokusai.core import ModelRegistry
registry = ModelRegistry()  # Auth handled internally
```

#### Method 2: Direct Initialization
```python
from hokusai.core import ModelRegistry

registry = ModelRegistry(api_key="hk_live_user_key_123")
```

#### Method 3: Configuration File
```python
# ~/.hokusai/config
[default]
api_key = hk_live_user_key_123
api_endpoint = https://api.hokus.ai

# SDK reads config
from hokusai.core import ModelRegistry
registry = ModelRegistry()  # Uses config file
```

#### Method 4: Auth Object
```python
from hokusai.auth import HokusaiAuth
from hokusai.core import ModelRegistry

auth = HokusaiAuth(api_key="hk_live_user_key_123")
registry = ModelRegistry(auth=auth)
```

### 3. Implementation Changes

#### Update Base Classes

```python
# hokusai/auth/client.py
class AuthenticatedClient:
    """Base client with authentication."""
    
    def __init__(self, api_key=None, api_endpoint=None):
        self.api_key = api_key or os.environ.get("HOKUSAI_API_KEY")
        self.api_endpoint = api_endpoint or os.environ.get(
            "HOKUSAI_API_ENDPOINT", 
            "https://api.hokus.ai"
        )
        
        if not self.api_key:
            raise AuthenticationError("No API key provided")
    
    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def _make_request(self, method, endpoint, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.update(self._get_headers())
        
        response = requests.request(
            method,
            f"{self.api_endpoint}{endpoint}",
            headers=headers,
            **kwargs
        )
        
        if response.status_code == 401:
            raise AuthenticationError("Invalid API key")
        
        response.raise_for_status()
        return response.json()
```

#### Update ModelRegistry

```python
# hokusai/core/registry.py
from hokusai.auth.client import AuthenticatedClient

class ModelRegistry(AuthenticatedClient):
    """Model registry with built-in authentication."""
    
    def __init__(self, tracking_uri=None, **auth_kwargs):
        super().__init__(**auth_kwargs)
        self.tracking_uri = tracking_uri or os.environ.get(
            "MLFLOW_TRACKING_URI",
            f"{self.api_endpoint}/mlflow"
        )
        mlflow.set_tracking_uri(self.tracking_uri)
    
    def register_baseline(self, model, model_type, metadata):
        """Register baseline model via authenticated API."""
        # Use parent's _make_request method
        return self._make_request(
            "POST",
            "/api/v1/models/baseline",
            json={
                "model_type": model_type,
                "metadata": metadata,
                "mlflow_run_id": mlflow.active_run().info.run_id
            }
        )
```

### 4. CLI Integration

```python
# hokusai/cli/auth.py
@click.group()
def auth():
    """Manage Hokusai authentication."""
    pass

@auth.command()
@click.option("--api-key", prompt=True, hide_input=True)
def login(api_key):
    """Save API key for future use."""
    config_dir = Path.home() / ".hokusai"
    config_dir.mkdir(exist_ok=True)
    
    config_file = config_dir / "config"
    config = configparser.ConfigParser()
    
    config["default"] = {"api_key": api_key}
    
    with open(config_file, "w") as f:
        config.write(f)
    
    # Set restrictive permissions
    config_file.chmod(0o600)
    
    click.echo("✅ Authentication saved successfully!")

@auth.command()
def logout():
    """Remove saved authentication."""
    config_file = Path.home() / ".hokusai" / "config"
    if config_file.exists():
        config_file.unlink()
        click.echo("✅ Logged out successfully!")
    else:
        click.echo("No authentication found.")
```

### 5. Error Handling

```python
# hokusai/auth/exceptions.py
class HokusaiAuthError(Exception):
    """Base authentication error."""
    pass

class AuthenticationError(HokusaiAuthError):
    """Invalid or missing API key."""
    pass

class AuthorizationError(HokusaiAuthError):
    """Valid key but insufficient permissions."""
    pass

class RateLimitError(HokusaiAuthError):
    """Rate limit exceeded."""
    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after
```

### 6. Updated SDK Usage Examples

```python
# Example 1: Quick start with environment variable
os.environ["HOKUSAI_API_KEY"] = "hk_live_my_key_123"

from hokusai.core import ModelRegistry
from hokusai.tracking import ExperimentManager

registry = ModelRegistry()
manager = ExperimentManager(registry)

# Example 2: Explicit configuration
from hokusai import configure

configure(
    api_key="hk_live_my_key_123",
    api_endpoint="https://api.hokus.ai"
)

# Example 3: Multiple environments
from hokusai.auth import Profile

# Development
dev = Profile(
    name="dev",
    api_key="hk_test_dev_key_123",
    api_endpoint="http://localhost:8000"
)

# Production
prod = Profile(
    name="prod",
    api_key="hk_live_prod_key_123",
    api_endpoint="https://api.hokus.ai"
)

# Use dev environment
registry = ModelRegistry(profile=dev)
```

### 7. Backward Compatibility

To maintain backward compatibility:

1. **MLflow Direct Access**: Users can still use MLflow directly if needed
2. **Optional Authentication**: Make auth optional for local/development use
3. **Gradual Migration**: Provide migration guide for existing users

### 8. Security Considerations

1. **Never log API keys**
2. **Use secure storage for config files** (chmod 600)
3. **Support key rotation** without code changes
4. **Clear error messages** without exposing keys
5. **HTTPS only** for API communication

### 9. Testing Strategy

1. **Mock authentication** in unit tests
2. **Integration tests** with test API keys
3. **Security tests** for key handling
4. **Documentation tests** for all examples

## Benefits of This Approach

1. **Simple for Users**: Just set env var or use config file
2. **Flexible**: Multiple authentication methods
3. **Secure**: Follows best practices
4. **SDK-Native**: Authentication is built into SDK components
5. **Backward Compatible**: Existing code continues to work

## Migration Path

1. **Phase 1**: Add auth module to SDK (backward compatible)
2. **Phase 2**: Update documentation with auth examples
3. **Phase 3**: Deprecate unauthenticated usage (with warnings)
4. **Phase 4**: Require authentication in next major version

## Next Steps

1. Update the test files to reflect SDK integration
2. Implement authentication module in hokusai-ml-platform
3. Update all SDK components to use authenticated client
4. Create migration guide for existing users
5. Update documentation with authentication examples