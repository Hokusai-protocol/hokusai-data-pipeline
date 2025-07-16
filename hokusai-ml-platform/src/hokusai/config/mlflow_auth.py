"""MLflow authentication configuration for Hokusai SDK."""

import os
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import mlflow
from mlflow.tracking import MlflowClient

logger = logging.getLogger(__name__)


class MLflowAuthConfig:
    """Configuration for MLflow authentication."""
    
    def __init__(
        self,
        tracking_uri: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        token: Optional[str] = None,
        insecure_tls: bool = False,
        aws_sigv4: bool = False,
        client_cert_path: Optional[str] = None,
        client_key_path: Optional[str] = None,
        ca_bundle_path: Optional[str] = None
    ):
        """Initialize MLflow authentication configuration.
        
        Args:
            tracking_uri: MLflow tracking server URI
            username: Basic auth username
            password: Basic auth password
            token: Bearer token for authentication
            insecure_tls: Whether to skip TLS verification
            aws_sigv4: Whether to use AWS Signature V4 authentication
            client_cert_path: Path to client certificate for mTLS
            client_key_path: Path to client key for mTLS
            ca_bundle_path: Path to CA bundle for custom CA
        """
        self.tracking_uri = tracking_uri or os.getenv("MLFLOW_TRACKING_URI")
        self.username = username or os.getenv("MLFLOW_TRACKING_USERNAME")
        self.password = password or os.getenv("MLFLOW_TRACKING_PASSWORD")
        self.token = token or os.getenv("MLFLOW_TRACKING_TOKEN")
        self.insecure_tls = insecure_tls or os.getenv("MLFLOW_TRACKING_INSECURE_TLS", "false").lower() == "true"
        self.aws_sigv4 = aws_sigv4 or os.getenv("MLFLOW_TRACKING_AWS_SIGV4", "false").lower() == "true"
        self.client_cert_path = client_cert_path or os.getenv("MLFLOW_TRACKING_CLIENT_CERT_PATH")
        self.client_key_path = client_key_path or os.getenv("MLFLOW_TRACKING_CLIENT_KEY_PATH")
        self.ca_bundle_path = ca_bundle_path or os.getenv("MLFLOW_TRACKING_CA_BUNDLE_PATH")
    
    def configure_environment(self) -> None:
        """Configure environment variables for MLflow authentication."""
        # Set tracking URI
        if self.tracking_uri:
            os.environ["MLFLOW_TRACKING_URI"] = self.tracking_uri
        
        # Basic authentication
        if self.username and self.password:
            os.environ["MLFLOW_TRACKING_USERNAME"] = self.username
            os.environ["MLFLOW_TRACKING_PASSWORD"] = self.password
            logger.info("Configured MLflow basic authentication")
        
        # Token authentication
        if self.token:
            os.environ["MLFLOW_TRACKING_TOKEN"] = self.token
            logger.info("Configured MLflow token authentication")
        
        # TLS settings
        if self.insecure_tls:
            os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
            logger.warning("MLflow TLS verification disabled - not recommended for production")
        
        # AWS Signature V4
        if self.aws_sigv4:
            os.environ["MLFLOW_TRACKING_AWS_SIGV4"] = "true"
            logger.info("Configured MLflow AWS Signature V4 authentication")
        
        # Client certificates
        if self.client_cert_path:
            os.environ["MLFLOW_TRACKING_CLIENT_CERT_PATH"] = self.client_cert_path
        if self.client_key_path:
            os.environ["MLFLOW_TRACKING_CLIENT_KEY_PATH"] = self.client_key_path
        if self.ca_bundle_path:
            os.environ["MLFLOW_TRACKING_CA_BUNDLE_PATH"] = self.ca_bundle_path
        
        if self.client_cert_path or self.ca_bundle_path:
            logger.info("Configured MLflow mTLS authentication")
    
    def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for direct API calls."""
        headers = {}
        
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        elif self.username and self.password:
            import base64
            credentials = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
        
        return headers
    
    def is_remote_tracking(self) -> bool:
        """Check if tracking URI is remote (not local file storage)."""
        if not self.tracking_uri:
            return False
        
        parsed = urlparse(self.tracking_uri)
        return parsed.scheme in ["http", "https"]
    
    def validate_connection(self) -> bool:
        """Validate MLflow connection with current authentication."""
        try:
            client = MlflowClient()
            # Try to list experiments - this will fail if auth is incorrect
            client.search_experiments(max_results=1)
            logger.info("MLflow authentication validated successfully")
            return True
        except Exception as e:
            if "403" in str(e) or "401" in str(e):
                logger.error(f"MLflow authentication failed: {e}")
            else:
                logger.error(f"MLflow connection failed: {e}")
            return False


def setup_mlflow_auth(
    tracking_uri: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    token: Optional[str] = None,
    validate: bool = True,
    **kwargs
) -> MLflowAuthConfig:
    """Setup MLflow authentication.
    
    Args:
        tracking_uri: MLflow tracking server URI
        username: Basic auth username
        password: Basic auth password
        token: Bearer token for authentication
        validate: Whether to validate the connection
        **kwargs: Additional configuration options
    
    Returns:
        MLflowAuthConfig instance
    
    Raises:
        Exception: If validation fails and validate=True
    """
    config = MLflowAuthConfig(
        tracking_uri=tracking_uri,
        username=username,
        password=password,
        token=token,
        **kwargs
    )
    
    # Configure environment
    config.configure_environment()
    
    # Set tracking URI in MLflow
    if config.tracking_uri:
        mlflow.set_tracking_uri(config.tracking_uri)
    
    # Validate if requested
    if validate and config.is_remote_tracking():
        if not config.validate_connection():
            raise Exception("MLflow authentication validation failed")
    
    return config


def get_mlflow_auth_status() -> Dict[str, Any]:
    """Get current MLflow authentication status."""
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "Not configured")
    
    status = {
        "tracking_uri": tracking_uri,
        "auth_type": "none",
        "is_remote": False,
        "is_configured": False
    }
    
    # Check authentication type
    if os.getenv("MLFLOW_TRACKING_TOKEN"):
        status["auth_type"] = "token"
        status["is_configured"] = True
    elif os.getenv("MLFLOW_TRACKING_USERNAME") and os.getenv("MLFLOW_TRACKING_PASSWORD"):
        status["auth_type"] = "basic"
        status["is_configured"] = True
    elif os.getenv("MLFLOW_TRACKING_AWS_SIGV4") == "true":
        status["auth_type"] = "aws_sigv4"
        status["is_configured"] = True
    elif os.getenv("MLFLOW_TRACKING_CLIENT_CERT_PATH"):
        status["auth_type"] = "mtls"
        status["is_configured"] = True
    
    # Check if remote
    if tracking_uri and tracking_uri != "Not configured":
        parsed = urlparse(tracking_uri)
        status["is_remote"] = parsed.scheme in ["http", "https"]
    
    return status