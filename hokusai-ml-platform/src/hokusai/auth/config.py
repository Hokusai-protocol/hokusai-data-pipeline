"""Authentication configuration for Hokusai SDK."""

import configparser
import os
from pathlib import Path
from typing import Optional


class AuthConfig:
    """Authentication configuration manager."""

    def __init__(self, api_key: Optional[str] = None, api_endpoint: Optional[str] = None):
        """Initialize authentication configuration."""
        # Priority: explicit args > env vars > config file
        self.api_key = api_key or self._get_api_key()
        self.api_endpoint = api_endpoint or self._get_api_endpoint()

    def _get_api_key(self) -> Optional[str]:
        """Get API key from environment or config file."""
        # Check environment variable
        api_key = os.environ.get("HOKUSAI_API_KEY")
        if api_key:
            return api_key

        # Check config file
        config = self._load_config_file()
        if config and "default" in config:
            return config["default"].get("api_key")

        return None

    def _get_api_endpoint(self) -> str:
        """Get API endpoint from environment or config file."""
        # Check environment variable
        endpoint = os.environ.get("HOKUSAI_API_ENDPOINT")
        if endpoint:
            return endpoint

        # Check config file
        config = self._load_config_file()
        if config and "default" in config:
            endpoint = config["default"].get("api_endpoint")
            if endpoint:
                return endpoint

        # Default endpoint
        return "https://registry.hokus.ai/api"

    def _load_config_file(self) -> Optional[configparser.ConfigParser]:
        """Load configuration from file."""
        config_paths = [
            Path.home() / ".hokusai" / "config",
            Path.cwd() / ".hokusai",
            Path.cwd() / "hokusai.ini",
        ]

        for config_path in config_paths:
            if config_path.exists():
                config = configparser.ConfigParser()
                config.read(config_path)
                return config

        return None

    @classmethod
    def from_file(cls, file_path: str) -> "AuthConfig":
        """Load configuration from specific file."""
        config = configparser.ConfigParser()
        config.read(file_path)

        api_key = None
        api_endpoint = None

        if "default" in config:
            api_key = config["default"].get("api_key")
            api_endpoint = config["default"].get("api_endpoint")

        return cls(api_key=api_key, api_endpoint=api_endpoint)

    def validate(self) -> None:
        """Validate configuration."""
        if not self.api_key:
            # Check if user is trying to use MLFLOW_TRACKING_TOKEN
            if os.environ.get("MLFLOW_TRACKING_TOKEN"):
                raise ValueError(
                    "Authentication failed: HOKUSAI_API_KEY is required.\n\n"
                    "You have MLFLOW_TRACKING_TOKEN set, but Hokusai requires HOKUSAI_API_KEY.\n"
                    "Both environment variables should be set to your API key:\n\n"
                    "  export HOKUSAI_API_KEY='your_api_key_here'\n"
                    "  export MLFLOW_TRACKING_TOKEN='your_api_key_here'\n\n"
                    "Alternative methods:\n"
                    "1. Pass api_key parameter: ModelRegistry(api_key='your_api_key')\n"
                    "2. Initialize global auth: hokusai.init(api_key='your_api_key')\n"
                    "3. Create config file at ~/.hokusai/config"
                )
            else:
                raise ValueError(
                    "Authentication failed: No API key found.\n\n"
                    "Please provide your Hokusai API key using one of these methods:\n\n"
                    "1. Set environment variables (recommended):\n"
                    "   export HOKUSAI_API_KEY='your_api_key_here'\n"
                    "   export MLFLOW_TRACKING_TOKEN='your_api_key_here'  # Same key for MLflow\n\n"
                    "2. Pass api_key parameter:\n"
                    "   registry = ModelRegistry(api_key='your_api_key')\n\n"
                    "3. Initialize global auth:\n"
                    "   import hokusai\n"
                    "   hokusai.init(api_key='your_api_key')\n\n"
                    "4. Create config file at ~/.hokusai/config:\n"
                    "   [default]\n"
                    "   api_key = your_api_key_here\n\n"
                    "Note: Both HOKUSAI_API_KEY and MLFLOW_TRACKING_TOKEN are required for full functionality."
                )


class ProfileManager:
    """Manage multiple authentication profiles."""

    def __init__(self):
        """Initialize profile manager."""
        self.config_file = Path.home() / ".hokusai" / "profiles"
        self.profiles = self._load_profiles()

    def _load_profiles(self) -> configparser.ConfigParser:
        """Load profiles from config file."""
        config = configparser.ConfigParser()
        if self.config_file.exists():
            config.read(self.config_file)
        return config

    def add_profile(self, name: str, api_key: str, api_endpoint: str = None) -> None:
        """Add a new profile."""
        if name not in self.profiles:
            self.profiles.add_section(name)

        self.profiles[name]["api_key"] = api_key
        if api_endpoint:
            self.profiles[name]["api_endpoint"] = api_endpoint

        self._save_profiles()

    def get_profile(self, name: str) -> Optional[AuthConfig]:
        """Get a specific profile."""
        if name not in self.profiles:
            return None

        return AuthConfig(
            api_key=self.profiles[name].get("api_key"),
            api_endpoint=self.profiles[name].get("api_endpoint"),
        )

    def set_active(self, name: str) -> None:
        """Set active profile."""
        if name not in self.profiles:
            raise ValueError(f"Profile '{name}' not found")

        # Save active profile to main config
        config_file = Path.home() / ".hokusai" / "config"
        config = configparser.ConfigParser()

        if not config.has_section("default"):
            config.add_section("default")

        config["default"]["active_profile"] = name
        config["default"]["api_key"] = self.profiles[name]["api_key"]

        if "api_endpoint" in self.profiles[name]:
            config["default"]["api_endpoint"] = self.profiles[name]["api_endpoint"]

        config_file.parent.mkdir(exist_ok=True)
        with open(config_file, "w") as f:
            config.write(f)

    def _save_profiles(self) -> None:
        """Save profiles to config file."""
        self.config_file.parent.mkdir(exist_ok=True)
        with open(self.config_file, "w") as f:
            self.profiles.write(f)
