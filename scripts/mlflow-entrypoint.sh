#!/bin/bash
set -e

echo "Starting MLflow server..."

ENVIRONMENT=${ENVIRONMENT:-development}
MLFLOW_MTLS_ENABLED=${MLFLOW_MTLS_ENABLED:-false}
echo "Environment: $ENVIRONMENT"
echo "mTLS: $MLFLOW_MTLS_ENABLED"
MLFLOW_ALLOWED_HOSTS=${MLFLOW_ALLOWED_HOSTS:-"registry.hokus.ai,mlflow.hokusai-development.local,mlflow.hokusai-production.local,localhost,localhost:5000,127.0.0.1,127.0.0.1:5000,mlflow,mlflow:5000"}
echo "Allowed hosts: $MLFLOW_ALLOWED_HOSTS"

# Configure mTLS when explicitly enabled. Historically this branched on
# ENVIRONMENT=staging/production, which forced dev to lie about its environment
# to get certs loaded. The flag decouples the two.
if [ "$MLFLOW_MTLS_ENABLED" = "true" ]; then
    CERT_DIR="/tmp/mlflow-certs"
    preloaded_ca=${MLFLOW_CA_BUNDLE_PATH:-}
    preloaded_cert=${MLFLOW_SERVER_CERT_PATH:-}
    preloaded_key=${MLFLOW_SERVER_KEY_PATH:-}

    if [ -r "$preloaded_ca" ] && [ -r "$preloaded_cert" ] && [ -r "$preloaded_key" ]; then
        echo "Using pre-mounted MLflow server certificates"
        CERT_DIR="$(dirname "$preloaded_cert")"
    else
        echo "Configuring mTLS from hokusai/$ENVIRONMENT/mlflow/* ..."

        # Install AWS CLI if not present
        if ! command -v aws &> /dev/null; then
            echo "Installing AWS CLI..."
            pip install --quiet awscli
        fi

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

        export MLFLOW_CA_BUNDLE_PATH="$CERT_DIR/ca.crt"
        export MLFLOW_SERVER_CERT_PATH="$CERT_DIR/server.crt"
        export MLFLOW_SERVER_KEY_PATH="$CERT_DIR/server.key"
    fi

    echo "Certificates loaded successfully"

    # --ssl-cert-reqs=1 = CERT_OPTIONAL: client cert requested but not required.
    # Lets ALB health checks (no client cert) and API calls (with client cert)
    # both succeed; authorization is enforced at the application layer.
    UVICORN_SSL_OPTS="--ssl-keyfile=${MLFLOW_SERVER_KEY_PATH:-$CERT_DIR/server.key} --ssl-certfile=${MLFLOW_SERVER_CERT_PATH:-$CERT_DIR/server.crt} --ssl-ca-certs=${MLFLOW_CA_BUNDLE_PATH:-$CERT_DIR/ca.crt} --ssl-cert-reqs=1"

    echo "Starting MLflow server with mTLS enabled..."
else
    echo "mTLS disabled - serving plain HTTP"
    UVICORN_SSL_OPTS=""
fi

export _MLFLOW_SERVER_FILE_STORE="${BACKEND_STORE_URI}"
export _MLFLOW_SERVER_ARTIFACT_ROOT="${DEFAULT_ARTIFACT_ROOT}"
export _MLFLOW_SERVER_SERVE_ARTIFACTS="true"
export _MLFLOW_STATIC_PREFIX="/mlflow"
export MLFLOW_SERVER_ALLOWED_HOSTS="$MLFLOW_ALLOWED_HOSTS"
export _MLFLOW_SGI_NAME="uvicorn"

# Start MLflow server through the Hokusai admin gateway. This protects direct
# ALB routes to /mlflow/* even when they bypass the FastAPI proxy service.
if [ -n "$UVICORN_SSL_OPTS" ]; then
    exec uvicorn hokusai_mlflow_admin_gateway:app \
        --host 0.0.0.0 \
        --port 5000 \
        $UVICORN_SSL_OPTS
else
    exec uvicorn hokusai_mlflow_admin_gateway:app \
        --host 0.0.0.0 \
        --port 5000
fi
