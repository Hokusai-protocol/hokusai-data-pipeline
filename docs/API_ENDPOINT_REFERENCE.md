# Hokusai API Endpoint Reference

This document provides a comprehensive reference for all available API endpoints in the Hokusai MLOps platform.

## Base URLs

- **Production**: `https://registry.hokus.ai/api`
- **Local Development**: `http://localhost:8001`

## Authentication

All API endpoints (except health checks and documentation) require authentication using API keys.

### Authentication Methods

1. **Authorization Header (Recommended)**
   ```bash
   Authorization: Bearer hk_live_your_api_key_here
   # or
   Authorization: ApiKey hk_live_your_api_key_here
   ```

2. **X-API-Key Header**
   ```bash
   X-API-Key: hk_live_your_api_key_here
   ```

3. **Query Parameter** (Not recommended for production)
   ```bash
   GET /endpoint?api_key=hk_live_your_api_key_here
   ```

## Core API Endpoints

### Health Check Endpoints

These endpoints do not require authentication and are used for monitoring service health.

#### `GET /health`
Overall service health status.

**Response:**
```json
{
  "status": "healthy|degraded|unhealthy",
  "version": "1.0.0",
  "services": {
    "mlflow": "healthy",
    "postgres": "healthy",
    "redis": "healthy|disabled",
    "message_queue": "healthy"
  },
  "timestamp": "2025-01-07T10:30:00Z"
}
```

#### `GET /ready`
Service readiness check for load balancer health checks.

**Response (200 OK):**
```json
{
  "ready": true,
  "can_serve_traffic": true,
  "checks": [
    {
      "name": "database",
      "passed": true,
      "error": null,
      "critical": true
    }
  ],
  "degraded_mode": false
}
```

#### `GET /live`
Basic liveness check.

**Response:**
```json
{
  "alive": true,
  "uptime": 3600,
  "memory_usage_mb": 256.5
}
```

#### `GET /version`
Version information.

**Response:**
```json
{
  "version": "1.0.0",
  "build_date": "2025-01-01",
  "git_commit": "abc123",
  "api_version": "v1"
}
```

#### `GET /metrics`
Prometheus-style metrics for monitoring.

**Response:** Plain text metrics in Prometheus format.

### Model Management Endpoints

All model endpoints require authentication.

#### `GET /models/`
List all registered models.

**Query Parameters:**
- `name` (string, optional): Filter models by name

**Response:**
```json
{
  "models": [
    {
      "name": "customer-classifier",
      "version": "1",
      "status": "READY",
      "created_at": 1641820800000,
      "tags": {
        "hokusai_token_id": "cust-class",
        "benchmark_metric": "accuracy",
        "benchmark_value": "0.85"
      }
    }
  ]
}
```

#### `GET /models/{model_name}/{version}`
Get specific model details by name and version.

**Response:**
```json
{
  "name": "customer-classifier",
  "version": "1",
  "status": "READY",
  "description": "Customer classification model",
  "tags": {
    "hokusai_token_id": "cust-class",
    "benchmark_metric": "accuracy"
  }
}
```

#### `PATCH /models/{model_name}/{version}`
Update model metadata (description, tags).

**Request Body:**
```json
{
  "description": "Updated description",
  "tags": {
    "environment": "production",
    "updated_by": "user123"
  }
}
```

#### `DELETE /models/{model_name}/{version}`
Delete a specific model version.

**Response:**
```json
{
  "message": "Model customer-classifier:1 deleted successfully"
}
```

#### `POST /models/{model_name}/{version}/transition`
Transition model to different stage.

**Request Body:**
```json
{
  "stage": "Production",
  "archive_existing": true
}
```

#### `POST /models/register`
Register a new model.

**Request Body:**
```json
{
  "model_data": "model_uri_or_reference",
  "model_type": "classification",
  "metadata": {
    "accuracy": 0.85,
    "dataset": "customer_data_v2"
  }
}
```

**Response:**
```json
{
  "model_id": "abc123",
  "model_name": "customer-classifier",
  "version": "1",
  "registration_timestamp": "2025-01-07T10:30:00Z"
}
```

#### `GET /models/compare`
Compare two model versions.

**Query Parameters:**
- `model1` (string): First model in format `ModelName:Version`
- `model2` (string): Second model in format `ModelName:Version`

**Response:**
```json
{
  "model1": {
    "name": "customer-classifier",
    "version": "1",
    "accuracy": 0.85
  },
  "model2": {
    "name": "customer-classifier", 
    "version": "2",
    "accuracy": 0.87
  },
  "delta": {
    "accuracy": 0.02
  },
  "recommendation": "Use version 2"
}
```

#### `POST /models/evaluate`
Evaluate model performance on a dataset.

