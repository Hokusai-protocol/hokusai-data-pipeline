#!/bin/bash
#
# Generate mTLS certificates for Hokusai MLflow internal communication
#
# This script creates:
# - CA certificate and key
# - Server certificate and key for MLflow service
# - Client certificate and key for API service
#
# Usage:
#   ./scripts/generate_mtls_certs.sh [environment]
#
# Arguments:
#   environment: development|staging|production (default: development)
#

set -e

# Configuration
ENVIRONMENT="${1:-development}"
CERT_DIR="./certs/${ENVIRONMENT}"
VALIDITY_DAYS=365

# For production, use shorter validity (90 days recommended for rotation)
if [ "$ENVIRONMENT" = "production" ]; then
    VALIDITY_DAYS=90
fi

echo "Generating mTLS certificates for ${ENVIRONMENT} environment"
echo "Certificate validity: ${VALIDITY_DAYS} days"
echo "Output directory: ${CERT_DIR}"
echo

# Create certificate directory
mkdir -p "${CERT_DIR}"

# Generate CA certificate
echo "📜 Generating CA certificate..."
openssl req -x509 -newkey rsa:4096 -days ${VALIDITY_DAYS} \
  -keyout "${CERT_DIR}/ca-key.pem" \
  -out "${CERT_DIR}/ca-cert.pem" \
  -subj "/CN=Hokusai MLflow CA (${ENVIRONMENT})" \
  -nodes

# Generate server certificate for MLflow
echo "🖥️  Generating MLflow server certificate..."
openssl req -newkey rsa:4096 \
  -keyout "${CERT_DIR}/server-key.pem" \
  -out "${CERT_DIR}/server-req.pem" \
  -subj "/CN=mlflow.hokusai-${ENVIRONMENT}.local" \
  -nodes

openssl x509 -req -in "${CERT_DIR}/server-req.pem" \
  -days ${VALIDITY_DAYS} \
  -CA "${CERT_DIR}/ca-cert.pem" \
  -CAkey "${CERT_DIR}/ca-key.pem" \
  -CAcreateserial \
  -out "${CERT_DIR}/server-cert.pem"

# Generate client certificate for API service
echo "💻 Generating API client certificate..."
openssl req -newkey rsa:4096 \
  -keyout "${CERT_DIR}/client-key.pem" \
  -out "${CERT_DIR}/client-req.pem" \
  -subj "/CN=hokusai-api-client-${ENVIRONMENT}" \
  -nodes

openssl x509 -req -in "${CERT_DIR}/client-req.pem" \
  -days ${VALIDITY_DAYS} \
  -CA "${CERT_DIR}/ca-cert.pem" \
  -CAkey "${CERT_DIR}/ca-key.pem" \
  -CAcreateserial \
  -out "${CERT_DIR}/client-cert.pem"

# Set restrictive permissions on private keys
echo "🔒 Setting restrictive permissions on private keys..."
chmod 600 "${CERT_DIR}"/*-key.pem

# Clean up certificate requests
echo "🧹 Cleaning up temporary files..."
rm -f "${CERT_DIR}"/*.pem.srl
rm -f "${CERT_DIR}"/*-req.pem

# Display certificate information
echo
echo "✅ Certificates generated successfully!"
echo
echo "Certificate files:"
echo "  CA Certificate:     ${CERT_DIR}/ca-cert.pem"
echo "  CA Key:             ${CERT_DIR}/ca-key.pem"
echo "  Server Certificate: ${CERT_DIR}/server-cert.pem"
echo "  Server Key:         ${CERT_DIR}/server-key.pem"
echo "  Client Certificate: ${CERT_DIR}/client-cert.pem"
echo "  Client Key:         ${CERT_DIR}/client-key.pem"
echo
echo "Next steps:"
echo "1. Upload certificates to AWS Secrets Manager:"
echo "   aws secretsmanager create-secret --name hokusai/${ENVIRONMENT}/mlflow/ca-cert \\"
echo "     --secret-string file://${CERT_DIR}/ca-cert.pem"
echo
echo "   aws secretsmanager create-secret --name hokusai/${ENVIRONMENT}/mlflow/server-cert \\"
echo "     --secret-string file://${CERT_DIR}/server-cert.pem"
echo
echo "   aws secretsmanager create-secret --name hokusai/${ENVIRONMENT}/mlflow/server-key \\"
echo "     --secret-string file://${CERT_DIR}/server-key.pem"
echo
echo "   aws secretsmanager create-secret --name hokusai/${ENVIRONMENT}/mlflow/client-cert \\"
echo "     --secret-string file://${CERT_DIR}/client-cert.pem"
echo
echo "   aws secretsmanager create-secret --name hokusai/${ENVIRONMENT}/mlflow/client-key \\"
echo "     --secret-string file://${CERT_DIR}/client-key.pem"
echo
echo "2. Update infrastructure to grant ECS tasks access to secrets"
echo "3. Deploy updated MLflow and API services"
echo
echo "⚠️  IMPORTANT: Keep private keys secure and never commit them to version control!"
echo "   Add ${CERT_DIR}/ to .gitignore if not already present"
