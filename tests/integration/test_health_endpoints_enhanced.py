"""
Enhanced integration tests for health endpoints.

Tests graceful degradation and all health check scenarios with real services.
"""

import pytest
import asyncio
import json
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routes.health import router
from src.utils.mlflow_config import reset_circuit_breaker


@pytest.fixture
def app():
    """Create FastAPI test app with health routes."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestHealthEndpointIntegration:
    """Integration tests for health endpoints with various service states."""
    
    def test_health_check_all_services_healthy(self, client):
        """Test health check when all services are healthy."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health.check_mlflow_connection') as mock_mlflow, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher:
            
            # Mock all services as healthy
            mock_db.return_value = (True, None)
            mock_mlflow.return_value = (True, None)
            
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.return_value = True
            mock_redis_module.return_value = mock_redis
            
            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg
            
            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}
            
            # Mock MLflow status
            with patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
                mock_mlflow_status.return_value = {
                    "connected": True,
                    "circuit_breaker_state": "CLOSED",
                    "error": None
                }
                
                response = client.get("/health")
                
                assert response.status_code == 200
                data = response.json()
                
                assert data["status"] == "healthy"
                assert data["services"]["mlflow"] == "healthy"
                assert data["services"]["redis"] == "healthy"
                assert data["services"]["postgres"] == "healthy"
                assert data["services"]["message_queue"] == "healthy"
                assert "timestamp" in data
                assert "version" in data
    
    def test_health_check_with_detailed_info(self, client):
        """Test health check with detailed parameter."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status, \
             patch('psutil.cpu_percent') as mock_cpu, \
             patch('psutil.virtual_memory') as mock_memory:
            
            # Setup mocks
            mock_db.return_value = (True, None)
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED",
                "tracking_uri": "http://localhost:5000",
                "response_time_ms": 45.2
            }
            
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.return_value = True
            mock_redis_module.return_value = mock_redis
            
            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg
            
            mock_publisher.return_value.health_check.return_value = {
                "status": "healthy",
                "queue_size": 5,
                "connection_pool_size": 10
            }
            
            mock_cpu.return_value = 25.5
            mock_memory.return_value = Mock(percent=45.2)
            
            response = client.get("/health?detailed=true")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "healthy"
            assert "system_info" in data
            assert data["system_info"]["cpu_percent"] == 25.5
            assert data["system_info"]["memory_percent"] == 45.2
            assert "mlflow_details" in data["services"]
            assert data["services"]["mlflow_details"]["tracking_uri"] == "http://localhost:5000"
    
    def test_health_check_mlflow_circuit_breaker_open(self, client):
        """Test health check when MLflow circuit breaker is open."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            # Setup other services as healthy
            mock_db.return_value = (True, None)
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.return_value = True
            mock_redis_module.return_value = mock_redis
            
            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg
            
            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}
            
            # MLflow circuit breaker is OPEN
            mock_mlflow_status.return_value = {
                "connected": False,
                "circuit_breaker_state": "OPEN",
                "error": "Circuit breaker is OPEN - MLflow unavailable (retry in 25s)",
                "can_retry_in_seconds": 25
            }
            
            response = client.get("/health?detailed=true")
            
            assert response.status_code == 200
            data = response.json()
            
            # Should be degraded due to MLflow circuit breaker
            assert data["status"] == "degraded"
            assert data["services"]["mlflow"] == "degraded"
            assert "Circuit breaker is open" in data["services"]["mlflow_details"]["degradation_reason"]
    
    def test_health_check_mlflow_circuit_breaker_half_open(self, client):
        """Test health check when MLflow circuit breaker is half-open."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            # Setup other services
            mock_db.return_value = (True, None)
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.return_value = True
            mock_redis_module.return_value = mock_redis
            
            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg
            
            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}
            
            # MLflow circuit breaker is HALF_OPEN
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "HALF_OPEN",
                "error": None
            }
            
            response = client.get("/health?detailed=true")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "degraded"
            assert data["services"]["mlflow"] == "recovering"
            assert "Circuit breaker is half-open" in data["services"]["mlflow_details"]["degradation_reason"]
    
    def test_health_check_multiple_services_unhealthy(self, client):
        """Test health check when multiple services are unhealthy."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            # Multiple services unhealthy
            mock_db.return_value = (False, "Connection timeout")
            mock_mlflow_status.return_value = {
                "connected": False,
                "circuit_breaker_state": "OPEN",
                "error": "MLflow server unreachable"
            }
            
            # Redis fails
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.side_effect = Exception("Redis connection failed")
            mock_redis_module.return_value = mock_redis
            
            # Postgres works
            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg
            
            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}
            
            response = client.get("/health")
            
            assert response.status_code == 200
            data = response.json()
            
            # Should be unhealthy with multiple failed services
            assert data["status"] == "unhealthy"
            assert data["services"]["redis"] == "unhealthy"
            assert data["services"]["mlflow"] == "degraded"
    
    def test_readiness_check_all_ready(self, client):
        """Test readiness check when all critical services are ready."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health.check_mlflow_connection') as mock_mlflow, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            mock_db.return_value = (True, None)
            mock_mlflow.return_value = (True, None)
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED"
            }
            
            response = client.get("/ready")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["ready"] is True
            assert data["can_serve_traffic"] is True
            assert data["degraded_mode"] is False
            
            # Check individual service checks
            db_check = next((check for check in data["checks"] if check["name"] == "database"), None)
            assert db_check is not None
            assert db_check["passed"] is True
            assert db_check["critical"] is True
    
    def test_readiness_check_database_down(self, client):
        """Test readiness check when critical database is down."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health.check_mlflow_connection') as mock_mlflow, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            mock_db.return_value = (False, "Database connection failed")
            mock_mlflow.return_value = (True, None)
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED"
            }
            
            response = client.get("/ready")
            
            # Should return 503 because database is critical
            assert response.status_code == 503
            data = response.json()
            
            assert data["ready"] is False
            assert data["can_serve_traffic"] is False  # Database is critical
            assert data["degraded_mode"] is False
    
    def test_readiness_check_mlflow_circuit_breaker_open(self, client):
        """Test readiness check when MLflow circuit breaker is open."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health.check_mlflow_connection') as mock_mlflow, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            mock_db.return_value = (True, None)
            mock_mlflow.return_value = (False, "Circuit breaker open")
            mock_mlflow_status.return_value = {
                "connected": False,
                "circuit_breaker_state": "OPEN"
            }
            
            response = client.get("/ready")
            
            # Should return 200 in degraded mode (can still serve some traffic)
            assert response.status_code == 200
            data = response.json()
            
            assert data["ready"] is False
            assert data["can_serve_traffic"] is True  # MLflow is not critical
            assert data["degraded_mode"] is True
            
            # Check MLflow-specific check
            mlflow_check = next((check for check in data["checks"] if check["name"] == "mlflow"), None)
            assert mlflow_check is not None
            assert mlflow_check["passed"] is False
            assert mlflow_check["critical"] is False
            assert mlflow_check.get("degraded_mode") is True
    
    def test_readiness_check_mlflow_half_open(self, client):
        """Test readiness check when MLflow circuit breaker is half-open."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health.check_mlflow_connection') as mock_mlflow, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            mock_db.return_value = (True, None)
            mock_mlflow.return_value = (True, None)
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "HALF_OPEN"
            }
            
            response = client.get("/ready")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["ready"] is True  # Half-open means recovering
            assert data["can_serve_traffic"] is True
            
            mlflow_check = next((check for check in data["checks"] if check["name"] == "mlflow"), None)
            assert mlflow_check["passed"] is True
            assert mlflow_check.get("recovering") is True
    
    def test_liveness_check(self, client):
        """Test liveness check endpoint."""
        with patch('src.api.routes.health.psutil') as mock_psutil:
            mock_process = Mock()
            mock_process.memory_info.return_value.rss = 1024 * 1024 * 100  # 100MB
            mock_psutil.Process.return_value = mock_process
            
            response = client.get("/live")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["alive"] is True
            assert data["memory_usage_mb"] == 100.0
            assert "uptime" in data
    
    def test_liveness_check_without_psutil(self, client):
        """Test liveness check when psutil is not available."""
        with patch('src.api.routes.health.psutil', None):
            response = client.get("/live")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["alive"] is True
            assert data["memory_usage_mb"] == 0
    
    def test_version_info(self, client):
        """Test version information endpoint."""
        with patch('src.api.routes.health.get_git_commit') as mock_git:
            mock_git.return_value = "abc123def"
            
            response = client.get("/version")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["version"] == "1.0.0"
            assert data["git_commit"] == "abc123def"
            assert data["api_version"] == "v1"
            assert "build_date" in data
    
    def test_mlflow_health_check_healthy(self, client):
        """Test MLflow-specific health check when healthy."""
        with patch('src.utils.mlflow_config.get_mlflow_status') as mock_status:
            mock_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED",
                "tracking_uri": "http://localhost:5000",
                "response_time_ms": 25.3
            }
            
            response = client.get("/health/mlflow")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["connected"] is True
            assert data["circuit_breaker_state"] == "CLOSED"
            assert "timestamp" in data
    
    def test_mlflow_health_check_circuit_breaker_open(self, client):
        """Test MLflow health check when circuit breaker is open."""
        with patch('src.utils.mlflow_config.get_mlflow_status') as mock_status:
            mock_status.return_value = {
                "connected": False,
                "circuit_breaker_state": "OPEN",
                "error": "Circuit breaker is OPEN",
                "can_retry_in_seconds": 15
            }
            
            response = client.get("/health/mlflow")
            
            # Should return 503 when circuit breaker is open
            assert response.status_code == 503
            data = response.json()
            
            assert data["connected"] is False
            assert data["circuit_breaker_state"] == "OPEN"
            assert "Circuit breaker is OPEN" in data["error"]
    
    def test_mlflow_health_check_exception(self, client):
        """Test MLflow health check when an exception occurs."""
        with patch('src.utils.mlflow_config.get_mlflow_status') as mock_status:
            mock_status.side_effect = Exception("MLflow connection error")
            
            response = client.get("/health/mlflow")
            
            assert response.status_code == 500
            data = response.json()
            
            assert data["connected"] is False
            assert data["circuit_breaker_state"] == "UNKNOWN"
            assert "MLflow connection error" in data["error"]
    
    def test_reset_mlflow_circuit_breaker(self, client):
        """Test manual reset of MLflow circuit breaker."""
        with patch('src.utils.mlflow_config.reset_circuit_breaker') as mock_reset:
            response = client.post("/health/mlflow/reset")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["message"] == "Circuit breaker reset successfully"
            assert data["reset_by"] == "manual_api_call"
            assert "timestamp" in data
            
            mock_reset.assert_called_once()
    
    def test_reset_mlflow_circuit_breaker_exception(self, client):
        """Test circuit breaker reset when an exception occurs."""
        with patch('src.utils.mlflow_config.reset_circuit_breaker') as mock_reset:
            mock_reset.side_effect = Exception("Reset failed")
            
            response = client.post("/health/mlflow/reset")
            
            assert response.status_code == 500
            data = response.json()
            
            assert "Reset failed" in data["detail"]
    
    def test_detailed_service_status(self, client):
        """Test comprehensive service status endpoint."""
        with patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status, \
             patch('src.utils.mlflow_config.get_circuit_breaker_status') as mock_cb_status, \
             patch('src.api.routes.health.health_check') as mock_health:
            
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED",
                "response_time_ms": 32.1
            }
            
            mock_cb_status.return_value = {
                "state": "CLOSED",
                "failure_count": 0,
                "consecutive_successes": 5
            }
            
            mock_health_response = Mock()
            mock_health_response.status = "healthy"
            mock_health_response.services = {
                "mlflow": "healthy",
                "redis": "healthy",
                "postgres": "healthy"
            }
            mock_health.return_value = mock_health_response
            
            response = client.get("/health/status")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["service_name"] == "hokusai-registry"
            assert data["api_version"] == "1.0.0"
            assert data["overall_health"] == "healthy"
            assert "mlflow" in data
            assert "circuit_breaker" in data["mlflow"]
            assert "timestamp" in data
    
    def test_metrics_endpoint_with_prometheus(self, client):
        """Test metrics endpoint with Prometheus metrics available."""
        with patch('src.utils.prometheus_metrics.get_prometheus_metrics') as mock_prometheus, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            mock_prometheus.return_value = """# HELP mlflow_connection_status MLflow connection status
# TYPE mlflow_connection_status gauge
mlflow_connection_status 1.0
# HELP mlflow_circuit_breaker_state MLflow circuit breaker state
# TYPE mlflow_circuit_breaker_state gauge
mlflow_circuit_breaker_state 0.0"""
            
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED"
            }
            
            response = client.get("/metrics")
            
            assert response.status_code == 200
            assert "mlflow_connection_status" in response.text
            assert "mlflow_circuit_breaker_state" in response.text
    
    def test_metrics_endpoint_fallback(self, client):
        """Test metrics endpoint fallback when Prometheus is unavailable."""
        with patch('src.utils.prometheus_metrics.get_prometheus_metrics') as mock_prometheus, \
             patch('src.api.routes.health.get_metrics') as mock_basic_metrics:
            
            mock_prometheus.side_effect = ImportError("prometheus_client not available")
            mock_basic_metrics.return_value = {
                "requests_total": 100,
                "requests_per_second": 5.2,
                "average_response_time_ms": 45.3
            }
            
            response = client.get("/metrics")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["requests_total"] == 100
            assert data["requests_per_second"] == 5.2


