#!/bin/bash
set -e

echo "Starting MLflow server with mTLS configuration..."

# Check environment
ENVIRONMENT=${ENVIRONMENT:-development}
echo "Environment: $ENVIRONMENT"

# Configure mTLS for staging/production
if [ "$ENVIRONMENT" = "staging" ] || [ "$ENVIRONMENT" = "production" ]; then
    echo "Configuring mTLS for $ENVIRONMENT environment..."

    # Install AWS CLI if not present
    if ! command -v aws &> /dev/null; then
        echo "Installing AWS CLI..."
        pip install --quiet awscli
    fi

    # Create certificate directory
    CERT_DIR="/tmp/mlflow-certs"
    mkdir -p "$CERT_DIR"
    chmod 700 "$CERT_DIR"

    echo "Retrieving certificates from AWS Secrets Manager..."

    # Retrieve certificates from Secrets Manager
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

    # Set restrictive permissions
    chmod 644 "$CERT_DIR/ca.crt"
    chmod 644 "$CERT_DIR/server.crt"
    chmod 600 "$CERT_DIR/server.key"

    echo "Certificates loaded successfully"

    # Build Uvicorn SSL options for mTLS
    # --ssl-cert-reqs=1 means CERT_OPTIONAL (client cert requested but not required)
    # This allows ALB health checks (no cert) and API authentication (with cert)
    UVICORN_SSL_OPTS="--ssl-keyfile=$CERT_DIR/server.key --ssl-certfile=$CERT_DIR/server.crt --ssl-ca-certs=$CERT_DIR/ca.crt --ssl-cert-reqs=1"

    echo "Starting MLflow server with mTLS enabled..."
else
    echo "Development environment - mTLS disabled"
    UVICORN_SSL_OPTS=""
fi

# Start MLflow server
# In staging/production: uses Uvicorn with mTLS
# In development: uses Uvicorn without TLS
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
