"""Unit tests for individual API endpoints.

This module provides focused unit tests for each API endpoint, testing
the endpoint logic in isolation with comprehensive mocking.
"""

import pytest
import json
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

from src.api.main import app


class TestHealthEndpointsUnit:
    """Unit tests for health endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def mock_dependencies(self):
        """Mock all external dependencies for unit testing."""
        with patch("src.api.routes.health.check_database_connection") as mock_db, \
             patch("src.api.routes.health.check_mlflow_connection") as mock_mlflow, \
             patch("src.api.routes.health.get_git_commit") as mock_git, \
             patch("src.api.routes.health._get_redis") as mock_redis, \
             patch("src.api.routes.health._get_psutil") as mock_psutil, \
             patch("src.utils.mlflow_config.get_mlflow_status") as mock_mlflow_status:
            
            # Setup default mocks
            mock_db.return_value = (True, None)
            mock_mlflow.return_value = (True, None)
            mock_git.return_value = "test_commit_hash"
            mock_psutil.return_value = Mock()
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED",
                "error": None
            }
            
            yield {
                "db": mock_db,
                "mlflow": mock_mlflow,
                "git": mock_git,
                "redis": mock_redis,
                "psutil": mock_psutil,
                "mlflow_status": mock_mlflow_status
            }

    def test_health_check_all_services_healthy(self, client, mock_dependencies):
        """Test health check when all services are healthy."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "postgres" in data["services"]
        assert "mlflow" in data["services"]

    def test_health_check_database_unhealthy(self, client, mock_dependencies):
        """Test health check when database is unhealthy."""
        mock_dependencies["db"].return_value = (False, "Connection failed")
        
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["unhealthy", "degraded"]
        assert data["services"]["postgres"] == "unhealthy"

    def test_health_check_mlflow_circuit_breaker_open(self, client, mock_dependencies):
        """Test health check when MLflow circuit breaker is open."""
        mock_dependencies["mlflow_status"].return_value = {
            "connected": False,
            "circuit_breaker_state": "OPEN",
            "error": "Circuit breaker open"
        }
        
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["services"]["mlflow"] == "degraded"

    def test_health_check_detailed_flag(self, client, mock_dependencies):
        """Test health check with detailed=true parameter."""
        response = client.get("/health?detailed=true")
        
        assert response.status_code == 200
        data = response.json()
        assert "system_info" in data
        # Should include detailed service information

    def test_readiness_check_all_ready(self, client, mock_dependencies):
        """Test readiness check when all services are ready."""
        response = client.get("/ready")
        
        assert response.status_code == 200
        data = response.json()
        assert "ready" in data
        assert "checks" in data
        assert isinstance(data["checks"], list)

    def test_readiness_check_database_not_ready(self, client, mock_dependencies):
        """Test readiness check when database is not ready."""
        mock_dependencies["db"].return_value = (False, "Database connection failed")
        
        response = client.get("/ready")
        
        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False
        assert data["can_serve_traffic"] is False

    def test_liveness_check(self, client, mock_dependencies):
        """Test liveness check always returns alive."""
        response = client.get("/live")
        
        assert response.status_code == 200
        data = response.json()
        assert data["alive"] is True
        assert "uptime" in data
        assert "memory_usage_mb" in data

    def test_version_info(self, client, mock_dependencies):
        """Test version information endpoint."""
        response = client.get("/version")
        
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1.0.0"
        assert data["git_commit"] == "test_commit_hash"
        assert "build_date" in data
        assert "api_version" in data

    def test_metrics_endpoint_prometheus(self, client, mock_dependencies):
        """Test metrics endpoint returns Prometheus format."""
        with patch("src.utils.prometheus_metrics.get_prometheus_metrics") as mock_prometheus:
            mock_prometheus.return_value = "# HELP requests_total Total requests\nrequests_total 100\n"
            
            response = client.get("/metrics")
            
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/plain"
            assert "requests_total" in response.text

    def test_metrics_endpoint_fallback(self, client, mock_dependencies):
        """Test metrics endpoint fallback when Prometheus not available."""
        with patch("src.utils.prometheus_metrics.get_prometheus_metrics", side_effect=ImportError):
            response = client.get("/metrics")
            
            assert response.status_code == 200
            # Should fall back to basic metrics
            assert response.headers["content-type"] == "application/json"

    def test_mlflow_health_endpoint_healthy(self, client, mock_dependencies):
        """Test MLflow health endpoint when healthy."""
        response = client.get("/health/mlflow")
        
        assert response.status_code == 200
        data = response.json()
        assert "connected" in data or "status" in data

    def test_mlflow_health_endpoint_circuit_breaker_open(self, client, mock_dependencies):
        """Test MLflow health endpoint when circuit breaker is open."""
        mock_dependencies["mlflow_status"].return_value = {
            "connected": False,
            "circuit_breaker_state": "OPEN",
            "error": "Circuit breaker open"
        }
        
        response = client.get("/health/mlflow")
        
        assert response.status_code == 503
        data = response.json()
        assert data["circuit_breaker_state"] == "OPEN"

    def test_mlflow_circuit_breaker_reset(self, client, mock_dependencies):
        """Test MLflow circuit breaker reset endpoint."""
        with patch("src.utils.mlflow_config.reset_circuit_breaker") as mock_reset:
            response = client.post("/health/mlflow/reset")
            
            assert response.status_code == 200
            data = response.json()
            assert "message" in data
            mock_reset.assert_called_once()

    def test_mlflow_circuit_breaker_reset_failure(self, client, mock_dependencies):
        """Test MLflow circuit breaker reset failure."""
        with patch("src.utils.mlflow_config.reset_circuit_breaker", side_effect=Exception("Reset failed")):
            response = client.post("/health/mlflow/reset")
            
            assert response.status_code == 500


