# MLflow Artifact Storage Configuration

This document describes the configuration changes made to enable MLflow artifact storage for the Hokusai platform.

## Overview

Model registration was failing with 404 errors when attempting to upload artifacts. This was due to missing artifact storage configuration in the MLflow server and proxy routing.

## Changes Made

### 1. Infrastructure (Already Configured)

The S3 bucket and IAM permissions were already properly configured in Terraform:
- S3 bucket: `hokusai-mlflow-artifacts-${environment}`
- IAM role with S3 read/write permissions
- Bucket versioning and encryption enabled

### 2. MLflow Server Configuration

Updated `Dockerfile.mlflow` to properly configure artifact storage:

```dockerfile
# Create entrypoint script to handle environment variables
RUN echo '#!/bin/bash\n\
exec mlflow server \\\n\
    --host 0.0.0.0 \\\n\
    --port 5000 \\\n\
    --static-prefix /mlflow \\\n\
    --backend-store-uri "${BACKEND_STORE_URI}" \\\n\
    --default-artifact-root "${DEFAULT_ARTIFACT_ROOT}" \\\n\
    --serve-artifacts' > /app/entrypoint.sh && \
    chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
```

Key changes:
- Added `--backend-store-uri` to connect to PostgreSQL
- Added `--default-artifact-root` to specify S3 bucket
- Added `--serve-artifacts` to enable artifact proxy endpoints

### 3. Proxy Routing Updates

Updated `src/api/routes/mlflow_proxy.py` to handle artifact endpoints:

```python
# Handle artifact endpoints - these should be proxied directly
if path.startswith("api/2.0/mlflow-artifacts/"):
    logger.info(f"Proxying artifact request: {path}")
    # Check if MLflow server has artifact serving enabled
    if not os.getenv("MLFLOW_SERVE_ARTIFACTS", "true").lower() == "true":
        raise HTTPException(
            status_code=503,
            detail="Artifact storage is not configured. Please contact your administrator."
        )
```

### 4. Service ID Fixes

Updated all references from `"ml-platform"` to `"platform"` to match the actual API key service registration:

- `src/cli/auth.py` - API key creation and validation
- `src/middleware/auth.py` - Authentication middleware
- `hokusai-ml-platform/src/hokusai/auth/client.py` - SDK authentication

## Environment Variables

The following environment variables are already configured in the ECS task definition:

- `BACKEND_STORE_URI`: PostgreSQL connection string for MLflow metadata
- `DEFAULT_ARTIFACT_ROOT`: S3 bucket path for artifact storage

## Testing

Created integration tests in `tests/integration/test_mlflow_artifact_storage.py` to verify:
- Artifact upload to S3
- Artifact download from S3
- Error handling for artifact operations
- Large file uploads (multipart)

## Deployment Steps

1. **Build and push updated MLflow Docker image**:
   ```bash
   docker build -f Dockerfile.mlflow -t hokusai-mlflow .
   docker tag hokusai-mlflow:latest <ecr-repo>/hokusai-mlflow:latest
   docker push <ecr-repo>/hokusai-mlflow:latest
   ```

2. **Update ECS service** to use the new image version

3. **Verify artifact endpoints** are accessible:
   ```bash
   curl -H "Authorization: Bearer $HOKUSAI_API_KEY" \
     https://registry.hokus.ai/api/mlflow/api/2.0/mlflow-artifacts/artifacts
   ```

## Troubleshooting

### Common Issues

1. **404 on artifact endpoints**
   - Ensure MLflow server is running with `--serve-artifacts` flag
   - Check that proxy is routing `/api/2.0/mlflow-artifacts/*` correctly

2. **403 Forbidden on S3**
   - Verify ECS task role has S3 permissions
   - Check S3 bucket policy allows the task role

3. **Connection refused**
   - Ensure MLflow server is healthy
   - Check security group rules

### Debugging Commands

```bash
# Check MLflow server logs
aws logs tail /ecs/hokusai/mlflow/production --follow

# Verify S3 bucket accessibility from ECS task
aws s3 ls s3://hokusai-mlflow-artifacts-production/

# Test artifact upload locally
export MLFLOW_TRACKING_URI=https://registry.hokus.ai/api/mlflow
export MLFLOW_TRACKING_TOKEN=$HOKUSAI_API_KEY
python test_real_registration.py
```

## Security Considerations

- Artifact access is controlled through the Hokusai API key authentication
- S3 bucket is private with access only through IAM roles
- All artifacts are encrypted at rest using S3 server-side encryption
- Artifact URLs are pre-signed with temporary credentials