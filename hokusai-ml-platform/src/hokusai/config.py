"""Configuration module for Hokusai ML Platform."""

import os
import logging
import mlflow

logger = logging.getLogger(__name__)


def setup_mlflow_auth(tracking_uri: str = None, validate: bool = True) -> None:
    """Setup MLflow authentication using environment variables.
    
    Args:
        tracking_uri: Optional MLflow tracking URI to override environment
        validate: Whether to validate the connection (default: True)
    
    Supported authentication methods:
    - MLFLOW_TRACKING_TOKEN: Bearer token authentication
    - MLFLOW_TRACKING_USERNAME/PASSWORD: Basic authentication
    - MLFLOW_TRACKING_AWS_SIGV4: AWS signature authentication
    
    The function will automatically detect and use the appropriate
    authentication method based on available environment variables.
    """
    # Set tracking URI if provided
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
        logger.info(f"MLflow tracking URI set to: {tracking_uri}")
    
    # Check for authentication environment variables
    auth_configured = False
    
    # Token authentication (most common)
    if os.environ.get("MLFLOW_TRACKING_TOKEN"):
        logger.info("MLflow token authentication configured")
        auth_configured = True
    
    # Basic authentication
    elif os.environ.get("MLFLOW_TRACKING_USERNAME") and os.environ.get("MLFLOW_TRACKING_PASSWORD"):
        logger.info("MLflow basic authentication configured")
        auth_configured = True
    
    # AWS signature authentication
    elif os.environ.get("MLFLOW_TRACKING_AWS_SIGV4") == "true":
        logger.info("MLflow AWS signature authentication configured")
        auth_configured = True
    
    # Databricks authentication
    elif os.environ.get("DATABRICKS_HOST") and os.environ.get("DATABRICKS_TOKEN"):
        logger.info("Databricks authentication configured")
        auth_configured = True
    
    if not auth_configured:
        logger.warning("No MLflow authentication configured. This may cause 403 errors.")
        logger.info("Set one of the following:")
        logger.info("  - MLFLOW_TRACKING_TOKEN for bearer token auth")
        logger.info("  - MLFLOW_TRACKING_USERNAME and MLFLOW_TRACKING_PASSWORD for basic auth")
        logger.info("  - MLFLOW_TRACKING_AWS_SIGV4=true for AWS auth")
        logger.info("  - Or use HOKUSAI_MOCK_MODE=true for local development")
    
    # Validate connection if requested
    if validate and auth_configured:
        try:
            # Try a simple operation to verify auth works
            mlflow.search_experiments(max_results=1)
            logger.info("MLflow authentication validated successfully")
        except Exception as e:
            logger.error(f"MLflow authentication validation failed: {str(e)}")
            raise


def get_mlflow_config() -> dict:
    """Get current MLflow configuration.
    
    Returns:
        Dictionary with MLflow configuration details
    """
    return {
        "tracking_uri": mlflow.get_tracking_uri(),
        "registry_uri": mlflow.get_registry_uri(),
        "has_token": bool(os.environ.get("MLFLOW_TRACKING_TOKEN")),
        "has_basic_auth": bool(
            os.environ.get("MLFLOW_TRACKING_USERNAME") and 
            os.environ.get("MLFLOW_TRACKING_PASSWORD")
        ),
        "has_aws_auth": os.environ.get("MLFLOW_TRACKING_AWS_SIGV4") == "true",
        "mock_mode": os.environ.get("HOKUSAI_MOCK_MODE", "false").lower() == "true",
        "optional_mlflow": os.environ.get("HOKUSAI_OPTIONAL_MLFLOW", "true").lower() == "true"
    }