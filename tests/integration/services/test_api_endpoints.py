"""Integration tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from src.api.main import app


class TestAPIEndpoints:
    """Integration tests for MLOps API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client for API."""
        return TestClient(app)
    
    @pytest.fixture
    def auth_headers(self):
        """Mock authentication headers."""
        return {"Authorization": "Bearer test_token"}
    
    @pytest.fixture
    def mock_registry(self):
        """Create mock model registry."""
        with patch('src.api.routes.models.HokusaiModelRegistry') as mock:
            yield mock.return_value
    
    @pytest.fixture
    def mock_tracker(self):
        """Create mock performance tracker."""
        with patch('src.api.routes.models.PerformanceTracker') as mock:
            yield mock.return_value
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
    
    def test_get_model_lineage_success(self, client, auth_headers, mock_registry):
        """Test successful model lineage retrieval."""
        # Mock lineage data
        mock_lineage = [
            {
                "version": "1",
                "is_baseline": True,
                "metrics": {"accuracy": 0.85}
            },
            {
                "version": "2",
                "is_baseline": False,
                "contributor": "0xABC123",
                "metrics": {"accuracy": 0.87},
                "improvements": {"accuracy": 0.02}
            }
        ]
        mock_registry.get_model_lineage.return_value = mock_lineage
        
        response = client.get("/models/test_model/lineage", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["lineage"]) == 2
        assert data["lineage"][0]["version"] == "1"
        assert data["lineage"][1]["contributor"] == "0xABC123"
    
    def test_get_model_lineage_not_found(self, client, auth_headers, mock_registry):
        """Test model lineage retrieval for non-existent model."""
        mock_registry.get_model_lineage.side_effect = ValueError("Model not found")
        
        response = client.get("/models/non_existent/lineage", headers=auth_headers)
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    def test_register_model_success(self, client, auth_headers, mock_registry):
        """Test successful model registration."""
        # Request data
        registration_data = {
            "model_name": "new_model",
            "model_type": "lead_scoring",
            "model_data": {"path": "s3://models/new_model.pkl"},
            "metadata": {
                "dataset": "training_v2",
                "version": "2.0.0"
            }
        }
        
        # Mock response
        mock_registry.register_baseline.return_value = {
            "model_id": "new_model/1",
            "model_name": "new_model",
            "version": "1"
        }
        
        response = client.post(
            "/models/register",
            json=registration_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["model_id"] == "new_model/1"
        assert data["status"] == "registered"
    
    def test_register_model_invalid_type(self, client, auth_headers):
        """Test model registration with invalid model type."""
        registration_data = {
            "model_name": "new_model",
            "model_type": "invalid_type",
            "model_data": {"path": "s3://models/new_model.pkl"},
            "metadata": {}
        }
        
        response = client.post(
            "/models/register",
            json=registration_data,
            headers=auth_headers
        )
        
        assert response.status_code == 422
    
    def test_get_contributor_impact_success(self, client, auth_headers, mock_tracker):
        """Test successful contributor impact retrieval."""
        contributor_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f62341"
        
        # Mock impact data
        mock_impact = {
            "total_models_improved": 5,
            "total_improvement_score": 0.15,
            "contributions": [
                {
                    "model_id": "model1/2",
                    "improvement": {"accuracy": 0.03},
                    "timestamp": "2024-01-01T00:00:00Z"
                },
                {
                    "model_id": "model2/3",
                    "improvement": {"accuracy": 0.02},
                    "timestamp": "2024-01-02T00:00:00Z"
                }
            ]
        }
        mock_tracker.get_contributor_impact.return_value = mock_impact
        
        response = client.get(
            f"/contributors/{contributor_address}/impact",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["address"] == contributor_address
        assert data["total_models_improved"] == 5
        assert len(data["contributions"]) == 2
    
    def test_get_contributor_impact_invalid_address(self, client, auth_headers):
        """Test contributor impact with invalid ETH address."""
        response = client.get(
            "/contributors/invalid_address/impact",
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "Invalid Ethereum address" in response.json()["detail"]
    
    def test_api_authentication_required(self, client):
        """Test that API endpoints require authentication."""
        # Test without auth headers
        response = client.get("/models/test_model/lineage")
        assert response.status_code == 401
        
        response = client.post("/models/register", json={})
        assert response.status_code == 401
        
        response = client.get("/contributors/0x123/impact")
        assert response.status_code == 401
    
    def test_rate_limiting(self, client, auth_headers):
        """Test API rate limiting."""
        # Make multiple rapid requests
        for i in range(101):  # Assuming rate limit is 100/minute
            response = client.get("/health", headers=auth_headers)
        
        # 101st request should be rate limited
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 429
        assert "rate limit" in response.json()["detail"].lower()
    
    def test_cors_headers(self, client):
        """Test CORS headers are properly set."""
        response = client.options("/health")
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers
    
    def test_openapi_documentation(self, client):
        """Test OpenAPI documentation endpoint."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        
        openapi_spec = response.json()
        assert openapi_spec["openapi"].startswith("3.")
        assert "paths" in openapi_spec
        assert "/models/{model_id}/lineage" in openapi_spec["paths"]
    
    @patch('src.api.routes.models.mlflow')
    def test_model_registration_with_mlflow_error(self, mock_mlflow, client, 
                                                 auth_headers, mock_registry):
        """Test model registration when MLflow fails."""
        mock_registry.register_baseline.side_effect = Exception("MLflow connection error")
        
        registration_data = {
            "model_name": "new_model",
            "model_type": "lead_scoring",
            "model_data": {"path": "s3://models/new_model.pkl"},
            "metadata": {}
        }
        
        response = client.post(
            "/models/register",
            json=registration_data,
            headers=auth_headers
        )
        
        assert response.status_code == 500
        assert "internal server error" in response.json()["detail"].lower()