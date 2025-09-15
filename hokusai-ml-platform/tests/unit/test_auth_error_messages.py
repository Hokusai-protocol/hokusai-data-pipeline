"""Test authentication error messages are clear and helpful."""

import os
import sys
from pathlib import Path

import pytest

# Add the SDK to path
sdk_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(sdk_path))

from hokusai.auth.config import AuthConfig


class TestAuthErrorMessages:
    """Test that authentication error messages guide users to the solution."""

    def setup_method(self):
        """Clear environment before each test."""
        for key in ["HOKUSAI_API_KEY", "MLFLOW_TRACKING_TOKEN"]:
            os.environ.pop(key, None)

    def teardown_method(self):
        """Clean up after each test."""
        for key in ["HOKUSAI_API_KEY", "MLFLOW_TRACKING_TOKEN"]:
            os.environ.pop(key, None)

    def test_error_when_only_mlflow_token_set(self):
        """Test specific error when user only sets MLFLOW_TRACKING_TOKEN."""
        # User follows old documentation and only sets MLFLOW_TRACKING_TOKEN
        os.environ["MLFLOW_TRACKING_TOKEN"] = "test_token"

        config = AuthConfig()

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        error_msg = str(exc_info.value)

        # Check for specific guidance about the issue
        assert "HOKUSAI_API_KEY is required" in error_msg
        assert "You have MLFLOW_TRACKING_TOKEN set" in error_msg
        assert "export HOKUSAI_API_KEY=" in error_msg
        assert "Both environment variables should be set" in error_msg

    def test_error_when_no_auth_provided(self):
        """Test comprehensive error when no authentication is provided."""
        config = AuthConfig()

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        error_msg = str(exc_info.value)

        # Check that all authentication methods are explained
        assert "Authentication failed" in error_msg
        assert "HOKUSAI_API_KEY" in error_msg
        assert "MLFLOW_TRACKING_TOKEN" in error_msg
        assert "ModelRegistry(api_key=" in error_msg
        assert "hokusai.init(api_key=" in error_msg
        assert "~/.hokusai/config" in error_msg

        # Check that the note about both being required is present
        assert "Both HOKUSAI_API_KEY and MLFLOW_TRACKING_TOKEN are required" in error_msg

    def test_no_error_with_hokusai_api_key(self):
        """Test that setting HOKUSAI_API_KEY works correctly."""
        os.environ["HOKUSAI_API_KEY"] = "test_key"

        config = AuthConfig()
        config.validate()  # Should not raise

        assert config.api_key == "test_key"

    def test_no_error_with_explicit_api_key(self):
        """Test that passing api_key directly works."""
        config = AuthConfig(api_key="explicit_key")
        config.validate()  # Should not raise

        assert config.api_key == "explicit_key"

    def test_error_messages_are_actionable(self):
        """Test that error messages provide clear actionable steps."""
        config = AuthConfig()

        with pytest.raises(ValueError) as exc_info:
            config.validate()

        error_msg = str(exc_info.value)

        # Check for actionable commands
        assert "export HOKUSAI_API_KEY=" in error_msg
        assert "export MLFLOW_TRACKING_TOKEN=" in error_msg

        # Check for code examples
        assert "ModelRegistry(api_key=" in error_msg
        assert "hokusai.init(api_key=" in error_msg

        # Check for config file format
        assert "[default]" in error_msg
        assert "api_key =" in error_msg
