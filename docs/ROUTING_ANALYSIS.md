# Hokusai API Routing Analysis

## Current Routing Configuration

Based on analysis of the Terraform configuration and application code, here is the current routing setup:

### ALB Routing Rules (by priority)

#### HTTP Listener (Port 80)

1. **Priority 40**: `registry.hokus.ai` + `/mlflow/*` → MLflow Target Group
   - Host header: `registry.hokus.ai`
   - Path pattern: `/mlflow`, `/mlflow/*`
   - Target: MLflow service

2. **Priority 50**: `registry.hokus.ai` + `/*` → API Target Group
   - Host header: `registry.hokus.ai`
   - Path pattern: (all paths not matched by higher priority)
   - Target: API service

3. **Priority 100**: `/api*` → API Target Group
   - Path pattern: `/api*` (matches ANY path starting with /api)
   - Target: API service
   - **ISSUE**: This catches ALL /api paths, including `/api/mlflow/*`

4. **Priority 200**: `/mlflow/*` → MLflow Target Group
   - Path pattern: `/mlflow`, `/mlflow/*`
   - Target: MLflow service

#### HTTPS Listener (Port 443) - Same rules as HTTP

### Application-Level Routing

The API application (FastAPI) includes these routes:
- `/health/*` - Health check endpoints
- `/models/*` - Model management endpoints
- `/dspy/*` - DSPy-related endpoints
- `/mlflow/*` - MLflow proxy (forwards to MLflow server)

### The Routing Conflict

The current routing conflict occurs because:

1. **ALB Rule Conflict**: The `/api*` rule at priority 100 catches ALL paths starting with `/api`, including `/api/mlflow/*`
2. **Path Mismatch**: The API proxy is mounted at `/mlflow/*` in the application, but documentation suggests `/api/mlflow/*`
3. **Priority Issue**: The catch-all `/api*` rule has higher priority (100) than the MLflow rule (200)

### Current Workarounds

1. **Direct MLflow Access**: Users can access MLflow via `/mlflow/*` paths
2. **Host-Based Routing**: When using `registry.hokus.ai`, the `/mlflow/*` paths work correctly
3. **Path Translation**: The proxy code translates `api/2.0/mlflow/` to `ajax-api/2.0/mlflow/` for MLflow compatibility

## Routing Map

```
Request Path                          → Target Service
----------------------------------------------------
/api*                                → API Service (Priority 100)
/api/v1/models                       → API Service ✓
/api/v1/health                       → API Service ✓
/api/mlflow/*                        → API Service ✗ (Should go to MLflow)
/mlflow/*                            → MLflow Service (Priority 200) ✓
registry.hokus.ai/mlflow/*           → MLflow Service (Priority 40) ✓
registry.hokus.ai/api/*              → API Service (Priority 50) ✓
registry.hokus.ai/*                  → API Service (Priority 50) ✓
```

## Identified Issues

1. **Primary Conflict**: `/api*` catch-all rule prevents `/api/mlflow/*` from reaching MLflow
2. **Documentation Inconsistency**: Docs mention `/api/mlflow/*` but app uses `/mlflow/*`
3. **No API Versioning**: The `/api*` rule doesn't distinguish between API versions
4. **Missing Route Documentation**: No central documentation of all routing paths

## Recommendations

See ROUTING_SOLUTION.md for proposed solutions.