"""Tests for provider abstraction layer."""

from typing import Any, Dict

import pytest

from src.services.providers.base_provider import (
    BaseProvider,
    DeploymentResult,
    PredictionResult,
    ProviderConfig,
)
from src.services.providers.provider_registry import ProviderRegistry


class TestProviderConfig:
    """Test ProviderConfig dataclass."""

    def test_create_provider_config(self):
        """Test creating a provider configuration."""
        config = ProviderConfig(
            provider_name="huggingface",
            credentials={"api_key": "test-key"},
            default_instance_type="cpu",
            supported_instance_types=["cpu", "gpu"],
            timeout=30.0,
            max_retries=3,
        )

        assert config.provider_name == "huggingface"
        assert config.credentials == {"api_key": "test-key"}
        assert config.default_instance_type == "cpu"
        assert config.supported_instance_types == ["cpu", "gpu"]
        assert config.timeout == 30.0
        assert config.max_retries == 3

    def test_provider_config_defaults(self):
        """Test provider configuration defaults."""
        config = ProviderConfig(provider_name="huggingface", credentials={"api_key": "test-key"})

        assert config.default_instance_type == "cpu"
        assert config.supported_instance_types == ["cpu"]
        assert config.timeout == 30.0
        assert config.max_retries == 3


class TestDeploymentResult:
    """Test DeploymentResult dataclass."""

    def test_successful_deployment_result(self):
        """Test creating a successful deployment result."""
        result = DeploymentResult(
            success=True,
            endpoint_url="https://api.huggingface.co/inference/endpoints/test",
            provider_model_id="test-endpoint",
            metadata={"instance_type": "cpu", "region": "us-east-1"},
        )

        assert result.success is True
        assert result.endpoint_url == "https://api.huggingface.co/inference/endpoints/test"
        assert result.provider_model_id == "test-endpoint"
        assert result.error_message is None
        assert result.metadata == {"instance_type": "cpu", "region": "us-east-1"}

    def test_failed_deployment_result(self):
        """Test creating a failed deployment result."""
        result = DeploymentResult(
            success=False, error_message="Deployment failed: insufficient quota"
        )

        assert result.success is False
        assert result.endpoint_url is None
        assert result.provider_model_id is None
        assert result.error_message == "Deployment failed: insufficient quota"
        assert result.metadata == {}


class TestPredictionResult:
    """Test PredictionResult dataclass."""

    def test_successful_prediction_result(self):
        """Test creating a successful prediction result."""
        predictions = [{"label": "positive", "score": 0.95}]
        result = PredictionResult(
            success=True,
            predictions=predictions,
            response_time_ms=150,
            metadata={"model_version": "v1.0"},
        )

        assert result.success is True
        assert result.predictions == predictions
        assert result.response_time_ms == 150
        assert result.error_message is None
        assert result.metadata == {"model_version": "v1.0"}

    def test_failed_prediction_result(self):
        """Test creating a failed prediction result."""
        result = PredictionResult(
            success=False, error_message="Model inference failed: timeout", response_time_ms=5000
        )

        assert result.success is False
        assert result.predictions == []
        assert result.response_time_ms == 5000
        assert result.error_message == "Model inference failed: timeout"
        assert result.metadata == {}


