#!/bin/bash
set -e

echo "Starting Hokusai API..."

ENVIRONMENT=${ENVIRONMENT:-development}
MLFLOW_MTLS_ENABLED=${MLFLOW_MTLS_ENABLED:-false}
echo "Environment: $ENVIRONMENT"
echo "MLflow mTLS: $MLFLOW_MTLS_ENABLED"

# When mTLS to MLflow is enabled, pull the CA bundle and this service's client
# cert/key from Secrets Manager and expose their paths to the application via
# env vars. The MLflow proxy (src/api/routes/mlflow_proxy_improved.py) reads
# these to configure httpx.
if [ "$MLFLOW_MTLS_ENABLED" = "true" ]; then
    echo "Fetching MLflow client certificates from hokusai/$ENVIRONMENT/mlflow/* ..."

    if ! command -v aws &> /dev/null; then
        echo "Installing AWS CLI..."
        pip install --quiet awscli
    fi

    CERT_DIR="/tmp/api-certs"
    mkdir -p "$CERT_DIR"
    chmod 700 "$CERT_DIR"

    aws secretsmanager get-secret-value \
        --secret-id "hokusai/$ENVIRONMENT/mlflow/ca-cert" \
        --region us-east-1 \
        --query 'SecretString' \
        --output text > "$CERT_DIR/ca.crt"

    aws secretsmanager get-secret-value \
        --secret-id "hokusai/$ENVIRONMENT/mlflow/client-cert" \
        --region us-east-1 \
        --query 'SecretString' \
        --output text > "$CERT_DIR/client.crt"

    aws secretsmanager get-secret-value \
        --secret-id "hokusai/$ENVIRONMENT/mlflow/client-key" \
        --region us-east-1 \
        --query 'SecretString' \
        --output text > "$CERT_DIR/client.key"

    chmod 644 "$CERT_DIR/ca.crt"
    chmod 644 "$CERT_DIR/client.crt"
    chmod 600 "$CERT_DIR/client.key"

    export MLFLOW_CA_BUNDLE_PATH="$CERT_DIR/ca.crt"
    export MLFLOW_CLIENT_CERT_PATH="$CERT_DIR/client.crt"
    export MLFLOW_CLIENT_KEY_PATH="$CERT_DIR/client.key"

    echo "MLflow client certificates loaded"
else
    echo "MLflow mTLS disabled - API will attempt plain-HTTP/default-verify calls"
fi

exec "$@"
