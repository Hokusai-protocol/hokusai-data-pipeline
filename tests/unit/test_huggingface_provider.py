"""Tests for HuggingFace provider implementation."""

from unittest.mock import Mock, patch

import httpx
import pytest

from src.services.providers.base_provider import ProviderConfig
from src.services.providers.huggingface_provider import HuggingFaceProvider


class TestHuggingFaceProvider:
    """Test HuggingFace provider implementation."""

    @pytest.fixture
    def provider_config(self):
        """Create test provider configuration."""
        return ProviderConfig(
            provider_name="huggingface",
            credentials={"api_key": "hf_test_key"},
            default_instance_type="cpu",
            supported_instance_types=["cpu", "gpu"],
            timeout=30.0,
            max_retries=3,
        )

    @pytest.fixture
    def provider(self, provider_config):
        """Create HuggingFace provider instance."""
        return HuggingFaceProvider(provider_config)

    def test_provider_initialization(self, provider, provider_config):
        """Test provider initialization."""
        assert provider.config == provider_config
        assert provider.provider_name == "huggingface"
        assert provider.api_key == "hf_test_key"
        assert provider.base_url == "https://api.huggingface.co"

    def test_validate_config_success(self, provider):
        """Test successful configuration validation."""
        config = ProviderConfig(
            provider_name="huggingface",
            credentials={"api_key": "hf_valid_key"},
            supported_instance_types=["cpu", "gpu"],
        )
        assert provider.validate_config(config) is True

    def test_validate_config_missing_api_key(self, provider):
        """Test configuration validation with missing API key."""
        config = ProviderConfig(provider_name="huggingface", credentials={})
        assert provider.validate_config(config) is False

    def test_validate_config_invalid_instance_type(self, provider):
        """Test configuration validation with invalid instance type."""
        config = ProviderConfig(
            provider_name="huggingface",
            credentials={"api_key": "hf_valid_key"},
            supported_instance_types=["invalid_type"],
        )
        assert provider.validate_config(config) is False

    @pytest.mark.asyncio
    async def test_deploy_model_success(self, provider):
        """Test successful model deployment."""
        mock_response_data = {
            "name": "test-model-endpoint",
            "status": {"state": "Pending"},
            "url": "https://test-model-endpoint.huggingface.co",
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_post.return_value = mock_response

            result = await provider.deploy_model(
                model_id="test-model-123",
                model_uri="microsoft/DialoGPT-medium",
                instance_type="cpu",
            )

            assert result.success is True
            assert result.provider_model_id == "test-model-endpoint"
            assert result.endpoint_url == "https://test-model-endpoint.huggingface.co"
            assert result.error_message is None

            # Verify API call was made
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_deploy_model_failure(self, provider):
        """Test failed model deployment."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.json.return_value = {"error": "Invalid model repository"}
            mock_post.return_value = mock_response

            result = await provider.deploy_model(
                model_id="test-model-123", model_uri="invalid/model", instance_type="cpu"
            )

            assert result.success is False
            assert result.provider_model_id is None
            assert result.endpoint_url is None
            assert "Invalid model repository" in result.error_message

    @pytest.mark.asyncio
    async def test_deploy_model_http_error(self, provider):
        """Test model deployment with HTTP error."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timeout")

            result = await provider.deploy_model(
                model_id="test-model-123",
                model_uri="microsoft/DialoGPT-medium",
                instance_type="cpu",
            )

            assert result.success is False
            assert "Request timeout" in result.error_message

    @pytest.mark.asyncio
    async def test_undeploy_model_success(self, provider):
        """Test successful model undeployment."""
        with patch("httpx.AsyncClient.delete") as mock_delete:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_delete.return_value = mock_response

            result = await provider.undeploy_model("test-model-endpoint")

            assert result is True
            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_undeploy_model_failure(self, provider):
        """Test failed model undeployment."""
        with patch("httpx.AsyncClient.delete") as mock_delete:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_delete.return_value = mock_response

            result = await provider.undeploy_model("nonexistent-endpoint")

            assert result is False

    @pytest.mark.asyncio
    async def test_get_deployment_status_running(self, provider):
        """Test getting deployment status for running model."""
        mock_response_data = {"status": {"state": "Running"}}

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_get.return_value = mock_response

            status = await provider.get_deployment_status("test-endpoint")

            assert status == "running"

    @pytest.mark.asyncio
    async def test_get_deployment_status_failed(self, provider):
        """Test getting deployment status for failed model."""
        mock_response_data = {"status": {"state": "Failed"}}

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_get.return_value = mock_response

            status = await provider.get_deployment_status("test-endpoint")

            assert status == "failed"

    @pytest.mark.asyncio
    async def test_get_deployment_status_not_found(self, provider):
        """Test getting deployment status for non-existent endpoint."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            status = await provider.get_deployment_status("nonexistent-endpoint")

            assert status == "not_found"

    @pytest.mark.asyncio
    async def test_predict_success(self, provider):
        """Test successful model prediction."""
        mock_response_data = [{"generated_text": "Hello, how are you today?"}]

        inputs = {"inputs": "Hello"}

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_post.return_value = mock_response

            with patch("time.time", side_effect=[1000.0, 1000.15]):  # 150ms response time
                result = await provider.predict(
                    endpoint_url="https://test-endpoint.huggingface.co", inputs=inputs
                )

            assert result.success is True
            assert result.predictions == mock_response_data
            assert 140 <= result.response_time_ms <= 160  # Allow small variance
            assert result.error_message is None

    @pytest.mark.asyncio
    async def test_predict_failure(self, provider):
        """Test failed model prediction."""
        inputs = {"inputs": "Hello"}

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.json.return_value = {"error": "Invalid input format"}
            mock_post.return_value = mock_response

            with patch("time.time", side_effect=[1000.0, 1000.5]):  # 500ms response time
                result = await provider.predict(
                    endpoint_url="https://test-endpoint.huggingface.co", inputs=inputs
                )

            assert result.success is False
            assert result.predictions == []
            assert result.response_time_ms == 500
            assert "Invalid input format" in result.error_message

    @pytest.mark.asyncio
    async def test_predict_timeout(self, provider):
        """Test model prediction with timeout."""
        inputs = {"inputs": "Hello"}

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timeout")

            with patch("time.time", side_effect=[1000.0, 1035.0]):  # 35s timeout
                result = await provider.predict(
                    endpoint_url="https://test-endpoint.huggingface.co", inputs=inputs
                )

            assert result.success is False
            assert result.response_time_ms == 35000
            assert "Request timeout" in result.error_message

    def test_generate_endpoint_name(self, provider):
        """Test endpoint name generation."""
        name = provider._generate_endpoint_name("test-model-123")
        assert name.startswith("hokusai-model-")
        assert len(name) <= 32  # HuggingFace endpoint name limit
        # Name should be deterministic for the same input
        name2 = provider._generate_endpoint_name("test-model-123")
        assert name == name2

    def test_map_status_to_standard(self, provider):
        """Test status mapping from HuggingFace to standard format."""
        assert provider._map_status_to_standard("Running") == "running"
        assert provider._map_status_to_standard("Pending") == "deploying"
        assert provider._map_status_to_standard("Failed") == "failed"
        assert provider._map_status_to_standard("Stopped") == "stopped"
        assert provider._map_status_to_standard("Unknown") == "unknown"

    @pytest.mark.asyncio
    async def test_create_inference_endpoint_payload(self, provider):
        """Test creating inference endpoint payload."""
        payload = provider._create_inference_endpoint_payload(
            model_uri="microsoft/DialoGPT-medium",
            endpoint_name="test-endpoint",
            instance_type="cpu",
        )

        expected = {
            "repository": "microsoft/DialoGPT-medium",
            "name": "test-endpoint",
            "accelerator": "cpu",
            "instance_size": "small",
            "instance_type": "public",
            "region": "us-east-1",
            "vendor": "aws",
            "account_id": None,
            "task": "text-generation",
        }

        assert payload == expected

    def test_get_instance_size_mapping(self, provider):
        """Test instance size mapping."""
        assert provider._get_instance_size("cpu") == "small"
        assert provider._get_instance_size("gpu") == "medium"
        assert provider._get_instance_size("gpu-large") == "large"

    def test_get_headers(self, provider):
        """Test API headers generation."""
        headers = provider._get_headers()
        expected = {"Authorization": "Bearer hf_test_key", "Content-Type": "application/json"}
        assert headers == expected
