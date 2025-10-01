"""Configuration settings for the API."""

import logging
import os
from functools import lru_cache
from typing import Optional

try:
    import boto3
    import botocore.exceptions
except ImportError:
    boto3 = None
    botocore = None

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """API configuration settings."""

    # API Settings
    api_host: str = "0.0.0.0"
    api_port: int = 8001

    # Security
    secret_key: str = "your-secret-key-here"  # In production, use environment variable
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # CORS
    cors_origins: list[str] = ["*"]  # In production, specify allowed origins

    # MLFlow
    mlflow_tracking_uri: str = (
        "http://mlflow.hokusai-development.local:5000"  # Use service discovery DNS
    )

    # Database Configuration
    # Support both old (mlflow) and new (mlflow_db) database names for backward compatibility
    database_host: str = "hokusai-mlflow-development.cmqduyfpzmbr.us-east-1.rds.amazonaws.com"
    database_port: int = 5432
    database_user: str = "mlflow"  # Changed to match MLflow RDS configuration
    database_password: Optional[str] = None  # Must come from environment or AWS Secrets Manager
    database_name: str = "mlflow_db"  # Updated to match infrastructure
    database_fallback_name: str = "mlflow"  # Fallback for backward compatibility

    # Environment variable overrides for flexibility
    @property
    def effective_database_host(self) -> str:
        # Support both DB_HOST and DATABASE_HOST
        return os.getenv("DB_HOST", os.getenv("DATABASE_HOST", self.database_host))

    @property
    def effective_database_port(self) -> int:
        # Support both DB_PORT and DATABASE_PORT
        return int(os.getenv("DB_PORT", os.getenv("DATABASE_PORT", str(self.database_port))))

    @property
    def effective_database_user(self) -> str:
        # Support both DB_USER and DATABASE_USER
        return os.getenv("DB_USER", os.getenv("DATABASE_USER", self.database_user))

    @property
    def effective_database_password(self) -> str:
        """Get database password from environment variables or AWS Secrets Manager."""
        logger = logging.getLogger(__name__)

        # First try environment variables (both supported for backward compatibility)
        env_password = os.getenv("DB_PASSWORD", os.getenv("DATABASE_PASSWORD"))
        if env_password:
            logger.info("Database password loaded from environment variable")
            return env_password

        # Try AWS Secrets Manager if boto3 is available
        if boto3 is not None:
            try:
                secret_name = os.getenv("DB_SECRET_NAME", "hokusai/database/credentials")
                region_name = os.getenv("AWS_REGION", "us-east-1")

                session = boto3.session.Session()
                client = session.client("secretsmanager", region_name=region_name)

                response = client.get_secret_value(SecretId=secret_name)
                import json

                secret_data = json.loads(response["SecretString"])

                # Try different possible keys for password
                password = (
                    secret_data.get("password")
                    or secret_data.get("PASSWORD")
                    or secret_data.get("db_password")
                )
                if password:
                    logger.info(
                        f"Database password loaded from AWS Secrets Manager (secret: {secret_name})"
                    )
                    return password
                else:
                    logger.warning(
                        f"Password not found in secret {secret_name}. Available keys: {list(secret_data.keys())}"
                    )

            except botocore.exceptions.ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code == "ResourceNotFoundException":
                    logger.warning(f"Secret not found in AWS Secrets Manager: {secret_name}")
                elif error_code == "UnauthorizedOperation":
                    logger.warning("Insufficient permissions to access AWS Secrets Manager")
                else:
                    logger.error(f"AWS Secrets Manager error: {error_code} - {e}")
            except Exception as e:
                logger.error(f"Error retrieving password from AWS Secrets Manager: {e}")
        else:
            logger.debug("boto3 not available, skipping AWS Secrets Manager")

        # If we have a fallback password from class defaults, use it but warn
        if self.database_password:
            logger.warning(
                "Using hardcoded database password - this should only be used in development"
            )
            return self.database_password

        # No password found anywhere - this is an error condition
        error_msg = (
            "Database password not found. Please set DB_PASSWORD or DATABASE_PASSWORD environment variable, "
            "or configure AWS Secrets Manager with secret 'hokusai/database/credentials'"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    @property
    def effective_database_name(self) -> str:
        # Support both DB_NAME and DATABASE_NAME
        return os.getenv("DB_NAME", os.getenv("DATABASE_NAME", self.database_name))

    # Connection settings
    database_connect_timeout: int = 10  # Increased from 5 seconds
    database_max_retries: int = 3
    database_retry_delay: float = 1.0  # Base delay for exponential backoff

    # Legacy property for backward compatibility
    @property
    def postgres_uri(self) -> str:
        """Generate PostgreSQL connection URI with new database name using environment variables."""
        from urllib.parse import quote_plus

        # URL-encode the password to handle special characters
        encoded_password = quote_plus(self.effective_database_password)
        return f"postgresql://{self.effective_database_user}:{encoded_password}@{self.effective_database_host}:{self.effective_database_port}/{self.effective_database_name}"

    @property
    def postgres_uri_fallback(self) -> str:
        """Generate fallback PostgreSQL connection URI with old database name."""
        from urllib.parse import quote_plus

        # URL-encode the password to handle special characters
        encoded_password = quote_plus(self.effective_database_password)
        return f"postgresql://{self.effective_database_user}:{encoded_password}@{self.effective_database_host}:{self.effective_database_port}/{self.database_fallback_name}"

    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 60  # seconds

    # Authentication Service
    auth_service_url: str = "https://auth.hokus.ai"
    auth_service_timeout: float = 10.0  # Increased from 5 seconds
    auth_service_id: str = "platform"  # Service ID for API key validation

    # Health Check Configuration
    health_check_timeout: float = 10.0  # Increased from 5 seconds

    # Circuit Breaker Configuration
    mlflow_cb_failure_threshold: int = 3
    mlflow_cb_recovery_timeout: int = 30
    mlflow_cb_max_recovery_attempts: int = 3

    # Redis Queue Configuration - No defaults, must be configured via environment
    redis_host: Optional[str] = None
    redis_port: int = 6379
    redis_auth_token: Optional[str] = None

    # Webhook Configuration
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    webhook_timeout: int = 30
    webhook_max_retries: int = 5
    webhook_retry_delay: int = 2
    enable_redis_fallback: bool = False
    webhook_circuit_breaker_failure_threshold: int = 5
    webhook_circuit_breaker_recovery_time: int = 60

    @property
    def webhook_enabled(self) -> bool:
        """Check if webhook is enabled."""
        return bool(os.getenv("WEBHOOK_URL"))

    @property
    def effective_webhook_url(self) -> Optional[str]:
        """Get webhook URL from environment."""
        return os.getenv("WEBHOOK_URL", self.webhook_url)

    @property
    def effective_webhook_secret(self) -> Optional[str]:
        """Get webhook secret from environment."""
        return os.getenv("WEBHOOK_SECRET", self.webhook_secret)

    @property
    def redis_enabled(self) -> bool:
        """Check if Redis is enabled (explicit configuration required)."""
        # Redis is enabled if explicitly configured OR if webhook fallback is enabled
        return bool(
            os.getenv("REDIS_URL")
            or os.getenv("REDIS_AUTH_TOKEN")
            or (os.getenv("REDIS_HOST") and not os.getenv("REDIS_HOST").startswith("localhost"))
            or (self.enable_redis_fallback and self.webhook_enabled)
        )

    @property
    def redis_url(self) -> str:
        """Build Redis URL from components or environment variables with TLS support.

        Handles various input formats:
        - Full URL with scheme (redis://, rediss://, unix://) - returned as-is
        - Bare hostname without scheme - scheme added based on REDIS_TLS_ENABLED
        - Component-based (REDIS_HOST, REDIS_PORT, REDIS_AUTH_TOKEN) - URL constructed with TLS support

        TLS Support:
        - REDIS_TLS_ENABLED=true → uses rediss:// scheme (required for AWS ElastiCache)
        - REDIS_TLS_ENABLED=false or not set → uses redis:// scheme

        Examples
        --------
        - REDIS_URL="redis://localhost:6379" → "redis://localhost:6379" (unchanged)
        - REDIS_URL="master.redis.amazonaws.com" + REDIS_TLS_ENABLED="true" → "rediss://master.redis.amazonaws.com:6379"
        - REDIS_HOST="redis.example.com" + REDIS_TLS_ENABLED="true" → "rediss://redis.example.com:6379/0"

        Returns
        -------
            str: Complete Redis URL with scheme (redis://, rediss://, or unix://)

        Raises
        ------
            ValueError: If neither REDIS_URL nor REDIS_HOST is set

        """
        logger = logging.getLogger(__name__)

        # Check for explicit REDIS_URL first
        if redis_url := os.getenv("REDIS_URL"):
            # Validate and fix URL format if needed
            if not redis_url.startswith(("redis://", "rediss://", "unix://")):
                logger.warning(
                    f"REDIS_URL missing scheme, will prepend based on TLS setting. "
                    f"Original value: {redis_url[:50]}..."  # Hide full hostname in logs
                )

                # Determine scheme based on TLS setting
                tls_enabled = os.getenv("REDIS_TLS_ENABLED", "false").lower() == "true"
                scheme = "rediss" if tls_enabled else "redis"

                # Add default port if not in URL
                if ":" not in redis_url:
                    port = os.getenv("REDIS_PORT", str(self.redis_port))
                    redis_url = f"{scheme}://{redis_url}:{port}"
                else:
                    # Port already in URL (host:port format)
                    redis_url = f"{scheme}://{redis_url}"

                logger.info(
                    f"Constructed Redis URL with {scheme}:// scheme and port. "
                    f"TLS enabled: {tls_enabled}"
                )
            else:
                # URL already has valid scheme
                logger.debug("Using Redis URL from environment with existing scheme")

            return redis_url

        # Build from components - require explicit configuration
        host = os.getenv("REDIS_HOST")
        if not host:
            raise ValueError(
                "Redis configuration missing: REDIS_HOST or REDIS_URL must be set. "
                "Redis will not fall back to localhost - explicit configuration required."
            )

        port = os.getenv("REDIS_PORT", str(self.redis_port))
        auth_token = os.getenv("REDIS_AUTH_TOKEN")
        tls_enabled = os.getenv("REDIS_TLS_ENABLED", "false").lower() == "true"

        # Use rediss:// for TLS connections (AWS ElastiCache), redis:// for non-TLS
        scheme = "rediss" if tls_enabled else "redis"

        if auth_token:
            # ElastiCache authenticated connection with TLS support
            url = f"{scheme}://:{auth_token}@{host}:{port}/0"
            logger.info(
                f"Built Redis URL from components with auth and {scheme}:// scheme. "
                f"Host: {host}:{port}, TLS: {tls_enabled}"
            )
            return url
        else:
            # Unauthenticated connection (development only)
            logger.warning(
                f"Redis connection without authentication to {host}:{port} using {scheme}:// - "
                "this should only be used in development"
            )
            return f"{scheme}://{host}:{port}/0"

    def validate_required_credentials(self) -> None:
        """Validate that all required credentials are available at startup."""
        logger = logging.getLogger(__name__)

        try:
            # Test that we can get the database password
            # Use a direct check to avoid infinite recursion
            env_password = os.getenv("DB_PASSWORD", os.getenv("DATABASE_PASSWORD"))
            secret_name = os.getenv("DB_SECRET_NAME")

            if not env_password and not secret_name and not self.database_password:
                raise ValueError(
                    "Database password not found. Please set DB_PASSWORD or DATABASE_PASSWORD environment variable, "
                    "or configure AWS Secrets Manager with secret 'hokusai/database/credentials'"
                )
            logger.info("Database credentials validation successful")
        except Exception as e:
            error_msg = f"Failed to validate database credentials: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra fields from .env


@lru_cache
def get_settings():
    """Get cached settings instance with credential validation."""
    settings = Settings()
    # Validate credentials on first access
    try:
        settings.validate_required_credentials()
    except ValueError as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Settings validation failed: {e}")
        # Re-raise to ensure the application doesn't start with invalid config
        raise
    return settings