**Request Body:**
```json
{
  "model_name": "customer-classifier",
  "model_version": "1",
  "dataset_path": "/path/to/dataset",
  "metrics": ["accuracy", "precision", "recall", "f1_score"]
}
```

#### `GET /models/{model_name}/{version}/metrics`
Get model metrics (training, validation, production).

**Response:**
```json
{
  "training_metrics": {
    "loss": 0.05,
    "accuracy": 0.95
  },
  "validation_metrics": {
    "loss": 0.07,
    "accuracy": 0.93
  },
  "production_metrics": {
    "latency_ms": 25,
    "throughput_rps": 100
  }
}
```

#### `GET /models/{model_name}/{version}/lineage`
Get model lineage information.

**Response:**
```json
{
  "model": "customer-classifier:1",
  "parents": ["customer-classifier:0"],
  "training_data": ["dataset_v1"],
  "experiments": ["exp_001"]
}
```

#### `GET /models/{model_name}/{version}/download`
Download model artifact file.

**Response:** File download or redirect to download URL.

#### `GET /models/{model_name}/{version}/predictions`
Get model prediction history and statistics.

**Response:**
```json
{
  "total_predictions": 10000,
  "date_range": {
    "start": "2024-01-01",
    "end": "2024-01-31"
  },
  "daily_counts": [
    {
      "date": "2024-01-01",
      "count": 350
    }
  ]
}
```

#### `POST /models/batch`
Perform batch operations on multiple models.

**Request Body:**
```json
{
  "operations": [
    {
      "action": "transition_stage",
      "model": "customer-classifier:1",
      "stage": "Production"
    }
  ]
}
```

#### `GET /models/production`
List all models currently in production.

**Response:**
```json
{
  "models": [
    {
      "name": "customer-classifier",
      "version": "1",
      "stage": "Production",
      "deployed_at": "2025-01-07T10:30:00Z"
    }
  ]
}
```

#### `GET /models/{model_id}/lineage`
Get complete improvement history of a model.

**Response:**
```json
{
  "model_id": "abc123",
  "lineage": [
    {
      "version": "1",
      "metrics": {"accuracy": 0.85},
      "created_at": "2025-01-01T00:00:00Z"
    }
  ],
  "total_versions": 1,
  "latest_version": "1"
}
```

#### `GET /models/contributors/{address}/impact`
Get total impact of a contributor across all models.

**Path Parameters:**
- `address` (string): Ethereum address (0x format)

**Response:**
```json
{
  "address": "0x1234567890123456789012345678901234567890",
  "total_models_improved": 5,
  "total_improvement_score": 0.25,
  "contributions": [
    {
      "model_id": "abc123",
      "improvement_score": 0.05,
      "contributed_at": "2025-01-01T00:00:00Z"
    }
  ],
  "first_contribution": "2024-12-01T00:00:00Z",
  "last_contribution": "2025-01-01T00:00:00Z"
}
```

### DSPy Pipeline Endpoints

DSPy endpoints enable execution of registered DSPy programs.

#### `POST /api/v1/dspy/execute`
Execute a DSPy program with given inputs.

**Request Body:**
```json
{
  "program_id": "email-assistant-v1",
  "inputs": {
    "recipient": "john@example.com",
    "subject": "Meeting Follow-up",
    "context": "Discussed Q4 targets"
  },
  "mode": "normal",
  "timeout": 300
}
```

**Response:**
```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "outputs": {
    "generated_email": "Hi John, ..."
  },
  "error": null,
  "execution_time": 2.5,
  "program_name": "email-assistant-v1",
  "metadata": {}
}
```

#### `POST /api/v1/dspy/execute/batch`
Execute a DSPy program on multiple inputs in batch.

**Request Body:**
```json
{
  "program_id": "email-assistant-v1",
  "inputs_list": [
    {
      "recipient": "john@example.com",
      "subject": "Meeting Follow-up"
    },
    {
      "recipient": "jane@example.com", 
      "subject": "Project Update"
    }
  ]
}
```

**Response:**
```json
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440001",
  "total": 2,
  "successful": 2,
  "failed": 0,
  "results": [
    {
      "execution_id": "550e8400-e29b-41d4-a716-446655440002",
      "success": true,
      "outputs": {...},
      "error": null,
      "execution_time": 2.3,
      "program_name": "email-assistant-v1",
      "metadata": {}
    }
  ]
}
```

#### `GET /api/v1/dspy/programs`
List available DSPy programs.

**Response:**
```json
[
  {
    "program_id": "email-assistant-v1",
    "name": "Email Assistant",
    "version": "1.0.0",
    "signatures": [
      {
        "input_fields": ["recipient", "subject", "context"],
        "output_fields": ["generated_email"]
      }
    ],
    "description": "AI-powered email generation"
  }
]
```

