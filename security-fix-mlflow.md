# Security Fix: MLflow Authentication

## Current Security Issues

The current implementation allows unauthenticated access to ALL MLflow endpoints, exposing:
- Proprietary ML models
- Performance metrics
- Token metadata
- Experiment data

## Proposed Solution

### Option 1: Require Hokusai API Key for MLflow Access (Recommended)

Modify the MLflow proxy to validate Hokusai API keys:

```python
# src/api/routes/mlflow_proxy.py
async def proxy_request(request: Request, path: str, mlflow_base_url: str = MLFLOW_SERVER_URL) -> Response:
    # Validate API key first
    api_key = get_api_key_from_request(request)
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required for MLflow access")
    
    # Validate the API key
    validation_result = api_key_service.validate_api_key(api_key)
    if not validation_result.is_valid:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Continue with proxy logic...
```

### Option 2: Implement Read-Only Public Access

Allow public read access but require authentication for writes:

```python
WRITE_METHODS = ["POST", "PUT", "DELETE", "PATCH"]
WRITE_PATHS = [
    "/api/2.0/mlflow/experiments/create",
    "/api/2.0/mlflow/runs/create",
    "/api/2.0/mlflow/registered-models/create",
]

if request.method in WRITE_METHODS or any(path.startswith(p) for p in WRITE_PATHS):
    # Require authentication for write operations
    api_key = get_api_key_from_request(request)
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required for write operations")
```

### Option 3: Use MLflow Native Authentication

Configure MLflow with its built-in authentication:

```yaml
# mlflow-config.yml
auth:
  enabled: true
  backend: database
  permissions:
    default: READ
    authenticated: WRITE
```

### Option 4: Token-Based Access Control

Implement fine-grained access based on token ownership:

```python
# Only allow access to experiments/models related to user's tokens
user_tokens = get_user_tokens(validation_result.user_id)
if not has_access_to_resource(path, user_tokens):
    raise HTTPException(status_code=403, detail="Access denied to this resource")
```

## Implementation Steps

1. **Remove MLflow from excluded paths**:
   ```python
   # src/middleware/auth.py
   self.excluded_paths = excluded_paths or [
       "/health",
       "/docs",
       "/openapi.json",
       "/redoc",
       "/favicon.ico",
       # Remove: "/mlflow"
   ]
   ```

2. **Update MLflow proxy to validate API keys**

3. **Add rate limiting to MLflow endpoints**

4. **Implement audit logging for all MLflow access**

5. **Document the authentication requirements**

## Migration Plan

1. **Phase 1**: Add warning logs for unauthenticated access
2. **Phase 2**: Require auth for write operations only
3. **Phase 3**: Require auth for all operations
4. **Phase 4**: Implement token-based access control

## Alternative: Separate Public and Private MLflow Instances

- Public MLflow: Contains only public experiments and demo models
- Private MLflow: Requires authentication for all access

This would require updating the SDK to use different endpoints based on the operation.