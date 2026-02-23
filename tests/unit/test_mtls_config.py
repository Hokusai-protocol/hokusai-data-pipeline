"""Tests for mTLS certificate configuration and management."""

import os
import tempfile
from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.utils.mlflow_config import configure_internal_mtls


class TestMTLSConfiguration:
    """Test mTLS certificate configuration for internal MLflow communication."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.mock_ca_cert = "-----BEGIN CERTIFICATE-----\nMOCK_CA_CERT\n-----END CERTIFICATE-----"
        self.mock_client_cert = (
            "-----BEGIN CERTIFICATE-----\nMOCK_CLIENT_CERT\n-----END CERTIFICATE-----"
        )
        self.mock_client_key = (
            "-----BEGIN PRIVATE KEY-----\nMOCK_CLIENT_KEY\n-----END PRIVATE KEY-----"
        )

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch.dict("os.environ", {"ENVIRONMENT": "development"}, clear=True)
    @patch("src.utils.mlflow_config.logger")
    def test_mtls_not_configured_in_development(self, mock_logger):
        """Test that mTLS is not configured in development environment."""
        configure_internal_mtls()

        mock_logger.info.assert_called_with(
            "Development mode: SSL verification disabled for self-signed certificates"
        )

        # Verify environment variables were not set
        assert "MLFLOW_TRACKING_CLIENT_CERT_PATH" not in os.environ
        assert "MLFLOW_TRACKING_CLIENT_KEY_PATH" not in os.environ
        assert "MLFLOW_TRACKING_SERVER_CERT_PATH" not in os.environ

    @patch.dict("os.environ", {"ENVIRONMENT": "staging"}, clear=True)
    @patch("boto3.client")
    @patch("src.utils.mlflow_config.logger")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.chmod")
    @patch("os.makedirs")
    def test_mtls_configured_in_staging(
        self, mock_makedirs, mock_chmod, mock_file, mock_logger, mock_boto3_client
    ):
        """Test that mTLS is configured properly in staging environment."""
        # Mock AWS Secrets Manager responses
        mock_secrets_client = MagicMock()
        mock_boto3_client.return_value = mock_secrets_client

        mock_secrets_client.get_secret_value.side_effect = [
            {"SecretString": self.mock_client_cert},
            {"SecretString": self.mock_client_key},
            {"SecretString": self.mock_ca_cert},
        ]

        # Configure mTLS
        configure_internal_mtls()

        # Verify boto3 client was created
        mock_boto3_client.assert_called_once_with("secretsmanager", region_name="us-east-1")

        # Verify secrets were retrieved
        assert mock_secrets_client.get_secret_value.call_count == 3
        mock_secrets_client.get_secret_value.assert_any_call(
            SecretId="hokusai/staging/mlflow/client-cert"
        )
        mock_secrets_client.get_secret_value.assert_any_call(
            SecretId="hokusai/staging/mlflow/client-key"
        )
        mock_secrets_client.get_secret_value.assert_any_call(
            SecretId="hokusai/staging/mlflow/ca-cert"
        )

        # Verify directory was created
        mock_makedirs.assert_called_once_with("/tmp/mlflow-certs", exist_ok=True)

        # Verify chmod was called on the private key
        mock_chmod.assert_called_once_with("/tmp/mlflow-certs/client.key", 0o600)

        # Verify certificates were written to files
        assert mock_file.call_count == 3

        # Verify logging
        mock_logger.info.assert_any_call(
            "Configured mTLS for internal MLflow communication "
            "(TLS verification disabled for .local domains, client cert authentication enabled)"
        )

    @patch.dict("os.environ", {"ENVIRONMENT": "production"}, clear=True)
    @patch("boto3.client")
    @patch("src.utils.mlflow_config.logger")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.chmod")
    @patch("os.makedirs")
    def test_mtls_configured_in_production(
        self, mock_makedirs, mock_chmod, mock_file, mock_logger, mock_boto3_client
    ):
        """Test that mTLS is configured properly in production environment."""
        # Mock AWS Secrets Manager responses
        mock_secrets_client = MagicMock()
        mock_boto3_client.return_value = mock_secrets_client

        mock_secrets_client.get_secret_value.side_effect = [
            {"SecretString": self.mock_client_cert},
            {"SecretString": self.mock_client_key},
            {"SecretString": self.mock_ca_cert},
        ]

        # Configure mTLS
        configure_internal_mtls()

        # Verify secrets were retrieved with correct IDs
        mock_secrets_client.get_secret_value.assert_any_call(
            SecretId="hokusai/production/mlflow/client-cert"
        )
        mock_secrets_client.get_secret_value.assert_any_call(
            SecretId="hokusai/production/mlflow/client-key"
        )
        mock_secrets_client.get_secret_value.assert_any_call(
            SecretId="hokusai/production/mlflow/ca-cert"
        )

    @patch.dict("os.environ", {"ENVIRONMENT": "staging"}, clear=True)
    @patch("boto3.client")
    @patch("src.utils.mlflow_config.logger")
    def test_mtls_handles_missing_certificates(self, mock_logger, mock_boto3_client):
        """Test error handling when certificates are missing from Secrets Manager."""
        # Mock AWS Secrets Manager to raise error
        mock_secrets_client = MagicMock()
        mock_boto3_client.return_value = mock_secrets_client

        mock_secrets_client.get_secret_value.side_effect = Exception("Secret not found")

        # Configure mTLS should raise exception
        with pytest.raises(Exception, match="Secret not found"):
            configure_internal_mtls()

    @patch.dict("os.environ", {"ENVIRONMENT": "staging"}, clear=True)
    @patch("boto3.client")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.chmod")
    @patch("os.makedirs")
    def test_mtls_sets_environment_variables(
        self, mock_makedirs, mock_chmod, mock_file, mock_boto3_client
    ):
        """Test that mTLS configuration sets correct environment variables."""
        # Mock AWS Secrets Manager responses
        mock_secrets_client = MagicMock()
        mock_boto3_client.return_value = mock_secrets_client

        mock_secrets_client.get_secret_value.side_effect = [
            {"SecretString": self.mock_client_cert},
            {"SecretString": self.mock_client_key},
            {"SecretString": self.mock_ca_cert},
        ]

        # Configure mTLS
        configure_internal_mtls()

        # Verify environment variables are set
        assert os.environ.get("MLFLOW_TRACKING_CLIENT_CERT_PATH") == "/tmp/mlflow-certs/client.crt"
        assert os.environ.get("MLFLOW_TRACKING_CLIENT_KEY_PATH") == "/tmp/mlflow-certs/client.key"
        assert os.environ.get("MLFLOW_TRACKING_SERVER_CERT_PATH") is None
        assert os.environ.get("MLFLOW_TRACKING_INSECURE_TLS") == "true"

    @patch.dict("os.environ", {"ENVIRONMENT": "staging"}, clear=True)
    @patch("boto3.client")
    @patch("src.utils.mlflow_config.logger")
    def test_mtls_handles_invalid_certificate_data(self, mock_logger, mock_boto3_client):
        """Test error handling when certificate data is invalid."""
        # Mock AWS Secrets Manager to return invalid data
        mock_secrets_client = MagicMock()
        mock_boto3_client.return_value = mock_secrets_client

        # SecretString is missing
        mock_secrets_client.get_secret_value.return_value = {"InvalidKey": "value"}

        # Configure mTLS should raise KeyError
        with pytest.raises(KeyError):
            configure_internal_mtls()

    @patch.dict("os.environ", {"ENVIRONMENT": "staging"}, clear=True)
    @patch("boto3.client")
    @patch("builtins.open", side_effect=OSError("Permission denied"))
    @patch("os.makedirs")
    def test_mtls_handles_file_write_error(self, mock_makedirs, mock_file, mock_boto3_client):
        """Test error handling when certificate file cannot be written."""
        # Mock AWS Secrets Manager responses
        mock_secrets_client = MagicMock()
        mock_boto3_client.return_value = mock_secrets_client

        mock_secrets_client.get_secret_value.side_effect = [
            {"SecretString": self.mock_client_cert},
            {"SecretString": self.mock_client_key},
            {"SecretString": self.mock_ca_cert},
        ]

        # Configure mTLS should raise OSError
        with pytest.raises(OSError, match="Permission denied"):
            configure_internal_mtls()

    @patch.dict("os.environ", {"ENVIRONMENT": "staging"}, clear=True)
    @patch("boto3.client")
    @patch("src.utils.mlflow_config.logger")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.chmod")
    @patch("os.makedirs")
    def test_mtls_certificate_directory_creation(
        self, mock_makedirs, mock_chmod, mock_file, mock_logger, mock_boto3_client
    ):
        """Test that certificate directory is created with correct permissions."""
        # Mock AWS Secrets Manager responses
        mock_secrets_client = MagicMock()
        mock_boto3_client.return_value = mock_secrets_client

        mock_secrets_client.get_secret_value.side_effect = [
            {"SecretString": self.mock_client_cert},
            {"SecretString": self.mock_client_key},
            {"SecretString": self.mock_ca_cert},
        ]

        # Configure mTLS
        configure_internal_mtls()

        # Verify directory was created with exist_ok=True
        mock_makedirs.assert_called_once_with("/tmp/mlflow-certs", exist_ok=True)

    @patch.dict("os.environ", {"ENVIRONMENT": ""}, clear=True)
    @patch("src.utils.mlflow_config.logger")
    def test_mtls_not_configured_when_environment_empty(self, mock_logger):
        """Test that mTLS is not configured when ENVIRONMENT is empty."""
        configure_internal_mtls()

        # Empty ENVIRONMENT now results in no-op (not development fallback branch)
        mock_logger.info.assert_not_called()

    @patch.dict("os.environ", {}, clear=True)
    @patch("src.utils.mlflow_config.logger")
    def test_mtls_not_configured_when_environment_missing(self, mock_logger):
        """Test that mTLS is not configured when ENVIRONMENT is not set."""
        configure_internal_mtls()

        mock_logger.info.assert_called_with(
            "Development mode: SSL verification disabled for self-signed certificates"
        )
