"""Unit tests for API health endpoints."""

from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from src.api.routes.health import router


class TestHealthAPI:
    """Test suite for health API endpoints."""

    def setup_method(self):
        """Set up test fixtures."""
        from fastapi import FastAPI

        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    @patch("src.api.routes.health._get_psycopg2")
    @patch("src.api.routes.health._get_redis")
    @patch("src.api.routes.health._get_mlflow")
    def test_health_check_endpoint(self, mock_get_mlflow, mock_get_redis, mock_get_psycopg2):
        """Test basic health check endpoint."""
        # Mock all services as healthy
        mock_mlflow = Mock()
        mock_mlflow.get_tracking_uri.return_value = "sqlite:///mlflow.db"
        mock_get_mlflow.return_value = mock_mlflow
        
        mock_redis = Mock()
        mock_redis.Redis.return_value.ping.return_value = True
        mock_get_redis.return_value = mock_redis
        
        mock_psycopg2 = Mock()
        mock_psycopg2.connect.return_value.close.return_value = None
        mock_get_psycopg2.return_value = mock_psycopg2
        
        response = self.client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data

    @patch("src.api.routes.health._get_psycopg2")
    @patch("src.api.routes.health._get_redis")
    @patch("src.api.routes.health._get_mlflow")
    def test_health_check_with_mlflow_healthy(self, mock_get_mlflow, mock_get_redis, mock_get_psycopg2):
        """Test health check with healthy MLflow connection."""
        # Mock all services as healthy
        mock_mlflow = Mock()
        mock_mlflow.get_tracking_uri.return_value = "sqlite:///mlflow.db"
        mock_get_mlflow.return_value = mock_mlflow
        
        mock_redis = Mock()
        mock_redis.Redis.return_value.ping.return_value = True
        mock_get_redis.return_value = mock_redis
        
        mock_psycopg2 = Mock()
        mock_psycopg2.connect.return_value.close.return_value = None
        mock_get_psycopg2.return_value = mock_psycopg2

        response = self.client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["services"]["mlflow"] == "healthy"

    @patch("src.api.routes.health._get_psycopg2")
    @patch("src.api.routes.health._get_redis")
    @patch("src.api.routes.health._get_mlflow")
    def test_health_check_with_mlflow_unhealthy(self, mock_get_mlflow, mock_get_redis, mock_get_psycopg2):
        """Test health check with unhealthy MLflow connection."""
        # Mock MLflow connection failure, others healthy
        mock_mlflow = Mock()
        mock_mlflow.get_tracking_uri.side_effect = Exception("Connection failed")
        mock_get_mlflow.return_value = mock_mlflow
        
        mock_redis = Mock()
        mock_redis.Redis.return_value.ping.return_value = True
        mock_get_redis.return_value = mock_redis
        
        mock_psycopg2 = Mock()
        mock_psycopg2.connect.return_value.close.return_value = None
        mock_get_psycopg2.return_value = mock_psycopg2

        response = self.client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["services"]["mlflow"] == "unhealthy"

    def test_readiness_check(self):
        """Test readiness check endpoint."""
        response = self.client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert "checks" in data

    @patch("src.api.routes.health.check_database_connection")
    @patch("src.api.routes.health.check_mlflow_connection")
    def test_readiness_check_all_healthy(self, mock_mlflow_check, mock_db_check):
        """Test readiness with all services healthy."""
        mock_db_check.return_value = (True, None)
        mock_mlflow_check.return_value = (True, None)

        response = self.client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert all(check["passed"] for check in data["checks"])

    @patch("src.api.routes.health.check_database_connection")
    def test_readiness_check_database_unhealthy(self, mock_db_check):
        """Test readiness with database unhealthy."""
        mock_db_check.return_value = (False, "Connection timeout")

        response = self.client.get("/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False
        assert any(not check["passed"] for check in data["checks"] if check["name"] == "database")

    def test_liveness_check(self):
        """Test liveness check endpoint."""
        response = self.client.get("/live")

        assert response.status_code == 200
        data = response.json()
        assert data["alive"] is True
        assert "uptime" in data
        assert "memory_usage_mb" in data

    @patch("src.api.routes.health.psutil")
    def test_liveness_with_memory_info(self, mock_psutil):
        """Test liveness check with memory information."""
        # Mock memory info
        mock_memory = Mock()
        mock_memory.rss = 100 * 1024 * 1024  # 100 MB
        mock_process = Mock()
        mock_process.memory_info.return_value = mock_memory
        mock_psutil.Process.return_value = mock_process

        response = self.client.get("/live")

        assert response.status_code == 200
        data = response.json()
        assert data["memory_usage_mb"] == 100

    def test_version_endpoint(self):
        """Test version information endpoint."""
        response = self.client.get("/version")

        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "build_date" in data
        assert "git_commit" in data
        assert "api_version" in data

    @patch("src.api.routes.health.get_git_commit")
    def test_version_with_git_info(self, mock_git_commit):
        """Test version endpoint with git information."""
        mock_git_commit.return_value = "abc123def456"

        response = self.client.get("/version")

        assert response.status_code == 200
        data = response.json()
        assert data["git_commit"] == "abc123def456"

    def test_metrics_endpoint(self):
        """Test metrics endpoint."""
        response = self.client.get("/metrics")

        assert response.status_code == 200
        data = response.json()
        assert "requests_total" in data
        assert "requests_per_second" in data
        assert "average_response_time_ms" in data
        assert "active_connections" in data

    @patch("src.api.routes.health.get_metrics")
    def test_metrics_with_custom_data(self, mock_get_metrics):
        """Test metrics endpoint with custom metrics."""
        mock_metrics = {
            "requests_total": 1000,
            "requests_per_second": 10.5,
            "average_response_time_ms": 25.3,
            "active_connections": 5,
            "error_rate": 0.01,
        }
        mock_get_metrics.return_value = mock_metrics

        response = self.client.get("/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["requests_total"] == 1000
        assert data["error_rate"] == 0.01

    def test_debug_endpoint_disabled(self):
        """Test debug endpoint when disabled."""
        with patch("src.api.routes.health.DEBUG_MODE", False):
            response = self.client.get("/debug")

            assert response.status_code == 404

    def test_debug_endpoint_enabled(self):
        """Test debug endpoint when enabled."""
        with patch("src.api.routes.health.DEBUG_MODE", True):
            response = self.client.get("/debug")

            assert response.status_code == 200
            data = response.json()
            assert "environment" in data
            assert "configuration" in data
            assert "loaded_modules" in data

    def test_health_check_response_headers(self):
        """Test health check response headers."""
        response = self.client.get("/health")

        assert response.headers["content-type"] == "application/json"
        # x-response-time header would be added by middleware, not present in unit tests

    def test_health_check_with_detailed_flag(self):
        """Test health check with detailed flag."""
        response = self.client.get("/health?detailed=true")

        assert response.status_code == 200
        data = response.json()
        assert "services" in data
        assert "system_info" in data
        assert "cpu_percent" in data["system_info"]
        assert "memory_percent" in data["system_info"]

    @patch("src.api.routes.health.check_external_service")
    def test_health_check_external_service(self, mock_check_external):
        """Test health check with external service check."""
        mock_check_external.return_value = {"status": "healthy", "latency_ms": 15.2}

        response = self.client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "external_api" in data["services"]
        assert data["services"]["external_api"] == "healthy"
