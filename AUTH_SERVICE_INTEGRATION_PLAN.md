# Auth Service Integration Plan

## Overview

This document outlines how to integrate the hokusai-data-pipeline with the dedicated hokusai-auth-service, keeping useful components from PR #40.

## Components to Keep from PR #40

### 1. Middleware Layer
Keep and modify these files to work with the external auth service:

```python
# src/middleware/auth.py - Modified version
class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, auth_service_url: str = None):
        super().__init__(app)
        self.auth_service_url = auth_service_url or os.getenv(
            "HOKUSAI_AUTH_SERVICE_URL", 
            "https://auth.hokus.ai"
        )
        # Keep cache for performance
        self.cache = redis.Redis(...)
    
    async def validate_api_key(self, api_key: str) -> ValidationResult:
        # Check cache first
        cached = self.cache.get(f"key:validation:{api_key}")
        if cached:
            return ValidationResult(**json.loads(cached))
        
        # Call auth service
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.auth_service_url}/api/v1/keys/validate",
                json={"api_key": api_key}
            )
            if response.status_code == 200:
                result = response.json()
                # Cache for 5 minutes
                self.cache.setex(
                    f"key:validation:{api_key}",
                    300,
                    json.dumps(result)
                )
                return ValidationResult(**result)
```

### 2. SDK Auth Integration
Keep the SDK auth client but modify to use the external service:

```python
# hokusai-ml-platform/src/hokusai/auth/client.py
class AuthClient:
    def __init__(self, api_key: str = None, auth_url: str = None):
        self.api_key = api_key or os.getenv("HOKUSAI_API_KEY")
        self.auth_url = auth_url or os.getenv(
            "HOKUSAI_AUTH_SERVICE_URL",
            "https://auth.hokus.ai"
        )
    
    def validate(self) -> bool:
        """Validate API key with auth service."""
        response = requests.post(
            f"{self.auth_url}/api/v1/keys/validate",
            json={"api_key": self.api_key}
        )
        return response.status_code == 200
```

### 3. Rate Limiting Middleware
Keep as-is - local rate limiting is still useful:
- `src/middleware/rate_limiter.py`

### 4. CLI Commands
Adapt to use the auth service API:

```python
# src/cli/auth.py
@click.command()
@click.option("--name", required=True, help="Name for the API key")
def create_key(name: str):
    """Create a new API key via auth service."""
    admin_token = os.getenv("HOKUSAI_ADMIN_TOKEN")
    if not admin_token:
        click.echo("Error: HOKUSAI_ADMIN_TOKEN required")
        return
    
    response = requests.post(
        f"{AUTH_SERVICE_URL}/api/v1/keys",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": name,
            "service_id": "ml-platform",
            "environment": "production",
            "scopes": ["model:read", "model:write", "mlflow:access"]
        }
    )
```

## Components to Remove

1. **Database Models & Operations**
   - `src/database/models.py` - API key tables
   - `src/database/operations.py` - API key operations
   - `scripts/create_api_key_tables.sql`
   - `scripts/migrate_api_keys.py`

2. **Local Auth Service**
   - `src/auth/api_key_service.py`
   - `src/api/auth.py` - API endpoints

3. **Database Tests**
   - `tests/unit/test_auth/test_api_key_database.py`
   - `tests/unit/test_auth/test_api_key_service.py`

## Integration Steps

1. **Environment Configuration**
   ```bash
   # Add to .env
   HOKUSAI_AUTH_SERVICE_URL=https://auth.hokus.ai
   HOKUSAI_ADMIN_TOKEN=<admin-token-for-cli>
   ```

2. **Update Middleware**
   - Modify `APIKeyAuthMiddleware` to call auth service
   - Keep Redis caching for performance
   - Add retry logic for auth service calls

3. **Update SDK**
   - Modify `AuthClient` to use external service
   - Keep the transparent auth in `ModelRegistry`
   - Update configuration handling

4. **Update CLI**
   - Modify all CLI commands to use auth service API
   - Require admin token for key management
   - Keep user-friendly interface

5. **Update Tests**
   - Mock auth service responses
   - Remove database-specific tests
   - Add integration tests with auth service

## Benefits of This Approach

1. **Centralized Auth**: Single source of truth for all Hokusai services
2. **Keep Good UX**: SDK and CLI remain user-friendly
3. **Performance**: Local caching prevents auth service overload
4. **Maintainability**: Less code to maintain in data-pipeline
5. **Scalability**: Auth service can scale independently

## Migration Path

1. Deploy auth service first
2. Update data-pipeline to use auth service (keep backward compatibility)
3. Migrate existing API keys to auth service
4. Remove local auth components
5. Update documentation

## Configuration for Different Environments

```python
# Development
HOKUSAI_AUTH_SERVICE_URL=http://localhost:8000
HOKUSAI_API_KEY=hok_dev_...

# Staging
HOKUSAI_AUTH_SERVICE_URL=https://auth-staging.hokus.ai
HOKUSAI_API_KEY=hok_test_...

# Production
HOKUSAI_AUTH_SERVICE_URL=https://auth.hokus.ai
HOKUSAI_API_KEY=hok_live_...
```