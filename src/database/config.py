"""Database configuration module for Hokusai ML Platform.
"""
import json
import os
from pathlib import Path
from typing import Any, Optional


class DatabaseConfig:
    """Configuration for database connections."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        db_type: str = "postgresql",
    ) -> None:
        self.host = host or os.getenv("HOKUSAI_DB_HOST", "localhost")
        self.port = port or int(os.getenv("HOKUSAI_DB_PORT", "5432"))
        self.database = database or os.getenv("HOKUSAI_DB_NAME", "hokusai")
        self.username = username or os.getenv("HOKUSAI_DB_USER", "hokusai_user")
        self.password = password or os.getenv("HOKUSAI_DB_PASSWORD", "")
        self.db_type = db_type or os.getenv("HOKUSAI_DB_TYPE", "postgresql")

    @classmethod
    def from_file(cls, config_path: str) -> "DatabaseConfig":
        """Load configuration from a JSON or YAML file."""
        path = Path(config_path)

        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(path) as f:
            if path.suffix == ".json":
                config_data = json.load(f)
            elif path.suffix in [".yml", ".yaml"]:
                try:
                    import yaml

                    config_data = yaml.safe_load(f)
                except ImportError:
                    raise ImportError(
                        "PyYAML is required to load YAML configuration files"
                    ) from None
            else:
                raise ValueError(f"Unsupported configuration file format: {path.suffix}")

        return cls(
            host=config_data.get("host"),
            port=config_data.get("port"),
            database=config_data.get("database"),
            username=config_data.get("username"),
            password=config_data.get("password"),
            db_type=config_data.get("db_type", "postgresql"),
        )

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Load configuration from environment variables."""
        return cls()

    def get_connection_string(self) -> str:
        """Get database connection string."""
        if self.db_type == "postgresql":
            return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        elif self.db_type == "mysql":
            return f"mysql+pymysql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        elif self.db_type == "sqlite":
            return f"sqlite:///{self.database}"
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "username": self.username,
            "db_type": self.db_type
            # Note: password is intentionally excluded for security
        }
