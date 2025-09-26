"""Tests for prediction API endpoints."""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.predict import router
from src.services.deployment_service import DeploymentService
from src.services.providers.base_provider import ProviderConfig

# Create test app
app = FastAPI()
app.include_router(router)


class TestPredictionEndpoints:
    """Test prediction API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_deployment_service(self):
        """Create mock deployment service."""
        return Mock(spec=DeploymentService)

    @pytest.fixture
    def provider_configs(self):
        """Create test provider configurations."""
        return {
            "huggingface": ProviderConfig(
                provider_name="huggingface", credentials={"api_key": "test-key"}
            )
        }

    def test_predict_success(self, client, mock_deployment_service, provider_configs):
        """Test successful prediction."""
        deployed_model_id = str(uuid4())
        inputs = {"text": "Hello, world!"}

        # Mock successful prediction
        predict_result = {
            "success": True,
            "predictions": [{"generated_text": "Hello, how are you today?"}],
            "response_time_ms": 150,
            "error_message": None,
            "metadata": {"model_version": "v1.0"},
        }
        mock_deployment_service.predict = AsyncMock(return_value=predict_result)

        with patch(
            "src.api.routes.predict.get_deployment_service", return_value=mock_deployment_service
        ):
            with patch(
                "src.api.routes.predict.get_provider_configs", return_value=provider_configs
            ):
                response = client.post(
                    f"/api/v1/models/{deployed_model_id}/predict",
                    json=inputs,
                    headers={"Authorization": "Bearer test-token"},
                )

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["success"] is True
        assert response_data["predictions"] == [{"generated_text": "Hello, how are you today?"}]
        assert response_data["response_time_ms"] == 150

        # Verify service was called correctly
        mock_deployment_service.predict.assert_called_once_with(
            deployed_model_id=deployed_model_id, inputs=inputs, provider_configs=provider_configs
        )

    def test_predict_failure(self, client, mock_deployment_service, provider_configs):
        """Test failed prediction."""
        deployed_model_id = str(uuid4())
        inputs = {"text": "Hello, world!"}

        # Mock failed prediction
        predict_result = {
            "success": False,
            "predictions": [],
            "response_time_ms": 500,
            "error_message": "Model inference failed: timeout",
            "metadata": {},
        }
        mock_deployment_service.predict = AsyncMock(return_value=predict_result)

        with patch(
            "src.api.routes.predict.get_deployment_service", return_value=mock_deployment_service
        ):
            with patch(
                "src.api.routes.predict.get_provider_configs", return_value=provider_configs
            ):
                response = client.post(
                    f"/api/v1/models/{deployed_model_id}/predict",
                    json=inputs,
                    headers={"Authorization": "Bearer test-token"},
                )

        assert response.status_code == 400
        response_data = response.json()
        assert response_data["success"] is False
        assert "Model inference failed: timeout" in response_data["error_message"]

    def test_predict_model_not_found(self, client, mock_deployment_service, provider_configs):
        """Test prediction for non-existent model."""
        deployed_model_id = str(uuid4())
        inputs = {"text": "Hello, world!"}

        # Mock model not found
        predict_result = {
            "success": False,
            "error_message": f"Deployed model {deployed_model_id} not found",
        }
        mock_deployment_service.predict = AsyncMock(return_value=predict_result)

        with patch(
            "src.api.routes.predict.get_deployment_service", return_value=mock_deployment_service
        ):
            with patch(
                "src.api.routes.predict.get_provider_configs", return_value=provider_configs
            ):
                response = client.post(
                    f"/api/v1/models/{deployed_model_id}/predict",
                    json=inputs,
                    headers={"Authorization": "Bearer test-token"},
                )

        assert response.status_code == 404
        response_data = response.json()
        assert response_data["success"] is False
        assert "not found" in response_data["error_message"]

    def test_predict_invalid_uuid(self, client):
        """Test prediction with invalid UUID."""
        response = client.post(
            "/api/v1/models/invalid-uuid/predict",
            json={"text": "Hello, world!"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422  # Validation error

    def test_predict_missing_inputs(self, client):
        """Test prediction with missing inputs."""
        deployed_model_id = str(uuid4())

        response = client.post(
            f"/api/v1/models/{deployed_model_id}/predict",
            json={},  # Empty JSON
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422  # Validation error

    def test_predict_without_auth(self, client):
        """Test prediction without authentication."""
        deployed_model_id = str(uuid4())

        response = client.post(
            f"/api/v1/models/{deployed_model_id}/predict",
            json={"text": "Hello, world!"},
            # No Authorization header
        )

        assert response.status_code == 401  # Unauthorized

    def test_get_model_info_success(self, client, mock_deployment_service):
        """Test getting model information."""
        deployed_model_id = str(uuid4())

        # Mock model info
        model_info = {
            "id": str(deployed_model_id),
            "model_id": "test-model-123",
            "provider": "huggingface",
            "status": "deployed",
            "endpoint_url": "https://test-endpoint.huggingface.co",
            "instance_type": "cpu",
            "created_at": "2023-01-01T00:00:00Z",
        }
        mock_deployment_service.get_deployed_model_info = Mock(return_value=model_info)

        with patch(
            "src.api.routes.predict.get_deployment_service", return_value=mock_deployment_service
        ):
            response = client.get(
                f"/api/v1/models/{deployed_model_id}",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["id"] == str(deployed_model_id)
        assert response_data["status"] == "deployed"
        assert response_data["provider"] == "huggingface"

    def test_get_model_info_not_found(self, client, mock_deployment_service):
        """Test getting non-existent model information."""
        deployed_model_id = str(uuid4())

        # Mock model not found
        mock_deployment_service.get_deployed_model_info = Mock(return_value=None)

        with patch(
            "src.api.routes.predict.get_deployment_service", return_value=mock_deployment_service
        ):
            response = client.get(
                f"/api/v1/models/{deployed_model_id}",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 404

    def test_list_models(self, client, mock_deployment_service):
        """Test listing deployed models."""
        # Mock model list
        model_list = [
            {
                "id": str(uuid4()),
                "model_id": "model-1",
                "provider": "huggingface",
                "status": "deployed",
            },
            {
                "id": str(uuid4()),
                "model_id": "model-2",
                "provider": "huggingface",
                "status": "pending",
            },
        ]
        mock_deployment_service.list_deployed_models = Mock(return_value=model_list)

        with patch(
            "src.api.routes.predict.get_deployment_service", return_value=mock_deployment_service
        ):
            response = client.get("/api/v1/models", headers={"Authorization": "Bearer test-token"})

        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data["models"]) == 2
        assert response_data["models"][0]["model_id"] == "model-1"
        assert response_data["models"][1]["model_id"] == "model-2"

    def test_list_models_with_status_filter(self, client, mock_deployment_service):
        """Test listing deployed models with status filter."""
        # Mock filtered model list
        model_list = [
            {
                "id": str(uuid4()),
                "model_id": "model-1",
                "provider": "huggingface",
                "status": "deployed",
            }
        ]
        mock_deployment_service.list_deployed_models = Mock(return_value=model_list)

        with patch(
            "src.api.routes.predict.get_deployment_service", return_value=mock_deployment_service
        ):
            with patch("src.database.deployed_models.DeployedModelStatus") as mock_status:
                mock_status.DEPLOYED = "deployed"
                response = client.get(
                    "/api/v1/models?status=deployed", headers={"Authorization": "Bearer test-token"}
                )

        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data["models"]) == 1
        assert response_data["models"][0]["status"] == "deployed"

    def test_get_model_status(self, client, mock_deployment_service, provider_configs):
        """Test getting model deployment status."""
        deployed_model_id = str(uuid4())

        # Mock status response
        status_result = {
            "success": True,
            "status": "running",
            "database_status": "deployed",
            "provider_status": "running",
        }
        mock_deployment_service.get_deployment_status = AsyncMock(return_value=status_result)

        with patch(
            "src.api.routes.predict.get_deployment_service", return_value=mock_deployment_service
        ):
            with patch(
                "src.api.routes.predict.get_provider_configs", return_value=provider_configs
            ):
                response = client.get(
                    f"/api/v1/models/{deployed_model_id}/status",
                    headers={"Authorization": "Bearer test-token"},
                )

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["success"] is True
        assert response_data["status"] == "running"
        assert response_data["database_status"] == "deployed"
        assert response_data["provider_status"] == "running"

    def test_get_model_status_not_found(self, client, mock_deployment_service, provider_configs):
        """Test getting status for non-existent model."""
        deployed_model_id = str(uuid4())

        # Mock model not found
        status_result = {
            "success": False,
            "error_message": f"Deployed model {deployed_model_id} not found",
        }
        mock_deployment_service.get_deployment_status = AsyncMock(return_value=status_result)

        with patch(
            "src.api.routes.predict.get_deployment_service", return_value=mock_deployment_service
        ):
            with patch(
                "src.api.routes.predict.get_provider_configs", return_value=provider_configs
            ):
                response = client.get(
                    f"/api/v1/models/{deployed_model_id}/status",
                    headers={"Authorization": "Bearer test-token"},
                )

        assert response.status_code == 404
        response_data = response.json()
        assert response_data["success"] is False
        assert "not found" in response_data["error_message"]
