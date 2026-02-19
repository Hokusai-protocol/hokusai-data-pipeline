"""Tests for API endpoint migration to match documentation."""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


# Mock external services to prevent timeouts
@pytest.fixture(autouse=True)
def mock_external_services():
    """Mock external services for all tests."""
    with (
        patch("src.api.routes.health.check_database_connection") as mock_pg,
        patch("src.api.routes.health.check_redis_connection") as mock_redis,
        patch("src.api.routes.health.check_mlflow_connection") as mock_mlflow,
        patch("src.utils.mlflow_config.get_mlflow_status") as mock_mlflow_status,
        patch("src.api.routes.health._get_redis") as mock_get_redis,
        patch("src.api.routes.health._get_psycopg2") as mock_get_psycopg2,
        patch("src.events.publishers.factory.get_publisher") as mock_get_publisher,
        patch("src.middleware.auth.APIKeyAuthMiddleware.validate_with_auth_service") as mock_auth,
        patch("src.api.routes.dspy.get_executor") as mock_dspy_executor,
    ):
        # Mock health check functions
        mock_pg.return_value = (True, None)  # Returns tuple (success, error_message)
        mock_redis.return_value = (True, "Redis disabled - skipping check")
        mock_mlflow.return_value = (
            True,
            None,
            {"health": {"status": "healthy"}},
        )  # Returns tuple (connected, error, dns_info)
        mock_mlflow_status.return_value = {
            "connected": True,
            "circuit_breaker_state": "CLOSED",
            "error": None,
        }

        # Mock Redis module
        mock_redis_module = Mock()
        mock_redis_module.Redis.return_value.ping.return_value = True
        mock_get_redis.return_value = mock_redis_module

        # Mock psycopg2 module
        mock_pg_module = Mock()
        mock_pg_module.connect.return_value.close.return_value = None
        mock_get_psycopg2.return_value = mock_pg_module

        # Mock event publisher
        mock_publisher = Mock()
        mock_publisher.health_check.return_value = {"status": "healthy"}
        mock_get_publisher.return_value = mock_publisher

        # Mock auth service to reject requests without valid API key
        mock_auth.return_value = None

        # Mock DSPy executor to prevent external service connections
        mock_executor = Mock()
        mock_executor.get_execution_stats.return_value = {
            "total_executions": 0,
            "success_rate": 100,
        }
        mock_dspy_executor.return_value = mock_executor

        yield


