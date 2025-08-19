# Authentication Architecture

## Overview
This document describes the authentication and authorization architecture for the Hokusai data pipeline services. Understanding this architecture is CRITICAL for maintaining secure service communication.

## Table of Contents
1. [Service Communication Patterns](#service-communication-patterns)
2. [Authentication Flow](#authentication-flow)
3. [Required Headers](#required-headers)
4. [Service-Specific Auth](#service-specific-auth)
5. [Common Pitfalls](#common-pitfalls)
6. [Troubleshooting](#troubleshooting)

## Service Communication Patterns

### External Client → API Gateway → Services
```mermaid
sequenceDiagram
    participant Client
    participant ALB as ALB/API Gateway
    participant Auth as Auth Service
    participant API as Data Pipeline API
    participant MLflow as MLflow Service
    
    Client->>ALB: Request + Bearer Token
    ALB->>Auth: Validate Token
    Auth-->>ALB: User Context
    ALB->>API: Request + Headers
    API->>MLflow: Internal Request + Auth
    MLflow-->>API: Response
    API-->>Client: Response
```

### Internal Service-to-Service Communication
```mermaid
sequenceDiagram
    participant API as Data Pipeline API
    participant SD as Service Discovery
    participant MLflow as MLflow Service
    
    Note over API: Prepare auth headers
    API->>SD: Resolve mlflow.hokusai-development.local
    SD-->>API: Internal IP
    API->>MLflow: Direct request with auth
    MLflow-->>API: Response
```

## Authentication Flow

### 1. External Request Authentication
All external requests to the Hokusai platform must include a valid JWT token:

```bash
curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
     https://api.hokus.ai/api/v1/models
```

The authentication flow:
1. **Client** sends request with Bearer token to public endpoint
2. **ALB** routes request based on path rules
3. **Auth Service** validates the JWT token
4. **Auth Service** extracts user context and permissions
5. **API Service** receives validated request with auth headers
6. **API Service** performs authorization checks
7. **Response** returned to client

### 2. Internal Service Authentication
Services communicate internally using service discovery with preserved auth context:

```python
# Internal service call example
headers = {
    'Authorization': request.headers.get('Authorization'),  # Preserve from original
    'X-User-ID': request.headers.get('X-User-ID'),
    'X-Request-ID': str(uuid.uuid4()),  # Generate for tracing
}

response = requests.post(
    'http://mlflow.hokusai-development.local:5000/api/2.0/mlflow/experiments/create',
    headers=headers,
    json=data
)
```

## Required Headers

### Core Authentication Headers

| Header | Purpose | Required | Example |
|--------|---------|----------|---------|
| `Authorization` | Bearer token for authentication | Yes | `Bearer eyJhbGciOiJIUzI1NiIs...` |
| `X-User-ID` | User identifier for audit logging | Yes | `user_123456` |
| `X-Request-ID` | Request tracing across services | Yes | `req_uuid4()` |
| `X-Tenant-ID` | Multi-tenancy isolation | If multi-tenant | `tenant_abc` |

### Service-Specific Headers

| Service | Additional Headers | Purpose |
|---------|-------------------|---------|
| MLflow | `MLFLOW_TRACKING_TOKEN` | Alternative to Authorization header |
| S3 Artifacts | `X-Amz-Security-Token` | AWS temporary credentials |
| Metrics | `X-Metrics-Key` | Metrics service API key |

## Service-Specific Auth

### MLflow Service Authentication
MLflow requires authentication for all operations:

```python
# Option 1: Using environment variable
os.environ['MLFLOW_TRACKING_TOKEN'] = get_token()
mlflow.set_tracking_uri('http://mlflow.hokusai-development.local:5000')

# Option 2: Using headers directly
from mlflow.tracking import MlflowClient

client = MlflowClient(
    tracking_uri='http://mlflow.hokusai-development.local:5000',
    registry_uri='http://mlflow.hokusai-development.local:5000'
)
# Note: MLflow client doesn't directly accept headers, 
# so we configure auth through environment or request interceptors
```

### API Proxy Authentication
The API proxy MUST forward all authentication headers:

```python
@app.route('/proxy/<path:path>')
def proxy_request(path):
    # CORRECT: Preserve all headers
    headers = dict(request.headers)
    headers.pop('Host', None)  # Remove only Host header
    
    # Make upstream request
    upstream_url = f"{UPSTREAM_SERVICE}/{path}"
    response = requests.request(
        method=request.method,
        url=upstream_url,
        headers=headers,  # All auth headers preserved!
        data=request.get_data(),
        stream=True
    )
    
    return response.content, response.status_code, dict(response.headers)
```

## Common Pitfalls

### ❌ Pitfall 1: Creating New Headers Dictionary
```python
# WRONG: This strips all auth headers!
headers = {
    'Content-Type': 'application/json'
}
response = requests.post(url, headers=headers)
```

### ✅ Solution 1: Preserve Existing Headers
```python
# CORRECT: Preserve all headers
headers = dict(request.headers)
headers['Content-Type'] = 'application/json'
response = requests.post(url, headers=headers)
```

### ❌ Pitfall 2: Forgetting Auth in Async Operations
```python
# WRONG: Background task without auth context
@celery.task
def process_model(model_id):
    # No auth headers available here!
    mlflow.get_model(model_id)
```

### ✅ Solution 2: Pass Auth Context to Async Tasks
```python
# CORRECT: Pass auth context
@celery.task
def process_model(model_id, auth_token):
    os.environ['MLFLOW_TRACKING_TOKEN'] = auth_token
    mlflow.get_model(model_id)

# When calling:
process_model.delay(model_id, request.headers.get('Authorization'))
```

### ❌ Pitfall 3: Not Handling Auth Errors
```python
# WRONG: Generic error handling
try:
    response = mlflow_client.get_experiment(exp_id)
except Exception as e:
    return {"error": "Failed"}
```

### ✅ Solution 3: Specific Auth Error Handling
```python
# CORRECT: Handle auth errors specifically
try:
    response = mlflow_client.get_experiment(exp_id)
except HTTPError as e:
    if e.response.status_code == 401:
        return {"error": "Authentication failed"}, 401
    elif e.response.status_code == 403:
        return {"error": "Insufficient permissions"}, 403
    raise
```

## Proxy Responsibilities

The API proxy is a critical component that MUST:

1. **Forward ALL authentication headers unchanged**
   - Never strip Authorization headers
   - Preserve X-User-ID for audit trails
   - Maintain X-Request-ID for tracing

2. **Handle both internal and external calls**
   - External: via ALB with full URL
   - Internal: via service discovery with internal DNS

3. **Preserve custom headers**
   - Service-specific headers
   - Tracing headers
   - Tenant isolation headers

4. **Never expose auth tokens in logs**
   - Mask Authorization headers in logs
   - Don't log full request headers
   - Use request IDs for correlation

## Troubleshooting

### Debugging Authentication Issues

1. **Check if headers are present:**
```python
import logging
logging.debug(f"Auth header present: {'Authorization' in request.headers}")
logging.debug(f"User ID: {request.headers.get('X-User-ID', 'MISSING')}")
```

2. **Verify token validity:**
```bash
# Decode JWT token (without verification)
echo $TOKEN | cut -d. -f2 | base64 -d | jq .

# Test token with auth service
curl -H "Authorization: Bearer $TOKEN" \
     https://auth.hokus.ai/api/v1/validate
```

3. **Check service logs:**
```bash
# View API service logs
aws logs tail /ecs/hokusai-api-development --follow

# View MLflow service logs
aws logs tail /ecs/hokusai-mlflow-development --follow

# Check for 401/403 errors
aws logs filter-log-events \
    --log-group-name /ecs/hokusai-api-development \
    --filter-pattern "401"
```

### Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `401 Unauthorized` | Missing or invalid token | Check Authorization header |
| `403 Forbidden` | Valid token but insufficient permissions | Verify user permissions |
| `MLflow authentication failed` | MLflow service can't validate token | Ensure proxy forwards auth headers |
| `Service communication failed` | Internal service can't authenticate | Check service discovery and auth forwarding |

### Testing Authentication

```bash
# Test script location
./scripts/test_auth_flow.sh

# Individual test commands
pytest tests/auth/test_auth_flow.py -v
pytest tests/integration/test_proxy_auth.py -v
python scripts/test_mlflow_connection.py
```

## Security Best Practices

1. **Never log sensitive data:**
   - Mask Authorization headers in logs
   - Don't log user credentials
   - Use structured logging with request IDs

2. **Validate tokens properly:**
   - Check token expiration
   - Verify token signature
   - Validate token issuer

3. **Handle token refresh:**
   - Implement token refresh logic
   - Handle refresh token rotation
   - Clear expired tokens

4. **Audit all access:**
   - Log all authentication attempts
   - Track authorization decisions
   - Monitor for suspicious patterns

## Implementation Examples

### Utility Function for Auth Headers
```python
# src/api/auth_utils.py
def get_auth_headers(request=None):
    """Get authentication headers for service calls."""
    headers = {}
    
    if request:
        # Preserve from incoming request
        if 'Authorization' in request.headers:
            headers['Authorization'] = request.headers['Authorization']
        if 'X-User-ID' in request.headers:
            headers['X-User-ID'] = request.headers['X-User-ID']
    else:
        # Use service account token
        token = os.environ.get('SERVICE_AUTH_TOKEN')
        if token:
            headers['Authorization'] = f'Bearer {token}'
    
    # Always add request ID for tracing
    headers['X-Request-ID'] = str(uuid.uuid4())
    
    return headers
```

### Proxy with Auth Preservation
```python
# src/api/proxy.py
from auth_utils import get_auth_headers

def proxy_to_mlflow(path, request):
    """Proxy requests to MLflow with auth preservation."""
    # Preserve ALL headers
    headers = dict(request.headers)
    headers.pop('Host', None)  # Only remove Host
    
    # Ensure auth headers are present
    if 'Authorization' not in headers:
        return {"error": "Authentication required"}, 401
    
    # Forward to MLflow
    mlflow_url = f"http://mlflow.hokusai-development.local:5000/{path}"
    
    try:
        response = requests.request(
            method=request.method,
            url=mlflow_url,
            headers=headers,
            data=request.get_data(),
            stream=True,
            timeout=30
        )
        
        return response.content, response.status_code, dict(response.headers)
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Proxy failed: {e}")
        return {"error": "Service unavailable"}, 503
```

## Monitoring and Alerts

Set up CloudWatch alarms for:
- Increased 401/403 response rates
- Failed auth service health checks
- Spike in authentication errors
- Token validation latency

```bash
# Example CloudWatch query for auth failures
fields @timestamp, @message
| filter @message like /401|403|Unauthorized|Forbidden/
| stats count() by bin(5m)
```

## References

- [PROXY_CHECKLIST.md](./PROXY_CHECKLIST.md) - Checklist for modifying proxy code
- [ONBOARDING.md](./ONBOARDING.md) - New developer guide
- [WEBHOOK_INTEGRATION_GUIDE.md](./WEBHOOK_INTEGRATION_GUIDE.md) - Webhook auth setup
- AWS Documentation: [ECS Service Discovery](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-discovery.html)
- MLflow Documentation: [Authentication](https://mlflow.org/docs/latest/auth/index.html)