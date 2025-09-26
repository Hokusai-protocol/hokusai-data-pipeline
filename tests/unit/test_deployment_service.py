"""Tests for deployment service."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from src.database.deployed_models import DeployedModel, DeployedModelStatus
from src.services.deployment_service import DeploymentService
from src.services.providers.base_provider import (
    BaseProvider,
    DeploymentResult,
    PredictionResult,
    ProviderConfig,
)
from src.services.providers.provider_registry import ProviderRegistry


class TestDeploymentService:
    """Test deployment service functionality."""

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        return Mock(spec=Session)

    @pytest.fixture
    def mock_provider_registry(self):
        """Create mock provider registry."""
        registry = Mock(spec=ProviderRegistry)
        return registry

    @pytest.fixture
    def mock_provider(self):
        """Create mock provider."""
        provider = Mock(spec=BaseProvider)
        provider.provider_name = "huggingface"
        return provider

    @pytest.fixture
    def provider_config(self):
        """Create test provider configuration."""
        return ProviderConfig(
            provider_name="huggingface",
            credentials={"api_key": "test-key"},
            default_instance_type="cpu",
        )

    @pytest.fixture
    def deployment_service(self, mock_db_session, mock_provider_registry):
        """Create deployment service instance."""
        return DeploymentService(
            db_session=mock_db_session, provider_registry=mock_provider_registry
        )

    def test_deployment_service_initialization(
        self, deployment_service, mock_db_session, mock_provider_registry
    ):
        """Test deployment service initialization."""
        assert deployment_service.db_session == mock_db_session
        assert deployment_service.provider_registry == mock_provider_registry

    @pytest.mark.asyncio
    async def test_deploy_model_success(
        self,
        deployment_service,
        mock_provider,
        provider_config,
        mock_db_session,
        mock_provider_registry,
    ):
        """Test successful model deployment."""
        model_id = str(uuid4())
        model_uri = "microsoft/DialoGPT-medium"

        # Mock provider registry
        mock_provider_registry.get_provider.return_value = mock_provider

        # Mock successful deployment
        deployment_result = DeploymentResult(
            success=True,
            endpoint_url="https://test-endpoint.huggingface.co",
            provider_model_id="test-endpoint-123",
            metadata={"instance_type": "cpu"},
        )
        mock_provider.deploy_model = AsyncMock(return_value=deployment_result)

        # Mock database operations
        mock_deployed_model = Mock(spec=DeployedModel)
        deployed_model_id = uuid4()
        mock_deployed_model.id = deployed_model_id
        mock_db_session.add = Mock()
        mock_db_session.commit = Mock()

        # Use side_effect to return our mock model on add
        def add_side_effect(model):
            # Set the ID on the model that gets added
            model.id = deployed_model_id
            return model

        mock_db_session.add.side_effect = add_side_effect

        # Execute deployment
        result = await deployment_service.deploy_model(
            model_id=model_id,
            model_uri=model_uri,
            provider_name="huggingface",
            provider_config=provider_config,
            instance_type="cpu",
        )

        # Verify results
        assert result["success"] is True
        assert result["deployed_model_id"] == str(deployed_model_id)
        assert result["endpoint_url"] == "https://test-endpoint.huggingface.co"
        assert result["provider_model_id"] == "test-endpoint-123"

        # Verify provider was called
        mock_provider.deploy_model.assert_called_once_with(
            model_id=model_id, model_uri=model_uri, instance_type="cpu"
        )

        # Verify database operations
        mock_db_session.add.assert_called()
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_deploy_model_failure(
        self,
        deployment_service,
        mock_provider,
        provider_config,
        mock_db_session,
        mock_provider_registry,
    ):
        """Test failed model deployment."""
        model_id = str(uuid4())
        model_uri = "invalid/model"

        # Mock provider registry
        mock_provider_registry.get_provider.return_value = mock_provider

        # Mock failed deployment
        deployment_result = DeploymentResult(
            success=False, error_message="Invalid model repository"
        )
        mock_provider.deploy_model = AsyncMock(return_value=deployment_result)

        # Mock database operations
        mock_db_session.add = Mock()
        mock_db_session.commit = Mock()

        # Execute deployment
        result = await deployment_service.deploy_model(
            model_id=model_id,
            model_uri=model_uri,
            provider_name="huggingface",
            provider_config=provider_config,
            instance_type="cpu",
        )

        # Verify results
        assert result["success"] is False
        assert result["error_message"] == "Invalid model repository"

        # Verify database operations (should still create record with failed status)
        mock_db_session.add.assert_called()
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_deploy_model_provider_not_found(
        self, deployment_service, mock_provider_registry
    ):
        """Test deployment with non-existent provider."""
        model_id = str(uuid4())
        provider_config = ProviderConfig(provider_name="nonexistent", credentials={})

        # Mock provider registry error
        mock_provider_registry.get_provider.side_effect = ValueError(
            "Provider 'nonexistent' not found"
        )

        result = await deployment_service.deploy_model(
            model_id=model_id,
            model_uri="test/model",
            provider_name="nonexistent",
            provider_config=provider_config,
        )

        assert result["success"] is False
        assert "Provider 'nonexistent' not found" in result["error_message"]

    @pytest.mark.asyncio
    async def test_undeploy_model_success(
        self, deployment_service, mock_provider, mock_db_session, mock_provider_registry
    ):
        """Test successful model undeployment."""
        deployed_model_id = uuid4()
        provider_model_id = "test-endpoint-123"

        # Mock database query
        mock_deployed_model = Mock(spec=DeployedModel)
        mock_deployed_model.id = deployed_model_id
        mock_deployed_model.provider_model_id = provider_model_id
        mock_deployed_model.provider = "huggingface"
        mock_deployed_model.status = DeployedModelStatus.DEPLOYED
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_deployed_model
        )

        # Mock provider registry
        provider_config = ProviderConfig(
            provider_name="huggingface", credentials={"api_key": "test"}
        )
        mock_provider_registry.get_provider.return_value = mock_provider

        # Mock successful undeployment
        mock_provider.undeploy_model = AsyncMock(return_value=True)

        # Execute undeployment
        result = await deployment_service.undeploy_model(
            deployed_model_id=str(deployed_model_id),
            provider_configs={"huggingface": provider_config},
        )

        # Verify results
        assert result["success"] is True
        assert mock_deployed_model.status == DeployedModelStatus.STOPPED

        # Verify provider was called
        mock_provider.undeploy_model.assert_called_once_with(provider_model_id)

        # Verify database commit
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_undeploy_model_not_found(self, deployment_service, mock_db_session):
        """Test undeployment of non-existent model."""
        deployed_model_id = str(uuid4())

        # Mock database query returning None
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = None

        result = await deployment_service.undeploy_model(
            deployed_model_id=deployed_model_id, provider_configs={}
        )

        assert result["success"] is False
        assert "not found" in result["error_message"]

    @pytest.mark.asyncio
    async def test_get_deployment_status_success(
        self, deployment_service, mock_provider, mock_db_session, mock_provider_registry
    ):
        """Test getting deployment status."""
        deployed_model_id = uuid4()
        provider_model_id = "test-endpoint-123"

        # Mock database query
        mock_deployed_model = Mock(spec=DeployedModel)
        mock_deployed_model.id = deployed_model_id
        mock_deployed_model.provider_model_id = provider_model_id
        mock_deployed_model.provider = "huggingface"
        mock_deployed_model.status = DeployedModelStatus.DEPLOYED
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_deployed_model
        )

        # Mock provider registry
        provider_config = ProviderConfig(
            provider_name="huggingface", credentials={"api_key": "test"}
        )
        mock_provider_registry.get_provider.return_value = mock_provider

        # Mock provider status check
        mock_provider.get_deployment_status = AsyncMock(return_value="running")

        # Execute status check
        result = await deployment_service.get_deployment_status(
            deployed_model_id=str(deployed_model_id),
            provider_configs={"huggingface": provider_config},
        )

        # Verify results
        assert result["success"] is True
        assert result["status"] == "running"
        assert result["provider_status"] == "running"
        assert result["database_status"] == "deployed"

        # Verify provider was called
        mock_provider.get_deployment_status.assert_called_once_with(provider_model_id)

    @pytest.mark.asyncio
    async def test_predict_success(
        self, deployment_service, mock_provider, mock_db_session, mock_provider_registry
    ):
        """Test successful model prediction."""
        deployed_model_id = uuid4()
        endpoint_url = "https://test-endpoint.huggingface.co"
        inputs = {"inputs": "Hello, world!"}

        # Mock database query
        mock_deployed_model = Mock(spec=DeployedModel)
        mock_deployed_model.id = deployed_model_id
        mock_deployed_model.endpoint_url = endpoint_url
        mock_deployed_model.provider = "huggingface"
        mock_deployed_model.status = DeployedModelStatus.DEPLOYED
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_deployed_model
        )

        # Mock provider registry
        provider_config = ProviderConfig(
            provider_name="huggingface", credentials={"api_key": "test"}
        )
        mock_provider_registry.get_provider.return_value = mock_provider

        # Mock successful prediction
        prediction_result = PredictionResult(
            success=True,
            predictions=[{"generated_text": "Hello, how are you?"}],
            response_time_ms=150,
        )
        mock_provider.predict = AsyncMock(return_value=prediction_result)

        # Execute prediction
        result = await deployment_service.predict(
            deployed_model_id=str(deployed_model_id),
            inputs=inputs,
            provider_configs={"huggingface": provider_config},
        )

        # Verify results
        assert result["success"] is True
        assert result["predictions"] == [{"generated_text": "Hello, how are you?"}]
        assert result["response_time_ms"] == 150

        # Verify provider was called
        mock_provider.predict.assert_called_once_with(endpoint_url=endpoint_url, inputs=inputs)

    @pytest.mark.asyncio
    async def test_predict_model_not_deployed(self, deployment_service, mock_db_session):
        """Test prediction on non-deployed model."""
        deployed_model_id = uuid4()

        # Mock database query
        mock_deployed_model = Mock(spec=DeployedModel)
        mock_deployed_model.status = DeployedModelStatus.PENDING
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_deployed_model
        )

        result = await deployment_service.predict(
            deployed_model_id=str(deployed_model_id), inputs={"inputs": "test"}, provider_configs={}
        )

        assert result["success"] is False
        assert "not deployed" in result["error_message"]

    def test_list_deployed_models(self, deployment_service, mock_db_session):
        """Test listing deployed models."""
        # Mock database query
        mock_models = [
            Mock(
                spec=DeployedModel,
                id=uuid4(),
                model_id="model-1",
                status=DeployedModelStatus.DEPLOYED,
            ),
            Mock(
                spec=DeployedModel,
                id=uuid4(),
                model_id="model-2",
                status=DeployedModelStatus.PENDING,
            ),
        ]
        for model in mock_models:
            model.to_dict = Mock(
                return_value={
                    "id": str(model.id),
                    "model_id": model.model_id,
                    "status": model.status.value,
                }
            )

        mock_db_session.query.return_value.all.return_value = mock_models

        result = deployment_service.list_deployed_models()

        assert len(result) == 2
        assert result[0]["model_id"] == "model-1"
        assert result[1]["model_id"] == "model-2"

    def test_list_deployed_models_by_status(self, deployment_service, mock_db_session):
        """Test listing deployed models filtered by status."""
        # Mock database query with filter
        mock_models = [
            Mock(
                spec=DeployedModel,
                id=uuid4(),
                model_id="model-1",
                status=DeployedModelStatus.DEPLOYED,
            )
        ]
        mock_models[0].to_dict = Mock(
            return_value={"id": str(mock_models[0].id), "model_id": "model-1", "status": "deployed"}
        )

        mock_db_session.query.return_value.filter_by.return_value.all.return_value = mock_models

        result = deployment_service.list_deployed_models(status=DeployedModelStatus.DEPLOYED)

        assert len(result) == 1
        assert result[0]["status"] == "deployed"

        # Verify filter was applied
        mock_db_session.query.return_value.filter_by.assert_called_with(
            status=DeployedModelStatus.DEPLOYED
        )

    def test_get_deployed_model_info(self, deployment_service, mock_db_session):
        """Test getting deployed model information."""
        deployed_model_id = uuid4()

        # Mock database query
        mock_deployed_model = Mock(spec=DeployedModel)
        mock_deployed_model.id = deployed_model_id
        mock_deployed_model.to_dict = Mock(
            return_value={
                "id": str(deployed_model_id),
                "model_id": "test-model",
                "status": "deployed",
            }
        )
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_deployed_model
        )

        result = deployment_service.get_deployed_model_info(str(deployed_model_id))

        assert result is not None
        assert result["id"] == str(deployed_model_id)
        assert result["model_id"] == "test-model"

    def test_get_deployed_model_info_not_found(self, deployment_service, mock_db_session):
        """Test getting non-existent deployed model information."""
        deployed_model_id = str(uuid4())

        # Mock database query returning None
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = None

        result = deployment_service.get_deployed_model_info(deployed_model_id)

        assert result is None