class TestEndpointStructure:
    """Test that endpoints match the documented API structure."""

    def test_health_endpoints_no_auth_required(self):
        """Test that health endpoints are accessible without authentication."""
        # These endpoints should not require authentication
        health_endpoints = [
            "/health",
            "/ready",
            "/live",
            "/version",
            "/metrics",
            "/api/v1/dspy/health",
        ]

        for endpoint in health_endpoints:
            response = client.get(endpoint)
            # Should not return 401 (unauthorized)
            assert response.status_code != 401, f"{endpoint} requires auth but shouldn't"

    def test_model_endpoints_require_auth(self):
        """Test that model endpoints require authentication."""
        # These endpoints should require authentication
        model_endpoints = [
            "/models/",
            "/models/test-model/1",
            "/models/compare",
            "/models/production",
            "/models/contributors/0x1234567890123456789012345678901234567890/impact",
        ]

        for endpoint in model_endpoints:
            response = client.get(endpoint)
            # Should return 401 (unauthorized) without auth
            assert response.status_code == 401, f"{endpoint} doesn't require auth but should"

    def test_model_register_endpoint_exists(self):
        """Test that POST /models/register endpoint exists."""
        response = client.post("/models/register", json={})
        # Should return 401 (needs auth) or 422 (validation error), not 404
        assert response.status_code in [401, 422], "POST /models/register endpoint not found"

    def test_model_lineage_endpoints_exist(self):
        """Test that both lineage endpoints exist and are different."""
        # Test the lineage getter
        response = client.get("/models/test-model/1/lineage")
        assert response.status_code in [401, 404], "GET lineage endpoint issue"

        # Test the lineage poster (for recording improvements)
        response = client.post("/models/test-id/lineage", json={})
        assert response.status_code in [401, 422], "POST lineage endpoint not found"

    def test_dspy_endpoints_with_prefix(self):
        """Test that DSPy endpoints use /api/v1/dspy prefix."""
        dspy_endpoints = [
            ("/api/v1/dspy/execute", "post"),
            ("/api/v1/dspy/execute/batch", "post"),
            ("/api/v1/dspy/programs", "get"),
            ("/api/v1/dspy/stats", "get"),
            ("/api/v1/dspy/cache/clear", "post"),
            ("/api/v1/dspy/health", "get"),
        ]

        for endpoint, method in dspy_endpoints:
            if method == "get":
                response = client.get(endpoint)
            else:
                response = client.post(endpoint, json={})
            # Should not return 404 (not found)
            assert response.status_code != 404, f"{endpoint} not found"

    def test_mlflow_proxy_endpoints(self):
        """Test that MLflow proxy endpoints are accessible."""
        # MLflow endpoints should be available at /mlflow/*
        response = client.get("/mlflow/api/2.0/mlflow/experiments/search")
        # Should return 401 (needs auth) not 404
        assert response.status_code in [401, 502], "MLflow proxy not configured at /mlflow/*"

    def test_mlflow_health_endpoints(self):
        """Test MLflow health check endpoints."""
        mlflow_health_endpoints = [
            "/api/health/mlflow",
            "/api/health/mlflow/detailed",
            "/api/health/mlflow/connectivity",
        ]

        for endpoint in mlflow_health_endpoints:
            response = client.get(endpoint)
            # These should be accessible (may return 503 if MLflow is down)
            assert response.status_code in [200, 503], f"{endpoint} not accessible"

    def test_contributor_endpoint_parameter(self):
        """Test that contributor impact endpoint uses 'address' parameter."""
        # The endpoint should use {address} not {contributor_address}
        response = client.get(
            "/models/contributors/0x1234567890123456789012345678901234567890/impact"
        )
        # Should return 401 (needs auth) not 404
        assert response.status_code == 401, "Contributor endpoint parameter issue"

    def test_authentication_excluded_paths(self):
        """Test that all health-related paths are excluded from authentication."""
        from src.middleware.auth import APIKeyAuthMiddleware

        mock_app = Mock()
        middleware = APIKeyAuthMiddleware(app=mock_app)
        expected_exclusions = [
            "/health",
            "/ready",
            "/live",
            "/version",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/favicon.ico",
            "/api/v1/dspy/health",
            "/api/health/mlflow",
        ]

        for path in expected_exclusions:
            assert path in middleware.excluded_paths, f"{path} should be excluded from auth"


class TestEndpointResponses:
    """Test that endpoint responses match documented formats."""

    def test_health_response_format(self):
        """Test that health endpoint returns expected format."""
        response = client.get("/health")
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert data["status"] in ["healthy", "degraded", "unhealthy"]
            assert "services" in data

    def test_ready_response_format(self):
        """Test that ready endpoint returns expected format."""
        response = client.get("/ready")
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "ready" in data
            assert isinstance(data["ready"], bool)

    def test_version_response_format(self):
        """Test that version endpoint returns expected format."""
        response = client.get("/version")
        assert response.status_code == 200

        data = response.json()
        assert "version" in data
        assert "api_version" in data


class TestBackwardCompatibility:
    """Test that existing endpoints still work for backward compatibility."""

    def test_existing_health_mlflow_endpoint(self):
        """Test that /health/mlflow still works."""
        response = client.get("/health/mlflow")
        # Should not return 404
        assert response.status_code != 404, "Existing /health/mlflow endpoint removed"

    def test_existing_debug_endpoint(self):
        """Test that debug endpoint exists (even if disabled in production)."""
        from src.api.routes.health import DEBUG_MODE
        from src.api.routes.health import router as health_router

        # Debug mode should be disabled in production
        assert not DEBUG_MODE, "Debug mode should be disabled in production"

        # Verify the debug route is registered in the health router
        route_paths = [route.path for route in health_router.routes]
        assert "/debug" in route_paths, "Debug endpoint route not registered"
