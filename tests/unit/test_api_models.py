"""Unit tests for API models endpoints."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
import json
from datetime import datetime

from src.api.routes.models import router
# Remove unused imports that don't exist


class TestModelsAPI:
    """Test suite for models API endpoints."""

    def setup_method(self):
        """Set up test fixtures."""
        from fastapi import FastAPI
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def test_list_models_endpoint(self):
        """Test list models endpoint."""
        with patch("src.api.routes.models.mlflow") as mock_mlflow:
            # Mock model versions
            mock_version1 = Mock()
            mock_version1.name = "EmailDraft"
            mock_version1.version = "1"
            mock_version1.status = "READY"
            mock_version1.creation_timestamp = 1000000

            mock_version2 = Mock()
            mock_version2.name = "SummarizeText"
            mock_version2.version = "2"
            mock_version2.status = "READY"
            mock_version2.creation_timestamp = 2000000

            mock_client = Mock()
            mock_client.search_model_versions.return_value = [mock_version1, mock_version2]
            mock_mlflow.tracking.MlflowClient.return_value = mock_client

            response = self.client.get("/models")

            assert response.status_code == 200
            data = response.json()
            assert len(data["models"]) == 2
            assert data["models"][0]["name"] == "EmailDraft"

    def test_list_models_with_filter(self):
        """Test list models with name filter."""
        with patch("src.api.routes.models.mlflow") as mock_mlflow:
            mock_version = Mock()
            mock_version.name = "EmailDraft"
            mock_version.version = "1"
            mock_version.status = "READY"
            mock_version.tags = {"category": "text_generation"}

            mock_client = Mock()
            mock_client.search_model_versions.return_value = [mock_version]
            mock_mlflow.tracking.MlflowClient.return_value = mock_client

            response = self.client.get("/models?name=EmailDraft")

            assert response.status_code == 200
            data = response.json()
            assert len(data["models"]) == 1
            assert data["models"][0]["name"] == "EmailDraft"

    def test_get_model_by_id(self):
        """Test get model by ID endpoint."""
        with patch("src.api.routes.models.mlflow") as mock_mlflow:
            mock_version = Mock()
            mock_version.name = "EmailDraft"
            mock_version.version = "1"
            mock_version.status = "READY"
            mock_version.description = "Email generation model"
            mock_version.tags = {"accuracy": "0.95"}

            mock_client = Mock()
            mock_client.get_model_version.return_value = mock_version
            mock_mlflow.tracking.MlflowClient.return_value = mock_client

            response = self.client.get("/models/EmailDraft/1")

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "EmailDraft"
            assert data["version"] == "1"
            assert data["description"] == "Email generation model"

    def test_get_model_not_found(self):
        """Test get model when not found."""
        with patch("src.api.routes.models.mlflow") as mock_mlflow:
            mock_client = Mock()
            mock_client.get_model_version.side_effect = Exception("Model not found")
            mock_mlflow.tracking.MlflowClient.return_value = mock_client

            response = self.client.get("/models/NonExistent/1")

            assert response.status_code == 404
            assert "Model not found" in response.json()["detail"]

    def test_register_model_endpoint(self):
        """Test register model endpoint."""
        with patch("src.api.routes.models.mlflow") as mock_mlflow:
            mock_client = Mock()
            mock_client.create_registered_model.return_value = Mock(name="NewModel")
            mock_client.create_model_version.return_value = Mock(
                name="NewModel",
                version="1",
                status="READY"
            )
            mock_mlflow.tracking.MlflowClient.return_value = mock_client

            request_data = {
                "name": "NewModel",
                "description": "A new model",
                "tags": {"type": "classification"},
                "model_uri": "runs:/abc123/model"
            }

            response = self.client.post("/models/register", json=request_data)

            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "NewModel"
            assert data["version"] == "1"

    def test_register_model_validation_error(self):
        """Test register model with validation error."""
        request_data = {
            "description": "Missing name field"
        }

        response = self.client.post("/models/register", json=request_data)

        assert response.status_code == 422

    def test_update_model_metadata(self):
        """Test update model metadata endpoint."""
        with patch("src.api.routes.models.mlflow") as mock_mlflow:
            mock_client = Mock()
            mock_mlflow.tracking.MlflowClient.return_value = mock_client

            update_data = {
                "description": "Updated description",
                "tags": {"accuracy": "0.97", "updated": "true"}
            }

            response = self.client.patch("/models/EmailDraft/1", json=update_data)

            assert response.status_code == 200
            assert response.json()["message"] == "Model updated successfully"

    def test_delete_model_version(self):
        """Test delete model version endpoint."""
        with patch("src.api.routes.models.mlflow") as mock_mlflow:
            mock_client = Mock()
            mock_mlflow.tracking.MlflowClient.return_value = mock_client

            response = self.client.delete("/models/EmailDraft/1")

            assert response.status_code == 200
            assert "deleted successfully" in response.json()["message"]

    def test_transition_model_stage(self):
        """Test transition model stage endpoint."""
        with patch("src.api.routes.models.mlflow") as mock_mlflow:
            mock_client = Mock()
            mock_mlflow.tracking.MlflowClient.return_value = mock_client

            transition_data = {
                "stage": "Production",
                "archive_existing": True
            }

            response = self.client.post(
                "/models/EmailDraft/1/transition",
                json=transition_data
            )

            assert response.status_code == 200
            assert "transitioned to Production" in response.json()["message"]

    def test_compare_models_endpoint(self):
        """Test compare models endpoint."""
        with patch("src.api.routes.models.ModelComparator") as mock_comparator_class:
            mock_comparator = Mock()
            mock_comparison = {
                "model1": {"name": "EmailDraft", "version": "1", "accuracy": 0.95},
                "model2": {"name": "EmailDraft", "version": "2", "accuracy": 0.97},
                "delta": {"accuracy": 0.02},
                "recommendation": "Use version 2"
            }
            mock_comparator.compare.return_value = mock_comparison
            mock_comparator_class.return_value = mock_comparator

            response = self.client.get("/models/compare?model1=EmailDraft:1&model2=EmailDraft:2")

            assert response.status_code == 200
            data = response.json()
            assert data["delta"]["accuracy"] == 0.02
            assert "recommendation" in data

    def test_evaluate_model_endpoint(self):
        """Test evaluate model endpoint."""
        with patch("src.api.routes.models.ModelEvaluator") as mock_evaluator_class:
            mock_evaluator = Mock()
            mock_results = {
                "accuracy": 0.95,
                "precision": 0.93,
                "recall": 0.97,
                "f1_score": 0.95
            }
            mock_evaluator.evaluate.return_value = mock_results
            mock_evaluator_class.return_value = mock_evaluator

            eval_request = {
                "model_name": "EmailDraft",
                "model_version": "1",
                "dataset_path": "/path/to/test/data",
                "metrics": ["accuracy", "precision", "recall", "f1_score"]
            }

            response = self.client.post("/models/evaluate", json=eval_request)

            assert response.status_code == 200
            data = response.json()
            assert data["results"]["accuracy"] == 0.95

    def test_model_lineage_endpoint(self):
        """Test model lineage endpoint."""
        with patch("src.api.routes.models.get_model_lineage") as mock_lineage:
            mock_lineage.return_value = {
                "model": "EmailDraft:1",
                "parents": ["EmailDraft:0"],
                "training_data": ["dataset_v1"],
                "experiments": ["exp_001"]
            }

            response = self.client.get("/models/EmailDraft/1/lineage")

            assert response.status_code == 200
            data = response.json()
            assert "parents" in data
            assert "training_data" in data

    def test_model_metrics_endpoint(self):
        """Test model metrics endpoint."""
        with patch("src.api.routes.models.get_model_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "training_metrics": {"loss": 0.05, "accuracy": 0.95},
                "validation_metrics": {"loss": 0.07, "accuracy": 0.93},
                "production_metrics": {"latency_ms": 25, "throughput_rps": 100}
            }

            response = self.client.get("/models/EmailDraft/1/metrics")

            assert response.status_code == 200
            data = response.json()
            assert "training_metrics" in data
            assert data["production_metrics"]["latency_ms"] == 25

    def test_download_model_endpoint(self):
        """Test download model endpoint."""
        with patch("src.api.routes.models.get_model_artifact_path") as mock_path:
            mock_path.return_value = "/tmp/model.pkl"

            with patch("src.api.routes.models.FileResponse") as mock_file_response:
                mock_file_response.return_value = Mock()

                response = self.client.get("/models/EmailDraft/1/download")

                assert response.status_code == 200

    def test_model_predictions_history(self):
        """Test model predictions history endpoint."""
        with patch("src.api.routes.models.get_predictions_history") as mock_history:
            mock_history.return_value = {
                "total_predictions": 10000,
                "date_range": {"start": "2024-01-01", "end": "2024-01-31"},
                "daily_counts": [{"date": "2024-01-01", "count": 350}]
            }

            response = self.client.get("/models/EmailDraft/1/predictions")

            assert response.status_code == 200
            data = response.json()
            assert data["total_predictions"] == 10000

    def test_batch_model_operations(self):
        """Test batch model operations endpoint."""
        with patch("src.api.routes.models.mlflow") as mock_mlflow:
            mock_client = Mock()
            mock_mlflow.tracking.MlflowClient.return_value = mock_client

            batch_request = {
                "operations": [
                    {"action": "tag", "model": "EmailDraft:1", "tags": {"tested": "true"}},
                    {"action": "transition", "model": "EmailDraft:2", "stage": "Staging"}
                ]
            }

            response = self.client.post("/models/batch", json=batch_request)

            assert response.status_code == 200
            data = response.json()
            assert len(data["results"]) == 2
