"""Configuration settings for the API."""

import os
from functools import lru_cache

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
    mlflow_tracking_uri: str = "http://mlflow.hokusai-development.local:5000"

    # Database Configuration
    # Support both old (mlflow) and new (mlflow_db) database names for backward compatibility
    database_host: str = "hokusai-mlflow-development.cmqduyfpzmbr.us-east-1.rds.amazonaws.com"
    database_port: int = 5432
    database_user: str = "mlflow"  # Changed to match MLflow RDS configuration
    database_password: str = "postgres"
    database_name: str = "mlflow_db"  # Updated to match infrastructure
    database_fallback_name: str = "mlflow"  # Fallback for backward compatibility
    
    # Environment variable overrides for flexibility
    @property
    def effective_database_host(self) -> str:
        return os.getenv("DATABASE_HOST", self.database_host)
    
    @property
    def effective_database_port(self) -> int:
        return int(os.getenv("DATABASE_PORT", str(self.database_port)))
    
    @property
    def effective_database_user(self) -> str:
        return os.getenv("DATABASE_USER", self.database_user)
    
    @property
    def effective_database_password(self) -> str:
        return os.getenv("DATABASE_PASSWORD", self.database_password)
    
    @property
    def effective_database_name(self) -> str:
        return os.getenv("DATABASE_NAME", self.database_name)
    
    # Connection settings
    database_connect_timeout: int = 10  # Increased from 5 seconds
    database_max_retries: int = 3
    database_retry_delay: float = 1.0  # Base delay for exponential backoff
    
    # Legacy property for backward compatibility
    @property
    def postgres_uri(self) -> str:
        """Generate PostgreSQL connection URI with new database name using environment variables."""
        return f"postgresql://{self.effective_database_user}:{self.effective_database_password}@{self.effective_database_host}:{self.effective_database_port}/{self.effective_database_name}"
    
    @property
    def postgres_uri_fallback(self) -> str:
        """Generate fallback PostgreSQL connection URI with old database name."""
        return f"postgresql://{self.effective_database_user}:{self.effective_database_password}@{self.effective_database_host}:{self.effective_database_port}/{self.database_fallback_name}"

    # Redis (optional - not currently deployed)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_enabled: bool = False  # Redis is optional and not deployed

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra fields from .env


@lru_cache
def get_settings():
    """Get cached settings instance."""
    return Settings()
