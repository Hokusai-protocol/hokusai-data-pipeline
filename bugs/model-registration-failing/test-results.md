# Hypothesis Testing Results

## Test Session Information
- Date: 2025-08-19
- Tester: Bug Investigation Workflow
- Environment: hokusai-development (us-east-1)

---

## Hypothesis 1: ALB Routing Rules Missing/Misconfigured
**Status**: PARTIALLY CONFIRMED
**Test Start Time**: 2025-08-19

### Test 1.1: Check ALB Configuration
- Registry ALB exists and is active: hokusai-registry-development
- HTTPS listener configured with routing rules:
  - /mlflow/* → MLflow target group (1 healthy, 1 unhealthy target)
  - /health → API target group (1 healthy, 1 initializing)
  - /api/mlflow/* → API target group
  - /api/* → API target group

### Test 1.2: Endpoint Accessibility
- https://registry.hokus.ai/mlflow/ → **200 OK** (MLflow UI works!)
- https://registry.hokus.ai/health → **504 Gateway Timeout**
- https://registry.hokus.ai/api/mlflow/health → **504 Gateway Timeout**
- https://registry.hokus.ai/api/2.0/mlflow/experiments/list → **504 Gateway Timeout**

**Finding**: MLflow service is accessible but API proxy endpoints timeout

---

## Hypothesis 2: MLflow Service Not Running or Unhealthy
**Status**: REJECTED
**Test Completed**: 2025-08-19

### Test 2.1: ECS Service Status
- MLflow service: 1/1 running (healthy)
- API service: **0/1 running** (CRITICAL FINDING)

### Test 2.2: Task Failure Analysis
- API service tasks repeatedly exiting with: "Essential container in task exited"
- Logs show Python syntax error in startup:
```
File "/app/src/services/model_registry.py", line 26
    def __init__(self, tracking_uri: str = "http://10.0.1.88:5000"  # TEMPORARY: Direct IP until service discovery fixed) -> None:
                ^
SyntaxError: '(' was never closed
```

**ROOT CAUSE IDENTIFIED**: API service has a syntax error preventing startup