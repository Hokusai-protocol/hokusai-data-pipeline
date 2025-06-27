"""Configuration settings for the API."""

from pydantic_settings import BaseSettings
from typing import List
from functools import lru_cache


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
    cors_origins: List[str] = ["*"]  # In production, specify allowed origins
    
    # MLFlow
    mlflow_tracking_uri: str = "http://mlflow-server:5000"
    
    # Database
    postgres_uri: str = "postgresql://mlflow:mlflow_password@postgres/mlflow_db"
    
    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    
    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 60  # seconds
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra fields from .env


@lru_cache()
def get_settings():
    """Get cached settings instance."""
    return Settings()