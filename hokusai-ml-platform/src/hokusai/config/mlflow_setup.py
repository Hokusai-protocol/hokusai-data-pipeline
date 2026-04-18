"""MLflow Setup and Configuration Module

This module provides comprehensive MLflow setup with automatic fallback mechanisms
to handle authentication errors gracefully.
"""

import logging
import os
from typing import Any, Dict, Optional

import mlflow
from mlflow.exceptions import MlflowException

logger = logging.getLogger(__name__)


class MLflowSetup:
    """Handles MLflow configuration with automatic fallback mechanisms."""

    DEFAULT_TRACKING_URI = "https://registry.hokus.ai/api/mlflow"
    LOCAL_TRACKING_URI = "http://localhost:5001"

    def __init__(self, tracking_uri: Optional[str] = None):
        self.tracking_uri = tracking_uri or os.environ.get(
            "MLFLOW_TRACKING_URI", self.DEFAULT_TRACKING_URI
        )
        self.is_configured = False
        self.is_local = False
        self.auth_method = None

    def configure(self, api_key: Optional[str] = None, force_local: bool = False) -> bool:
        """Configure MLflow with automatic fallback to local server.

        Args:
        ----
            api_key: Optional API key for authentication
            force_local: Force use of local MLflow server

        Returns:
        -------
            bool: True if configuration successful, False otherwise

        """
        # Check if we should use mock mode
        if os.environ.get("HOKUSAI_MOCK_MODE"):
            logger.info("MLflow mock mode enabled - skipping configuration")
            self.is_configured = False
            return False

        # Try remote server first (unless forced local)
        if not force_local:
            if self._configure_remote(api_key):
                return True

            # Remote failed. If the caller explicitly supplied an api_key they
            # want authenticated remote tracking — silently falling back to an
            # unauthenticated local server would hide the real failure and, worse,
            # clobber MLFLOW_TRACKING_TOKEN so later retries against the remote
            # also 401 with "API key required".
            if api_key is not None:
                logger.error(
                    "Remote MLflow configuration failed at %s; refusing to fall "
                    "back to local because an API key was provided.",
                    self.tracking_uri,
                )
                self.is_configured = False
                return False

        # Fallback to local server
        if self._configure_local():
            return True

        # If optional MLflow is enabled, just log and continue
        if os.environ.get("HOKUSAI_OPTIONAL_MLFLOW"):
            logger.warning(
                "MLflow configuration failed but HOKUSAI_OPTIONAL_MLFLOW is set - continuing without MLflow"
            )
            self.is_configured = False
            return False

        logger.error("Failed to configure MLflow - no working server found")
        self.is_configured = False
        return False

    def _configure_remote(self, api_key: Optional[str] = None) -> bool:
        """Try to configure remote MLflow server."""
        try:
            # Set tracking URI
            mlflow.set_tracking_uri(self.tracking_uri)

            # Configure authentication
            if api_key:
                os.environ["MLFLOW_TRACKING_TOKEN"] = api_key
                self.auth_method = "bearer_token"
            elif os.environ.get("MLFLOW_TRACKING_TOKEN"):
                self.auth_method = "bearer_token"
            elif os.environ.get("MLFLOW_TRACKING_USERNAME"):
                self.auth_method = "basic_auth"
            else:
                self.auth_method = "none"

            # Test connection
            logger.info(
                f"Testing MLflow connection to {self.tracking_uri} with auth method: {self.auth_method}"
            )
            experiments = mlflow.search_experiments()

            logger.info(f"Successfully connected to MLflow at {self.tracking_uri}")
            self.is_configured = True
            self.is_local = False
            return True

        except MlflowException as e:
            if "403" in str(e):
                logger.error(f"Authentication failed for {self.tracking_uri}: {e}")
            elif "404" in str(e):
                logger.error(f"MLflow endpoint not found at {self.tracking_uri}: {e}")
            else:
                logger.error(f"Failed to connect to MLflow at {self.tracking_uri}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to MLflow: {e}")
            return False

    def _configure_local(self) -> bool:
        """Try to configure local MLflow server.

        The auth env vars and global tracking URI are snapshotted before the
        attempt and restored on failure, so a failed local probe never leaves
        the process in a half-reconfigured state that breaks subsequent remote
        calls.
        """
        auth_keys = (
            "MLFLOW_TRACKING_TOKEN",
            "MLFLOW_TRACKING_USERNAME",
            "MLFLOW_TRACKING_PASSWORD",
        )
        saved_env = {key: os.environ.get(key) for key in auth_keys}
        saved_tracking_uri = mlflow.get_tracking_uri()

        try:
            # Clear any existing auth that might interfere with an unauthenticated
            # local server.
            for key in auth_keys:
                os.environ.pop(key, None)

            # Set local tracking URI
            mlflow.set_tracking_uri(self.LOCAL_TRACKING_URI)
            self.auth_method = "none"

            # Test connection
            logger.info(f"Testing local MLflow connection at {self.LOCAL_TRACKING_URI}")
            experiments = mlflow.search_experiments()

            logger.info(f"Successfully connected to local MLflow at {self.LOCAL_TRACKING_URI}")
            self.tracking_uri = self.LOCAL_TRACKING_URI
            self.is_configured = True
            self.is_local = True
            return True

        except Exception as e:
            logger.error(f"Failed to connect to local MLflow: {e}")
            # Restore prior auth/URI so callers can still reach the remote server.
            for key, value in saved_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            mlflow.set_tracking_uri(saved_tracking_uri)
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get current MLflow configuration status."""
        return {
            "configured": self.is_configured,
            "tracking_uri": self.tracking_uri if self.is_configured else None,
            "is_local": self.is_local,
            "auth_method": self.auth_method,
            "mock_mode": bool(os.environ.get("HOKUSAI_MOCK_MODE")),
            "optional_mlflow": bool(os.environ.get("HOKUSAI_OPTIONAL_MLFLOW")),
        }


# Global instance
_mlflow_setup = MLflowSetup()


def setup_mlflow(
    tracking_uri: Optional[str] = None, api_key: Optional[str] = None, force_local: bool = False
) -> bool:
    """Configure MLflow with automatic fallback mechanisms.

    This is the main entry point for MLflow configuration. It will:
    1. Try to connect to the specified tracking URI with authentication
    2. Fall back to local MLflow server if remote fails
    3. Handle mock mode and optional MLflow settings

    Args:
    ----
        tracking_uri: Optional MLflow tracking URI
        api_key: Optional API key for authentication
        force_local: Force use of local MLflow server

    Returns:
    -------
        bool: True if MLflow is configured and ready, False otherwise

    """
    global _mlflow_setup

    if tracking_uri:
        _mlflow_setup = MLflowSetup(tracking_uri)

    return _mlflow_setup.configure(api_key, force_local)


def get_mlflow_status() -> Dict[str, Any]:
    """Get current MLflow configuration status."""
    return _mlflow_setup.get_status()


def ensure_mlflow_configured() -> bool:
    """Ensure MLflow is configured, attempting to configure if not.

    Returns
    -------
        bool: True if MLflow is configured, False otherwise

    """
    if _mlflow_setup.is_configured:
        return True

    # Try to configure with environment variables
    api_key = os.environ.get("HOKUSAI_API_KEY") or os.environ.get("MLFLOW_TRACKING_TOKEN")
    return setup_mlflow(api_key=api_key)