class TestModelEndpointsUnit:
    """Unit tests for model endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_auth(self):
        """Mock authentication middleware."""
        with patch("src.middleware.auth.require_auth") as mock_auth:
            mock_auth.return_value = {"user_id": "test_user", "api_key_id": "test_key"}
            yield mock_auth

    @pytest.fixture
    def mock_registry(self):
        """Mock model registry."""
        with patch("src.api.routes.models.registry") as mock_reg:
            yield mock_reg

    @pytest.fixture
    def mock_mlflow(self):
        """Mock MLflow client."""
        with patch("src.api.routes.models.mlflow") as mock_mlflow:
            mock_client = Mock()
            mock_mlflow.tracking.MlflowClient.return_value = mock_client
            yield mock_client

    def test_list_models_no_filter(self, client, mock_mlflow):
        """Test listing models without name filter."""
        mock_mlflow.search_model_versions.return_value = [
            Mock(name="model1", version="1", status="READY", creation_timestamp=1234567890, tags={"key": "value"}),
            Mock(name="model2", version="1", status="READY", creation_timestamp=1234567891, tags={})
        ]
        
        response = client.get("/models/")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["models"]) == 2
        assert data["models"][0]["name"] == "model1"

    def test_list_models_with_name_filter(self, client, mock_mlflow):
        """Test listing models with name filter."""
        mock_mlflow.search_model_versions.return_value = [
            Mock(name="test_model", version="1", status="READY", creation_timestamp=1234567890, tags={})
        ]
        
        response = client.get("/models/?name=test_model")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["models"]) == 1
        mock_mlflow.search_model_versions.assert_called_with("name='test_model'")

    def test_list_models_mlflow_error(self, client, mock_mlflow):
        """Test listing models when MLflow throws error."""
        mock_mlflow.search_model_versions.side_effect = Exception("MLflow error")
        
        response = client.get("/models/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["models"] == []  # Should return empty list on error

    def test_get_model_by_id_success(self, client, mock_mlflow):
        """Test getting model by ID successfully."""
        mock_version = Mock()
        mock_version.name = "test_model"
        mock_version.version = "1"
        mock_version.status = "READY"
        mock_version.description = "Test description"
        mock_version.tags = {"env": "test"}
        
        mock_mlflow.get_model_version.return_value = mock_version
        
        response = client.get("/models/test_model/1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test_model"
        assert data["version"] == "1"
        assert data["description"] == "Test description"
        assert data["tags"] == {"env": "test"}

    def test_get_model_by_id_not_found(self, client, mock_mlflow):
        """Test getting model by ID when model not found."""
        mock_mlflow.get_model_version.side_effect = Exception("Model not found")
        
        response = client.get("/models/nonexistent/1")
        
        assert response.status_code == 404

    def test_get_model_lineage_success(self, client, mock_auth, mock_registry):
        """Test getting model lineage successfully."""
        mock_registry.get_model_lineage.return_value = [
            {"version": "1", "is_baseline": True, "metrics": {"accuracy": 0.85}},
            {"version": "2", "is_baseline": False, "metrics": {"accuracy": 0.87}}
        ]
        
        with patch("src.api.routes.models.require_auth", return_value=mock_auth.return_value):
            response = client.get("/models/test_model/lineage", headers={"X-API-Key": "test"})
            
            assert response.status_code == 200
            data = response.json()
            assert data["model_id"] == "test_model"
            assert len(data["lineage"]) == 2
            assert data["total_versions"] == 2

    def test_get_model_lineage_not_found(self, client, mock_auth, mock_registry):
        """Test getting lineage for non-existent model."""
        mock_registry.get_model_lineage.side_effect = ValueError("Model not found")
        
        with patch("src.api.routes.models.require_auth", return_value=mock_auth.return_value):
            response = client.get("/models/nonexistent/lineage", headers={"X-API-Key": "test"})
            
            assert response.status_code == 404

    def test_register_model_success(self, client, mock_auth, mock_registry):
        """Test successful model registration."""
        registration_data = {
            "model_name": "new_model",
            "model_type": "lead_scoring",
            "model_data": {"path": "s3://models/new_model.pkl"},
            "metadata": {"version": "1.0.0"}
        }
        
        mock_registry.register_baseline.return_value = {
            "model_id": "new_model/1",
            "model_name": "new_model",
            "version": "1",
            "registration_timestamp": "2024-01-01T00:00:00Z"
        }
        
        with patch("src.api.routes.models.require_auth", return_value=mock_auth.return_value):
            response = client.post("/models/register", json=registration_data, headers={"X-API-Key": "test"})
            
            assert response.status_code == 201
            data = response.json()
            assert data["model_id"] == "new_model/1"
            assert data["model_name"] == "new_model"

    def test_register_model_validation_error(self, client, mock_auth, mock_registry):
        """Test model registration with validation error."""
        mock_registry.register_baseline.side_effect = ValueError("Invalid model type")
        
        registration_data = {
            "model_name": "new_model",
            "model_type": "invalid_type",
            "model_data": {},
            "metadata": {}
        }
        
        with patch("src.api.routes.models.require_auth", return_value=mock_auth.return_value):
            response = client.post("/models/register", json=registration_data, headers={"X-API-Key": "test"})
            
            assert response.status_code == 422

    def test_update_model_metadata_success(self, client, mock_mlflow):
        """Test updating model metadata successfully."""
        update_data = {
            "description": "Updated description",
            "tags": {"env": "production"}
        }
        
        response = client.patch("/models/test_model/1", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Model updated successfully"
        
        # Verify calls to MLflow client
        mock_mlflow.update_model_version.assert_called_once()
        mock_mlflow.set_model_version_tag.assert_called()

    def test_delete_model_version_success(self, client, mock_mlflow):
        """Test deleting model version successfully."""
        response = client.delete("/models/test_model/1")
        
        assert response.status_code == 200
        data = response.json()
        assert "deleted successfully" in data["message"]
        mock_mlflow.delete_model_version.assert_called_once_with(name="test_model", version="1")

    def test_transition_model_stage_success(self, client, mock_mlflow):
        """Test model stage transition successfully."""
        transition_data = {
            "stage": "Production",
            "archive_existing": True
        }
        
        response = client.post("/models/test_model/1/transition", json=transition_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "transitioned to Production" in data["message"]
        mock_mlflow.transition_model_version_stage.assert_called_once()

    def test_compare_models_success(self, client):
        """Test model comparison successfully."""
        response = client.get("/models/compare?model1=model_a:1&model2=model_b:2")
        
        assert response.status_code == 200
        data = response.json()
        assert "model1" in data
        assert "model2" in data
        assert "delta" in data
        assert "recommendation" in data

    def test_compare_models_invalid_format(self, client):
        """Test model comparison with invalid model format."""
        response = client.get("/models/compare?model1=invalid_format&model2=also_invalid")
        
        assert response.status_code == 400
        assert "Invalid model format" in response.json()["detail"]

    def test_evaluate_model_success(self, client):
        """Test model evaluation successfully."""
        eval_request = {
            "model_name": "test_model",
            "model_version": "1",
            "metrics": ["accuracy", "precision"]
        }
        
        response = client.post("/models/evaluate", json=eval_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "test_model:1"
        assert "results" in data
        assert "accuracy" in data["results"]
        assert "precision" in data["results"]

    def test_get_model_metrics(self, client):
        """Test getting model metrics."""
        response = client.get("/models/test_model/1/metrics")
        
        assert response.status_code == 200
        data = response.json()
        assert "training_metrics" in data
        assert "validation_metrics" in data
        assert "production_metrics" in data

    def test_get_production_models(self, client, mock_registry):
        """Test getting production models."""
        mock_registry.get_production_models.return_value = [
            {"name": "prod_model_1", "version": "2", "stage": "Production"},
            {"name": "prod_model_2", "version": "1", "stage": "Production"}
        ]
        
        response = client.get("/models/production")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["models"]) == 2

    def test_batch_operations_success(self, client):
        """Test batch model operations."""
        batch_request = {
            "operations": [
                {"action": "archive", "model": "model1:1"},
                {"action": "promote", "model": "model2:2"}
            ]
        }
        
        response = client.post("/models/batch", json=batch_request)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        assert all(result["status"] == "success" for result in data["results"])

    def test_contributor_impact_valid_address(self, client, mock_auth):
        """Test contributor impact with valid Ethereum address."""
        valid_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f62341"
        
        with patch("src.api.routes.models.tracker") as mock_tracker:
            mock_tracker.get_contributor_impact.return_value = {
                "total_models_improved": 3,
                "total_improvement_score": 0.15,
                "contributions": [],
                "first_contribution": "2024-01-01T00:00:00Z",
                "last_contribution": "2024-01-31T00:00:00Z"
            }
            
            with patch("src.api.routes.models.require_auth", return_value=mock_auth.return_value):
                response = client.get(f"/models/contributors/{valid_address}/impact", headers={"X-API-Key": "test"})
                
                assert response.status_code == 200
                data = response.json()
                assert data["address"] == valid_address
                assert data["total_models_improved"] == 3

    def test_contributor_impact_invalid_address(self, client, mock_auth):
        """Test contributor impact with invalid Ethereum address."""
        invalid_address = "invalid_eth_address"
        
        with patch("src.api.routes.models.require_auth", return_value=mock_auth.return_value):
            response = client.get(f"/models/contributors/{invalid_address}/impact", headers={"X-API-Key": "test"})
            
            assert response.status_code == 400
            assert "Invalid Ethereum address" in response.json()["detail"]


class TestDSPyEndpointsUnit:
    """Unit tests for DSPy endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_auth(self):
        """Mock authentication."""
        with patch("src.api.routes.dspy.require_auth") as mock_auth:
            mock_auth.return_value = {"user_id": "test_user", "api_key_id": "test_key"}
            yield mock_auth

    @pytest.fixture
    def mock_executor(self):
        """Mock DSPy executor."""
        with patch("src.api.routes.dspy.get_executor") as mock_get_executor:
            mock_executor = Mock()
            mock_get_executor.return_value = mock_executor
            yield mock_executor

    def test_dspy_health_check(self, client, mock_executor):
        """Test DSPy health check endpoint."""
        mock_executor.get_execution_stats.return_value = {
            "total_executions": 100,
            "success_rate": 0.95
        }
        
        response = client.get("/api/v1/dspy/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["total_executions"] == 100
        assert data["success_rate"] == 0.95

    def test_dspy_health_check_error(self, client, mock_executor):
        """Test DSPy health check when executor fails."""
        mock_executor.get_execution_stats.side_effect = Exception("Executor error")
        
        response = client.get("/api/v1/dspy/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert "error" in data

    def test_execute_dspy_program_success(self, client, mock_auth, mock_executor):
        """Test successful DSPy program execution."""
        mock_result = Mock()
        mock_result.success = True
        mock_result.outputs = {"result": "Generated text"}
        mock_result.error = None
        mock_result.execution_time = 2.5
        mock_result.program_name = "text_generator"
        mock_result.metadata = {"version": "1.0"}
        
        mock_executor.execute.return_value = mock_result
        
        execution_request = {
            "program_id": "text_generator",
            "inputs": {"prompt": "Generate some text"},
            "mode": "normal"
        }
        
        response = client.post("/api/v1/dspy/execute", json=execution_request, headers={"X-API-Key": "test"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["outputs"] == {"result": "Generated text"}
        assert data["execution_time"] == 2.5
        assert "execution_id" in data

    def test_execute_dspy_program_failure(self, client, mock_auth, mock_executor):
        """Test DSPy program execution failure."""
        mock_result = Mock()
        mock_result.success = False
        mock_result.outputs = None
        mock_result.error = "Program execution failed"
        mock_result.execution_time = 0.5
        mock_result.program_name = "text_generator"
        mock_result.metadata = {}
        
        mock_executor.execute.return_value = mock_result
        
        execution_request = {
            "program_id": "text_generator",
            "inputs": {"prompt": "Generate some text"}
        }
        
        response = client.post("/api/v1/dspy/execute", json=execution_request, headers={"X-API-Key": "test"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Program execution failed"

    def test_execute_dspy_program_invalid_mode(self, client, mock_auth, mock_executor):
        """Test DSPy program execution with invalid mode."""
        execution_request = {
            "program_id": "text_generator",
            "inputs": {"prompt": "test"},
            "mode": "invalid_mode"
        }
        
        mock_executor.execute.side_effect = ValueError("Invalid execution mode")
        
        response = client.post("/api/v1/dspy/execute", json=execution_request, headers={"X-API-Key": "test"})
        
        assert response.status_code == 400

    def test_execute_dspy_batch_success(self, client, mock_auth, mock_executor):
        """Test successful DSPy batch execution."""
        mock_result1 = Mock()
        mock_result1.success = True
        mock_result1.outputs = {"result": "Output 1"}
        mock_result1.error = None
        mock_result1.execution_time = 1.0
        mock_result1.program_name = "test_program"
        mock_result1.metadata = {}
        
        mock_result2 = Mock()
        mock_result2.success = True
        mock_result2.outputs = {"result": "Output 2"}
        mock_result2.error = None
        mock_result2.execution_time = 1.2
        mock_result2.program_name = "test_program"
        mock_result2.metadata = {}
        
        mock_executor.execute_batch.return_value = [mock_result1, mock_result2]
        
        batch_request = {
            "program_id": "test_program",
            "inputs_list": [
                {"input": "text 1"},
                {"input": "text 2"}
            ]
        }
        
        response = client.post("/api/v1/dspy/execute/batch", json=batch_request, headers={"X-API-Key": "test"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["successful"] == 2
        assert data["failed"] == 0
        assert len(data["results"]) == 2

    def test_list_dspy_programs_success(self, client, mock_auth):
        """Test listing DSPy programs successfully."""
        with patch("src.services.model_registry.HokusaiModelRegistry") as mock_registry_class:
            mock_registry = Mock()
            mock_registry.list_models.return_value = [
                {
                    "id": "email_assistant",
                    "name": "Email Assistant",
                    "version": "1.0.0",
                    "signatures": [{"input": "context", "output": "email"}],
                    "description": "Generates professional emails"
                },
                {
                    "id": "text_summarizer",
                    "name": "Text Summarizer", 
                    "version": "2.0.0",
                    "signatures": [{"input": "text", "output": "summary"}],
                    "description": None
                }
            ]
            mock_registry_class.return_value = mock_registry
            
            response = client.get("/api/v1/dspy/programs", headers={"X-API-Key": "test"})
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["program_id"] == "email_assistant"
            assert data[0]["name"] == "Email Assistant"
            assert data[1]["program_id"] == "text_summarizer"

    def test_get_execution_stats_success(self, client, mock_auth, mock_executor):
        """Test getting DSPy execution statistics."""
        mock_executor.get_execution_stats.return_value = {
            "total_executions": 1000,
            "successful_executions": 950,
            "failed_executions": 50,
            "success_rate": 0.95,
            "avg_execution_time": 2.3,
            "last_24h_executions": 100
        }
        mock_executor.cache_enabled = True
        mock_executor.mlflow_tracking = True
        
        response = client.get("/api/v1/dspy/stats", headers={"X-API-Key": "test"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["statistics"]["total_executions"] == 1000
        assert data["statistics"]["success_rate"] == 0.95
        assert data["cache_enabled"] is True
        assert data["mlflow_tracking"] is True

    def test_clear_cache_success(self, client, mock_auth, mock_executor):
        """Test clearing DSPy cache successfully."""
        response = client.post("/api/v1/dspy/cache/clear", headers={"X-API-Key": "test"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Cache cleared successfully"
        mock_executor.clear_cache.assert_called_once()

    def test_clear_cache_failure(self, client, mock_auth, mock_executor):
        """Test clearing DSPy cache failure."""
        mock_executor.clear_cache.side_effect = Exception("Cache clear failed")
        
        response = client.post("/api/v1/dspy/cache/clear", headers={"X-API-Key": "test"})
        
        assert response.status_code == 500

    def test_get_execution_details_not_implemented(self, client, mock_auth):
        """Test getting execution details returns 501."""
        response = client.get("/api/v1/dspy/execution/test_execution_id", headers={"X-API-Key": "test"})
        
        assert response.status_code == 501
        data = response.json()
        assert "not yet implemented" in data["detail"]


class TestMLflowHealthEndpointsUnit:
    """Unit tests for MLflow health endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def mock_httpx(self):
        """Mock httpx for MLflow health checks."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.elapsed.total_seconds.return_value = 0.1
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.request.return_value = mock_response
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            
            mock_client.return_value = mock_client_instance
            yield mock_client_instance

    def test_mlflow_health_check_success(self, client, mock_httpx):
        """Test MLflow health check when server is healthy."""
        response = client.get("/api/health/mlflow")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "mlflow_server" in data
        assert "checks" in data

    def test_mlflow_health_check_server_down(self, client, mock_httpx):
        """Test MLflow health check when server is down."""
        mock_httpx.get.side_effect = Exception("Connection refused")
        
        response = client.get("/api/health/mlflow")
        
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"

    def test_mlflow_detailed_health_check(self, client, mock_httpx):
        """Test MLflow detailed health check."""
        response = client.get("/api/health/mlflow/detailed")
        
        assert response.status_code == 200
        data = response.json()
        assert "mlflow_server" in data
        assert "tests" in data
        assert "overall_health" in data
        assert isinstance(data["tests"], list)

    def test_mlflow_connectivity_check_success(self, client, mock_httpx):
        """Test MLflow connectivity check success."""
        response = client.get("/api/health/mlflow/connectivity")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"
        assert "response_time_ms" in data

    def test_mlflow_connectivity_check_timeout(self, client, mock_httpx):
        """Test MLflow connectivity check timeout."""
        import httpx
        mock_httpx.get.side_effect = httpx.TimeoutException("Timeout")
        
        response = client.get("/api/health/mlflow/connectivity")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "timeout"
        assert "error" in data


# Test utilities for response validation
class TestResponseValidation:
    """Unit tests for response validation and schemas."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_health_response_contains_required_fields(self, client):
        """Test health response contains all required fields."""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = ["status", "version", "services", "timestamp"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_model_list_response_structure(self, client):
        """Test model list response has correct structure."""
        response = client.get("/models/")
        assert response.status_code == 200
        
        data = response.json()
        assert "models" in data
        assert isinstance(data["models"], list)
        
        # If models exist, check structure
        if data["models"]:
            model = data["models"][0]
            expected_fields = ["name", "version", "status", "tags"]
            for field in expected_fields:
                assert field in model

    def test_error_response_structure(self, client):
        """Test error responses have consistent structure."""
        response = client.get("/nonexistent-endpoint")
        assert response.status_code == 404
        
        data = response.json()
        assert "detail" in data
        
    def test_json_content_type_headers(self, client):
        """Test that JSON endpoints return correct content-type."""
        json_endpoints = ["/health", "/ready", "/live", "/version"]
        
        for endpoint in json_endpoints:
            response = client.get(endpoint)
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type, f"Wrong content-type for {endpoint}: {content_type}"


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])