#### `GET /api/v1/dspy/execution/{execution_id}`
Get details of a specific execution.

**Response:** 501 Not Implemented (planned feature)

#### `GET /api/v1/dspy/stats`
Get execution statistics for the DSPy pipeline executor.

**Response:**
```json
{
  "statistics": {
    "total_executions": 1000,
    "success_rate": 0.95,
    "average_execution_time": 2.3
  },
  "cache_enabled": true,
  "mlflow_tracking": true
}
```

#### `POST /api/v1/dspy/cache/clear`
Clear the DSPy program cache.

**Response:**
```json
{
  "message": "Cache cleared successfully"
}
```

#### `GET /api/v1/dspy/health`
Check health of DSPy executor service.

**Response:**
```json
{
  "status": "healthy",
  "total_executions": 1000,
  "success_rate": 0.95
}
```

## MLflow Proxy Endpoints

All MLflow endpoints are proxied through the Hokusai API with authentication. The proxy automatically translates paths and handles authentication.

### MLflow API Structure

MLflow endpoints are available at `/mlflow/*` and are proxied to the internal MLflow server.

#### Core MLflow Endpoints

**Experiments:**
- `GET /mlflow/api/2.0/mlflow/experiments/search` - List experiments
- `POST /mlflow/api/2.0/mlflow/experiments/create` - Create experiment
- `GET /mlflow/api/2.0/mlflow/experiments/get` - Get experiment details

**Runs:**
- `POST /mlflow/api/2.0/mlflow/runs/create` - Create a new run
- `POST /mlflow/api/2.0/mlflow/runs/update` - Update run status
- `POST /mlflow/api/2.0/mlflow/runs/log-metric` - Log metrics
- `POST /mlflow/api/2.0/mlflow/runs/log-parameter` - Log parameters

**Models:**
- `POST /mlflow/api/2.0/mlflow/registered-models/create` - Register model
- `GET /mlflow/api/2.0/mlflow/registered-models/search` - Search models
- `POST /mlflow/api/2.0/mlflow/model-versions/create` - Create version

**Artifacts:**
- `GET /mlflow/api/2.0/mlflow-artifacts/artifacts/*` - Download artifacts
- `PUT /mlflow/api/2.0/mlflow-artifacts/artifacts/*` - Upload artifacts

### MLflow Health Check Endpoints

#### `GET /mlflow/health/mlflow`
Check if MLflow server is accessible with detailed diagnostics.

**Response:**
```json
{
  "status": "healthy|unhealthy",
  "mlflow_server": "http://mlflow.hokusai-development.local:5000",
  "checks": {
    "connectivity": {
      "status": "healthy",
      "message": "MLflow server is reachable"
    },
    "experiments_api": {
      "status": "healthy",
      "message": "Experiments API is functional"
    },
    "artifacts_api": {
      "status": "healthy",
      "message": "Artifact API is accessible"
    }
  }
}
```

#### `GET /mlflow/health/mlflow/detailed`
Perform comprehensive MLflow health checks including all API endpoints.

**Response:**
```json
{
  "mlflow_server": "http://mlflow.hokusai-development.local:5000",
  "timestamp": "Tue Jan  7 10:30:00 UTC 2025",
  "environment": {
    "MLFLOW_SERVER_URL": "http://mlflow.hokusai-development.local:5000",
    "MLFLOW_SERVE_ARTIFACTS": "true",
    "PROXY_DEBUG": false
  },
  "tests": [
    {
      "endpoint": "experiments_list",
      "url": "http://mlflow.hokusai-development.local:5000/api/2.0/mlflow/experiments/search",
      "status_code": 200,
      "success": true,
      "response_time_ms": 45.2
    }
  ],
  "overall_health": true
}
```

### Additional MLflow Health Endpoints

#### `GET /api/health/mlflow`
MLflow health check accessible at `/api/health/mlflow`.

#### `GET /api/health/mlflow/detailed`
Detailed MLflow health check accessible at `/api/health/mlflow/detailed`.

#### `GET /api/health/mlflow/connectivity`
Simple connectivity check for MLflow server.

**Response:**
```json
{
  "status": "connected|timeout|error",
  "mlflow_server": "http://mlflow.hokusai-development.local:5000",
  "response_code": 200,
  "response_time_ms": 45.2
}
```

### Enhanced Health Check Endpoints

#### `GET /health/mlflow`
Get detailed MLflow connection status and circuit breaker state.

**Response (200 OK):**
```json
{
  "connected": true,
  "circuit_breaker_state": "CLOSED",
  "timestamp": "2025-01-07T10:30:00Z"
}
```