class TestHealthEndpointScenarios:
    """Test various real-world scenarios for health endpoints."""
    
    def test_gradual_service_degradation(self, client):
        """Test health reporting during gradual service degradation."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            # Stage 1: All healthy
            mock_db.return_value = (True, None)
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.return_value = True
            mock_redis_module.return_value = mock_redis
            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg
            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED"
            }
            
            response1 = client.get("/health")
            assert response1.json()["status"] == "healthy"
            
            # Stage 2: MLflow starts having issues
            mock_mlflow_status.return_value = {
                "connected": False,
                "circuit_breaker_state": "OPEN"
            }
            
            response2 = client.get("/health")
            assert response2.json()["status"] == "degraded"
            
            # Stage 3: Redis also fails
            mock_redis.Redis.return_value.ping.side_effect = Exception("Redis timeout")
            
            response3 = client.get("/health")
            assert response3.json()["status"] == "unhealthy"
    
    def test_service_recovery_sequence(self, client):
        """Test health reporting during service recovery."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            # Setup baseline services
            mock_db.return_value = (True, None)
            mock_redis = Mock()
            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg
            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}
            
            # Stage 1: MLflow and Redis both down
            mock_mlflow_status.return_value = {
                "connected": False,
                "circuit_breaker_state": "OPEN"
            }
            mock_redis.Redis.return_value.ping.side_effect = Exception("Redis down")
            mock_redis_module.return_value = mock_redis
            
            response1 = client.get("/health")
            assert response1.json()["status"] == "unhealthy"
            
            # Stage 2: Redis recovers
            mock_redis.Redis.return_value.ping.side_effect = None
            mock_redis.Redis.return_value.ping.return_value = True
            
            response2 = client.get("/health")
            assert response2.json()["status"] == "degraded"  # Still degraded due to MLflow
            
            # Stage 3: MLflow circuit breaker goes to HALF_OPEN
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "HALF_OPEN"
            }
            
            response3 = client.get("/health")
            assert response3.json()["status"] == "degraded"  # Still degraded, but recovering
            
            # Stage 4: MLflow fully recovers
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED"
            }
            
            response4 = client.get("/health")
            assert response4.json()["status"] == "healthy"
    
    def test_timeout_handling(self, client):
        """Test handling of service timeouts."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module:
            
            # Database times out
            mock_db.return_value = (False, "Connection timeout")
            
            # Redis times out
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.side_effect = Exception("Connection timeout")
            mock_redis_module.return_value = mock_redis
            
            # PostgreSQL times out
            mock_pg = Mock()
            mock_pg.connect.side_effect = Exception("Connection timeout")
            mock_pg_module.return_value = mock_pg
            
            response = client.get("/health?detailed=true")
            
            assert response.status_code == 200
            data = response.json()
            
            # Should handle timeouts gracefully
            assert data["status"] == "unhealthy"
            assert "timeout" in data["services"].get("redis_error", "").lower() or \
                   "timeout" in data["services"].get("postgres_error", "").lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])