"""Unit tests for SDK integration with API key authentication."""

import os
from unittest.mock import Mock, patch

import pytest

from hokusai.core import ModelRegistry
from hokusai.auth import HokusaiAuth


class TestSDKAuthentication:
    """Test cases for SDK authentication integration."""

    @pytest.fixture
    def mock_api_key_service(self):
        """Mock API key service."""
        with patch('hokusai.auth.api_key_service') as mock_service:
            yield mock_service

    def test_sdk_initialization_with_api_key(self, mock_api_key_service):
        """Test SDK initialization with API key."""
        # Arrange
        api_key = "hk_live_test_key_123"
        mock_api_key_service.validate_api_key.return_value = Mock(
            is_valid=True,
            user_id="user123"
        )
        
        # Act
        # Option 1: Environment variable
        with patch.dict(os.environ, {"HOKUSAI_API_KEY": api_key}):
            registry = ModelRegistry()
            assert registry._auth.api_key == api_key
        
        # Option 2: Direct initialization
        registry = ModelRegistry(api_key=api_key)
        assert registry._auth.api_key == api_key
        
        # Option 3: Auth object
        auth = HokusaiAuth(api_key=api_key)
        registry = ModelRegistry(auth=auth)
        assert registry._auth.api_key == api_key

    def test_sdk_authenticated_requests(self, mock_api_key_service):
        """Test that SDK includes API key in requests."""
        # Arrange
        api_key = "hk_live_test_key_123"
        
        with patch('requests.post') as mock_post:
            mock_post.return_value.json.return_value = {"model_id": "model123"}
            
            # Act
            registry = ModelRegistry(api_key=api_key)
            registry.register_baseline(
                model=Mock(),
                model_type="test_model",
                metadata={}
            )
            
            # Assert
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            headers = call_args[1]["headers"]
            assert headers["Authorization"] == f"Bearer {api_key}"

    def test_sdk_client_configuration(self):
        """Test SDK client configuration with authentication."""
        # This is how users would configure the SDK
        from hokusai.client import HokusaiClient
        
        # Option 1: Simple API key
        client = HokusaiClient(api_key="hk_live_my_key_123")
        
        # Option 2: Full configuration
        client = HokusaiClient(
            api_key="hk_live_my_key_123",
            api_endpoint="https://api.hokus.ai",
            timeout=30,
            retry_count=3
        )
        
        # Option 3: From environment
        with patch.dict(os.environ, {
            "HOKUSAI_API_KEY": "hk_live_env_key_123",
            "HOKUSAI_API_ENDPOINT": "https://api.hokus.ai"
        }):
            client = HokusaiClient()
            assert client.api_key == "hk_live_env_key_123"

    def test_sdk_auth_error_handling(self):
        """Test SDK handling of authentication errors."""
        # Arrange
        from hokusai.exceptions import AuthenticationError
        
        with patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 401
            mock_post.return_value.json.return_value = {"detail": "Invalid API key"}
            
            # Act & Assert
            registry = ModelRegistry(api_key="invalid_key")
            with pytest.raises(AuthenticationError) as exc_info:
                registry.register_baseline(Mock(), "test", {})
            
            assert "Invalid API key" in str(exc_info.value)

    def test_sdk_token_refresh(self):
        """Test SDK automatic token refresh/rotation."""
        # Arrange
        from hokusai.auth import TokenManager
        
        initial_key = "hk_live_initial_key_123"
        rotated_key = "hk_live_rotated_key_456"
        
        with patch('hokusai.auth.TokenManager.rotate_if_needed') as mock_rotate:
            mock_rotate.return_value = rotated_key
            
            # Act
            token_manager = TokenManager(initial_key)
            registry = ModelRegistry(auth=token_manager)
            
            # Simulate time passing and key rotation
            current_key = token_manager.get_current_key()
            
            # Assert
            assert current_key == rotated_key


class TestSDKAuthenticationMethods:
    """Test different authentication methods for the SDK."""

    def test_api_key_from_file(self):
        """Test loading API key from config file."""
        # Arrange
        config_content = """
        [hokusai]
        api_key = hk_live_file_key_123
        api_endpoint = https://api.hokus.ai
        """
        
        with patch('builtins.open', mock_open(read_data=config_content)):
            from hokusai.config import Config
            
            # Act
            config = Config.from_file("~/.hokusai/config")
            
            # Assert
            assert config.api_key == "hk_live_file_key_123"
            assert config.api_endpoint == "https://api.hokus.ai"

    def test_multiple_profiles(self):
        """Test managing multiple API key profiles."""
        # Arrange
        from hokusai.auth import ProfileManager
        
        # Act
        profiles = ProfileManager()
        profiles.add_profile("dev", api_key="hk_test_dev_key_123")
        profiles.add_profile("prod", api_key="hk_live_prod_key_123")
        profiles.set_active("dev")
        
        # Assert
        assert profiles.get_active_key() == "hk_test_dev_key_123"
        
        # Switch profile
        profiles.set_active("prod")
        assert profiles.get_active_key() == "hk_live_prod_key_123"

    def test_sdk_with_service_account(self):
        """Test SDK authentication with service account."""
        # Arrange
        from hokusai.auth import ServiceAccountAuth
        
        service_account_key = {
            "type": "service_account",
            "project_id": "hokusai-ml",
            "private_key_id": "key123",
            "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
        }
        
        # Act
        auth = ServiceAccountAuth.from_json(service_account_key)
        registry = ModelRegistry(auth=auth)
        
        # Assert
        assert auth.project_id == "hokusai-ml"


class TestSDKUsageExamples:
    """Test real-world SDK usage patterns with authentication."""

    def test_basic_sdk_usage_with_auth(self):
        """Test basic SDK usage pattern with authentication."""
        # This is how users would actually use the SDK
        
        # 1. Set up authentication
        os.environ["HOKUSAI_API_KEY"] = "hk_live_user_key_123"
        
        # 2. Initialize SDK components
        from hokusai.core import ModelRegistry
        from hokusai.tracking import ExperimentManager
        
        registry = ModelRegistry()  # Automatically uses env var
        manager = ExperimentManager(registry)
        
        # 3. Use the SDK normally
        with manager.start_experiment("test_experiment"):
            # Training code here
            pass

    def test_sdk_cli_integration(self):
        """Test SDK CLI commands with authentication."""
        # The CLI would handle auth internally
        from hokusai.cli import cli
        from click.testing import CliRunner
        
        runner = CliRunner()
        
        # User runs: hokusai auth login
        result = runner.invoke(cli, ["auth", "login", "--api-key", "hk_live_cli_key_123"])
        assert result.exit_code == 0
        
        # Then uses other commands
        result = runner.invoke(cli, ["model", "list"])
        assert result.exit_code == 0

    def test_sdk_notebook_usage(self):
        """Test SDK usage in Jupyter notebooks."""
        # Common notebook pattern
        from hokusai import setup
        
        # One-time setup in notebook
        setup(api_key="hk_live_notebook_key_123")
        
        # Then use normally
        from hokusai.core import ModelRegistry
        registry = ModelRegistry()  # Uses the setup configuration