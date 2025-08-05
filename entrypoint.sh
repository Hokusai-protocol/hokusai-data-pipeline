#!/bin/bash
set -e

echo "Starting MLflow server with artifact serving..."
echo "Backend store URI: ${BACKEND_STORE_URI}"
echo "Default artifact root: ${DEFAULT_ARTIFACT_ROOT}"

exec mlflow server \
    --host 0.0.0.0 \
    --port 5000 \
    --static-prefix /mlflow \
    --backend-store-uri "${BACKEND_STORE_URI}" \
    --default-artifact-root "${DEFAULT_ARTIFACT_ROOT}" \
    --serve-artifacts