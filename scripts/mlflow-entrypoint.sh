#!/bin/bash
set -e

echo "Starting MLflow server..."

ENVIRONMENT=${ENVIRONMENT:-development}
MLFLOW_MTLS_ENABLED=${MLFLOW_MTLS_ENABLED:-false}
echo "Environment: $ENVIRONMENT"
echo "mTLS: $MLFLOW_MTLS_ENABLED"

# Configure mTLS when explicitly enabled. Historically this branched on
# ENVIRONMENT=staging/production, which forced dev to lie about its environment
# to get certs loaded. The flag decouples the two.
if [ "$MLFLOW_MTLS_ENABLED" = "true" ]; then
    echo "Configuring mTLS from hokusai/$ENVIRONMENT/mlflow/* ..."

    # Install AWS CLI if not present
    if ! command -v aws &> /dev/null; then
        echo "Installing AWS CLI..."
        pip install --quiet awscli
    fi

    CERT_DIR="/tmp/mlflow-certs"
    mkdir -p "$CERT_DIR"
    chmod 700 "$CERT_DIR"

    echo "Retrieving certificates from AWS Secrets Manager..."

    aws secretsmanager get-secret-value \
        --secret-id "hokusai/$ENVIRONMENT/mlflow/ca-cert" \
        --region us-east-1 \
        --query 'SecretString' \
        --output text > "$CERT_DIR/ca.crt"

    aws secretsmanager get-secret-value \
        --secret-id "hokusai/$ENVIRONMENT/mlflow/server-cert" \
        --region us-east-1 \
        --query 'SecretString' \
        --output text > "$CERT_DIR/server.crt"

    aws secretsmanager get-secret-value \
        --secret-id "hokusai/$ENVIRONMENT/mlflow/server-key" \
        --region us-east-1 \
        --query 'SecretString' \
        --output text > "$CERT_DIR/server.key"

    chmod 644 "$CERT_DIR/ca.crt"
    chmod 644 "$CERT_DIR/server.crt"
    chmod 600 "$CERT_DIR/server.key"

    echo "Certificates loaded successfully"

    # --ssl-cert-reqs=1 = CERT_OPTIONAL: client cert requested but not required.
    # Lets ALB health checks (no client cert) and API calls (with client cert)
    # both succeed; authorization is enforced at the application layer.
    UVICORN_SSL_OPTS="--ssl-keyfile=$CERT_DIR/server.key --ssl-certfile=$CERT_DIR/server.crt --ssl-ca-certs=$CERT_DIR/ca.crt --ssl-cert-reqs=1"

    echo "Starting MLflow server with mTLS enabled..."
else
    echo "mTLS disabled - serving plain HTTP"
    UVICORN_SSL_OPTS=""
fi

# Start MLflow server
if [ -n "$UVICORN_SSL_OPTS" ]; then
    exec mlflow server \
        --host 0.0.0.0 \
        --port 5000 \
        --allowed-hosts "*" \
        --static-prefix /mlflow \
        --backend-store-uri "${BACKEND_STORE_URI}" \
        --default-artifact-root "${DEFAULT_ARTIFACT_ROOT}" \
        --serve-artifacts \
        --uvicorn-opts "$UVICORN_SSL_OPTS"
else
    exec mlflow server \
        --host 0.0.0.0 \
        --port 5000 \
        --allowed-hosts "*" \
        --static-prefix /mlflow \
        --backend-store-uri "${BACKEND_STORE_URI}" \
        --default-artifact-root "${DEFAULT_ARTIFACT_ROOT}" \
        --serve-artifacts
fi
