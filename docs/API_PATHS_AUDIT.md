# Hokusai API Paths Audit

## Current API Endpoints

Based on analysis of the codebase, here are all the API endpoints currently in use:

### Health Endpoints (no prefix)
- `GET /health` - Main health check
- `GET /ready` - Readiness probe
- `GET /live` - Liveness probe
- `GET /version` - Version information
- `GET /metrics` - Prometheus metrics
- `GET /debug` - Debug information

### Models API (`/models` prefix)
- `GET /models` - List all models
- `GET /models/{model_name}/{version}` - Get specific model
- `POST /models` - Register new model
- `PATCH /models/{model_name}/{version}` - Update model
- `DELETE /models/{model_name}/{version}` - Delete model
- `POST /models/{model_name}/{version}/transition` - Transition model stage
- `GET /models/compare` - Compare models
- `POST /models/evaluate` - Evaluate model
- `GET /models/{model_name}/{version}/metrics` - Get model metrics
- `GET /models/{model_name}/{version}/lineage` - Get model lineage
- `GET /models/{model_name}/{version}/download` - Download model
- `GET /models/{model_name}/{version}/predictions` - Get predictions
- `POST /models/batch` - Batch operations
- `GET /models/production` - List production models

### DSPy API (`/api/v1/dspy` prefix)
- `POST /api/v1/dspy/execute` - Execute DSPy program
- `POST /api/v1/dspy/execute/batch` - Batch execution
- `GET /api/v1/dspy/programs` - List programs
- `GET /api/v1/dspy/execution/{execution_id}` - Get execution details
- `GET /api/v1/dspy/stats` - Get statistics
- `POST /api/v1/dspy/cache/clear` - Clear cache
- `GET /api/v1/dspy/health` - DSPy health check

### Auth API (`/api/v1/auth` prefix - if mounted)
- `POST /api/v1/auth/keys` - Create API key
- `GET /api/v1/auth/keys` - List API keys
- `DELETE /api/v1/auth/keys/{key_id}` - Delete API key
- `POST /api/v1/auth/keys/{key_id}/rotate` - Rotate API key
- `GET /api/v1/auth/keys/{key_id}/usage` - Get key usage stats

### MLflow Proxy (`/mlflow` prefix)
- `/{path:path}` - Proxy all MLflow requests
- `/health/mlflow` - MLflow health check

## ALB Routing Impact

The current ALB rule `/api*` at priority 100 catches:
- ✅ `/api/v1/dspy/*` - Correctly routed to API service
- ✅ `/api/v1/auth/*` - Correctly routed to API service
- ❌ `/api/mlflow/*` - INCORRECTLY routed to API service (should go to MLflow or API proxy)

## Paths Not Behind `/api`
These paths work correctly and are not affected by the routing conflict:
- `/health`, `/ready`, `/live`, `/version`, `/metrics`, `/debug`
- `/models/*`
- `/mlflow/*`

## Recommended ALB Rule Update

Replace the broad `/api*` rule with specific paths:

```hcl
condition {
  path_pattern {
    values = [
      "/api/v1/*",      # Covers all versioned APIs
      "/api/health",    # If we add /api/health endpoint
      "/api/health/*",  # If we add /api/health/* endpoints
    ]
  }
}
```

This would allow `/api/mlflow/*` to be handled by a separate rule.