**Response (503 Service Unavailable):**
```json
{
  "connected": false,
  "circuit_breaker_state": "OPEN",
  "error": "MLflow server unavailable",
  "timestamp": "2025-01-07T10:30:00Z"
}
```

#### `POST /health/mlflow/reset`
Manually reset the MLflow circuit breaker.

**Response:**
```json
{
  "message": "Circuit breaker reset successfully",
  "timestamp": "2025-01-07T10:30:00Z",
  "reset_by": "manual_api_call"
}
```

#### `GET /health/status`
Get comprehensive service status for monitoring and diagnostics.

**Response:**
```json
{
  "timestamp": "2025-01-07T10:30:00Z",
  "api_version": "1.0.0",
  "service_name": "hokusai-registry",
  "overall_health": "healthy",
  "services": {
    "mlflow": "healthy",
    "postgres": "healthy",
    "redis": "healthy"
  },
  "mlflow": {
    "status": {
      "connected": true,
      "circuit_breaker_state": "CLOSED"
    },
    "circuit_breaker": {
      "state": "CLOSED",
      "failure_count": 0,
      "last_failure_time": null
    }
  },
  "system_info": {
    "cpu_percent": 15.2,
    "memory_percent": 45.8
  },
  "uptime_seconds": 3600,
  "environment": "development"
}
```

## Error Responses

All endpoints return consistent error responses:

### Authentication Errors

**401 Unauthorized:**
```json
{
  "detail": "API key required"
}
```

```json
{
  "detail": "Invalid or expired API key"
}
```

### Rate Limiting Errors

**429 Too Many Requests:**
```json
{
  "detail": "Rate limit exceeded"
}
```

### Validation Errors

**422 Unprocessable Entity:**
```json
{
  "detail": [
    {
      "loc": ["body", "model_type"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Not Found Errors

**404 Not Found:**
```json
{
  "detail": "Model not found: customer-classifier:1"
}
```

### Server Errors

**500 Internal Server Error:**
```json
{
  "detail": "Internal server error"
}
```

**502 Bad Gateway:**
```json
{
  "detail": "Failed to connect to MLflow server at http://mlflow.hokusai-development.local:5000"
}
```

**503 Service Unavailable:**
```json
{
  "detail": "Authentication service timeout"
}
```

**504 Gateway Timeout:**
```json
{
  "detail": "MLflow server request timeout after 30s"
}
```

## Rate Limits

- **Default Rate Limit**: 1000 requests per hour per API key
- **Model Registration**: 20 requests per minute per API key
- **Model Lineage**: 100 requests per minute per API key
- **Contributor Impact**: 100 requests per minute per API key

Rate limits can be customized per API key during creation.

## Request/Response Headers

### Standard Request Headers
- `Authorization`: Bearer token or ApiKey authentication
- `X-API-Key`: Alternative authentication method
- `Content-Type`: `application/json` for POST/PATCH requests
- `Accept`: `application/json` (default)

### Standard Response Headers
- `Content-Type`: `application/json` or appropriate MIME type
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Unix timestamp when rate limit resets

## SDK Integration

### Python SDK
```python
from hokusai import setup, ModelRegistry

# Setup with API key
setup(api_key="hk_live_your_api_key_here")

# Use the registry
registry = ModelRegistry("https://registry.hokus.ai/api/mlflow")
models = registry.list_models()
```

### MLflow Client
```python
import mlflow
import os

# Configure MLflow to use Hokusai
os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/mlflow"
os.environ["MLFLOW_TRACKING_TOKEN"] = "hk_live_your_api_key_here"

# Use standard MLflow operations
with mlflow.start_run():
    mlflow.log_metric("accuracy", 0.95)
```

## Status Codes Summary

- **200 OK**: Successful request
- **201 Created**: Resource created successfully
- **400 Bad Request**: Invalid request parameters
- **401 Unauthorized**: Missing or invalid authentication
- **403 Forbidden**: Insufficient permissions
- **404 Not Found**: Resource not found
- **422 Unprocessable Entity**: Validation errors
- **429 Too Many Requests**: Rate limit exceeded
- **500 Internal Server Error**: Server error
- **502 Bad Gateway**: Upstream service error
- **503 Service Unavailable**: Service temporarily unavailable
- **504 Gateway Timeout**: Request timeout

## Notes

1. All timestamps are in ISO 8601 format (UTC)
2. Model names and versions should follow semantic versioning where applicable
3. Ethereum addresses must be in 0x format with 40 hexadecimal characters
4. Large file uploads are chunked and may require multiple requests
5. MLflow endpoints support the full MLflow REST API specification
6. Circuit breaker protection is enabled for MLflow connectivity with automatic recovery