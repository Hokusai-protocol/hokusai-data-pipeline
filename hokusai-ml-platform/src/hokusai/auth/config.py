"""Authentication configuration for Hokusai SDK."""

import os
from pathlib import Path
from typing import Optional
import configparser


class AuthConfig:
    """Authentication configuration manager."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_endpoint: Optional[str] = None
    ):
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
        return "https://api.hokus.ai"
    
    def _load_config_file(self) -> Optional[configparser.ConfigParser]:
        """Load configuration from file."""
        config_paths = [
            Path.home() / ".hokusai" / "config",
            Path.cwd() / ".hokusai",
            Path.cwd() / "hokusai.ini"
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
            raise ValueError(
                "No API key found. Set HOKUSAI_API_KEY environment variable "
                "or create a config file at ~/.hokusai/config"
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
            api_endpoint=self.profiles[name].get("api_endpoint")
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