class TestBaseProvider:
    """Test BaseProvider abstract class."""

    def test_base_provider_is_abstract(self):
        """Test that BaseProvider is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            BaseProvider()

    def test_base_provider_abstract_methods(self):
        """Test that BaseProvider has required abstract methods."""
        abstract_methods = BaseProvider.__abstractmethods__
        expected_methods = {
            "deploy_model",
            "undeploy_model",
            "predict",
            "get_deployment_status",
            "validate_config",
        }
        assert abstract_methods == expected_methods

    def test_concrete_provider_implementation(self):
        """Test that a concrete provider can be implemented."""

        class TestProvider(BaseProvider):
            """Test concrete provider implementation."""

            async def deploy_model(
                self, model_id: str, model_uri: str, instance_type: str = "cpu", **kwargs
            ) -> DeploymentResult:
                return DeploymentResult(
                    success=True,
                    endpoint_url="https://test.example.com/endpoint",
                    provider_model_id="test-model-123",
                )

            async def undeploy_model(self, provider_model_id: str) -> bool:
                return True

            async def predict(
                self, endpoint_url: str, inputs: Dict[str, Any], **kwargs
            ) -> PredictionResult:
                return PredictionResult(
                    success=True, predictions=[{"output": "test prediction"}], response_time_ms=100
                )

            async def get_deployment_status(self, provider_model_id: str) -> str:
                return "running"

            def validate_config(self, config: ProviderConfig) -> bool:
                return True

        # Should be able to instantiate concrete provider
        config = ProviderConfig(provider_name="test", credentials={})
        provider = TestProvider(config)
        assert isinstance(provider, BaseProvider)
        assert provider.config == config

    def test_provider_name_property(self):
        """Test that provider_name property works correctly."""

        class TestProvider(BaseProvider):
            async def deploy_model(
                self, model_id: str, model_uri: str, instance_type: str = "cpu", **kwargs
            ) -> DeploymentResult:
                pass

            async def undeploy_model(self, provider_model_id: str) -> bool:
                pass

            async def predict(
                self, endpoint_url: str, inputs: Dict[str, Any], **kwargs
            ) -> PredictionResult:
                pass

            async def get_deployment_status(self, provider_model_id: str) -> str:
                pass

            def validate_config(self, config: ProviderConfig) -> bool:
                pass

        config = ProviderConfig(provider_name="test-provider", credentials={})
        provider = TestProvider(config)
        assert provider.provider_name == "test-provider"


class TestProviderRegistry:
    """Test provider registry functionality."""

    def test_create_provider_registry(self):
        """Test creating a provider registry."""
        registry = ProviderRegistry()
        assert isinstance(registry, ProviderRegistry)
        assert len(registry.get_available_providers()) == 0

    def test_register_provider_class(self):
        """Test registering a provider class."""
        registry = ProviderRegistry()

        class TestProvider(BaseProvider):
            async def deploy_model(
                self, model_id: str, model_uri: str, instance_type: str = "cpu", **kwargs
            ) -> DeploymentResult:
                pass

            async def undeploy_model(self, provider_model_id: str) -> bool:
                pass

            async def predict(
                self, endpoint_url: str, inputs: Dict[str, Any], **kwargs
            ) -> PredictionResult:
                pass

            async def get_deployment_status(self, provider_model_id: str) -> str:
                pass

            def validate_config(self, config: ProviderConfig) -> bool:
                pass

        registry.register_provider("test", TestProvider)
        available_providers = registry.get_available_providers()
        assert "test" in available_providers
        assert available_providers["test"] == TestProvider

    def test_get_provider_instance(self):
        """Test getting a provider instance from registry."""
        registry = ProviderRegistry()

        class TestProvider(BaseProvider):
            async def deploy_model(
                self, model_id: str, model_uri: str, instance_type: str = "cpu", **kwargs
            ) -> DeploymentResult:
                pass

            async def undeploy_model(self, provider_model_id: str) -> bool:
                pass

            async def predict(
                self, endpoint_url: str, inputs: Dict[str, Any], **kwargs
            ) -> PredictionResult:
                pass

            async def get_deployment_status(self, provider_model_id: str) -> str:
                pass

            def validate_config(self, config: ProviderConfig) -> bool:
                return True

        registry.register_provider("test", TestProvider)

        config = ProviderConfig(provider_name="test", credentials={"key": "value"})
        provider = registry.get_provider("test", config)

        assert isinstance(provider, TestProvider)
        assert provider.config == config

    def test_get_nonexistent_provider(self):
        """Test getting a provider that doesn't exist."""
        registry = ProviderRegistry()
        config = ProviderConfig(provider_name="nonexistent", credentials={})

        with pytest.raises(ValueError, match="Provider 'nonexistent' not found"):
            registry.get_provider("nonexistent", config)

    def test_provider_exists(self):
        """Test checking if a provider exists."""
        registry = ProviderRegistry()

        class TestProvider(BaseProvider):
            async def deploy_model(
                self, model_id: str, model_uri: str, instance_type: str = "cpu", **kwargs
            ) -> DeploymentResult:
                pass

            async def undeploy_model(self, provider_model_id: str) -> bool:
                pass

            async def predict(
                self, endpoint_url: str, inputs: Dict[str, Any], **kwargs
            ) -> PredictionResult:
                pass

            async def get_deployment_status(self, provider_model_id: str) -> str:
                pass

            def validate_config(self, config: ProviderConfig) -> bool:
                pass

        registry.register_provider("test", TestProvider)

        assert registry.provider_exists("test") is True
        assert registry.provider_exists("nonexistent") is False

    def test_singleton_registry(self):
        """Test that provider registry follows singleton pattern."""
        registry1 = ProviderRegistry()
        registry2 = ProviderRegistry()

        # Both should be the same instance
        assert registry1 is registry2

    def test_registry_clear(self):
        """Test clearing the provider registry."""
        registry = ProviderRegistry()

        class TestProvider(BaseProvider):
            async def deploy_model(
                self, model_id: str, model_uri: str, instance_type: str = "cpu", **kwargs
            ) -> DeploymentResult:
                pass

            async def undeploy_model(self, provider_model_id: str) -> bool:
                pass

            async def predict(
                self, endpoint_url: str, inputs: Dict[str, Any], **kwargs
            ) -> PredictionResult:
                pass

            async def get_deployment_status(self, provider_model_id: str) -> str:
                pass

            def validate_config(self, config: ProviderConfig) -> bool:
                pass

        registry.register_provider("test", TestProvider)
        assert len(registry.get_available_providers()) == 1

        registry.clear()
        assert len(registry.get_available_providers()) == 0
