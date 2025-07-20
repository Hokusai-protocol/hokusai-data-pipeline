# Hokusai API Routing Documentation

## Overview

This document describes the routing configuration for the Hokusai API platform, including Application Load Balancer (ALB) rules and application-level routing.

## ALB Routing Rules

The Application Load Balancer routes incoming requests to different target groups based on path patterns and host headers. Rules are evaluated in priority order (lower numbers = higher priority).

### Current Routing Rules (After Fix)

| Priority | Path Pattern | Host Header | Target | Description |
|----------|-------------|-------------|--------|-------------|
| 40 | `/mlflow`, `/mlflow/*` | `registry.hokus.ai` | MLflow | Direct MLflow access for registry.hokus.ai |
| 50 | `/*` | `registry.hokus.ai` | API | All other registry.hokus.ai paths |
| 90 | `/api/mlflow/*` | - | API | MLflow proxy endpoint (NEW) |
| 100 | `/api/v1/*`, `/api/health`, `/api/health/*` | - | API | Versioned API endpoints (UPDATED) |
| 200 | `/mlflow`, `/mlflow/*` | - | MLflow | Direct MLflow access |

### Path Routing Examples

```
Request Path                              → Target Service → Final Destination
--------------------------------------------------------------------------------
/api/v1/dspy/execute                     → API Service    → DSPy endpoint
/api/v1/auth/keys                        → API Service    → Auth endpoint
/api/mlflow/api/2.0/mlflow/experiments   → API Service    → MLflow (via proxy)
/mlflow/api/2.0/mlflow/experiments       → MLflow         → MLflow directly
/models/list                             → API Service    → Models endpoint
/health                                  → API Service    → Health endpoint
registry.hokus.ai/mlflow/*               → MLflow         → MLflow directly
registry.hokus.ai/api/v1/*               → API Service    → API endpoints
```

## Application-Level Routing

The FastAPI application handles routing at the application level:

### Route Prefixes

| Prefix | Router | Description |
|--------|--------|-------------|
| (none) | health | Health check endpoints |
| `/models` | models | Model management API |
| `/api/v1/dspy` | dspy | DSPy execution API |
| `/mlflow` | mlflow_proxy | MLflow proxy (legacy) |
| `/api/mlflow` | mlflow_proxy | MLflow proxy (standard) |

### MLflow Proxy Behavior

The MLflow proxy handles path translation for compatibility:
- Incoming: `/api/mlflow/api/2.0/mlflow/*`
- Translated: `ajax-api/2.0/mlflow/*` (for registry.hokus.ai MLflow instance)
- Forwarded to: MLflow server

## Client Configuration

### Standard MLflow Client (After Fix)
```python
# Standard MLflow configuration
os.environ["MLFLOW_TRACKING_URI"] = "http://registry.hokus.ai/api/mlflow"
os.environ["MLFLOW_TRACKING_TOKEN"] = "hk_live_your_api_key"
```

### Legacy Configuration (Still Supported)
```python
# Direct MLflow access (bypasses API proxy)
os.environ["MLFLOW_TRACKING_URI"] = "http://registry.hokus.ai/mlflow"
```

### Hokusai SDK Configuration
```python
from hokusai import setup
setup(api_key="hk_live_your_api_key")
# SDK automatically configures MLflow tracking URI
```

## Routing Conflict Resolution

### The Problem
- Previous ALB rule: `/api*` → API Service (priority 100)
- This caught ALL paths starting with `/api`, including `/api/mlflow/*`
- MLflow clients expect to use `/api/2.0/mlflow/*` paths

### The Solution
1. Changed ALB rule from `/api*` to specific paths: `/api/v1/*`, `/api/health`, `/api/health/*`
2. Added new ALB rule: `/api/mlflow/*` → API Service (priority 90)
3. Added `/api/mlflow` mount point in FastAPI application
4. Existing proxy handles path translation

### Migration Path
1. **Phase 1**: Deploy routing fixes (both paths work)
2. **Phase 2**: Update documentation to use standard paths
3. **Phase 3**: Monitor and deprecate legacy `/mlflow` paths

## Testing Endpoints

### Health Checks
```bash
# API health
curl http://registry.hokus.ai/health

# MLflow health (via proxy)
curl http://registry.hokus.ai/api/mlflow/health/mlflow

# Direct MLflow health
curl http://registry.hokus.ai/mlflow/health
```

### API Endpoints
```bash
# DSPy API
curl -X POST http://registry.hokus.ai/api/v1/dspy/execute \
  -H "Authorization: Bearer hk_live_your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"program_name": "test", "inputs": {}}'

# Models API
curl http://registry.hokus.ai/models \
  -H "Authorization: Bearer hk_live_your_api_key"
```

### MLflow Endpoints
```bash
# Via API proxy (standard)
curl http://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search \
  -H "Authorization: Bearer hk_live_your_api_key"

# Direct access (legacy)
curl http://registry.hokus.ai/mlflow/ajax-api/2.0/mlflow/experiments/search
```

## Troubleshooting

### 404 Not Found on `/api/mlflow/*`
- **Cause**: Routing fix not yet deployed
- **Workaround**: Use `/mlflow/*` paths instead
- **Fix**: Deploy the routing-fix.tf changes

### 403 Forbidden from MLflow
- **Cause**: Missing or invalid API key
- **Fix**: Ensure `MLFLOW_TRACKING_TOKEN` is set with valid API key

### 502 Bad Gateway
- **Cause**: MLflow server is down or unreachable
- **Check**: MLflow health endpoint
- **Fix**: Verify MLflow service is running

## Future Considerations

1. **API Version 2**: When adding `/api/v2/*`, add to ALB rules
2. **GraphQL**: If adding GraphQL, consider `/api/graphql` path
3. **WebSocket**: May need additional ALB configuration for WebSocket support
4. **Rate Limiting**: Currently applied at application level, consider ALB-level limits