"""Unit tests for MLflow health check endpoints."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import httpx
from fastapi.testclient import TestClient
from src.api.routes.health_mlflow import router

# Create test client
from fastapi import FastAPI
app = FastAPI()
app.include_router(router)
client = TestClient(app)


class TestMLflowHealthEndpoints:
    """Test cases for MLflow health check endpoints."""
    
    def test_health_check_all_healthy(self):
        """Test health check when all services are healthy."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = Mock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            # Mock responses for health checks
            mock_response_health = Mock()
            mock_response_health.status_code = 200
            
            mock_response_api = Mock()
            mock_response_api.status_code = 200
            
            mock_client.get = AsyncMock(side_effect=[
                mock_response_health,  # Basic connectivity
                mock_response_api      # Experiments API
            ])
            
            mock_client_class.return_value = mock_client
            
            response = client.get("/mlflow")
            
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'healthy'
            assert data['checks']['connectivity']['status'] == 'healthy'
            assert data['checks']['experiments_api']['status'] == 'healthy'
    
    def test_health_check_mlflow_down(self):
        """Test health check when MLflow is down."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = Mock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            # Mock connection error
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            
            mock_client_class.return_value = mock_client
            
            response = client.get("/mlflow")
            
            assert response.status_code == 503
            data = response.json()
            assert data['detail']['status'] == 'unhealthy'
            assert data['detail']['checks']['connectivity']['status'] == 'unhealthy'
    
    def test_connectivity_check_success(self):
        """Test connectivity check when MLflow is reachable."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = Mock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.elapsed = Mock(total_seconds=Mock(return_value=0.123))
            
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            response = client.get("/mlflow/connectivity")
            
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'connected'
            assert 'response_time_ms' in data
    
    def test_connectivity_check_timeout(self):
        """Test connectivity check timeout."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = Mock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client_class.return_value = mock_client
            
            response = client.get("/mlflow/connectivity")
            
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'timeout'
            assert 'error' in data
    
    def test_detailed_health_check(self):
        """Test detailed health check."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = Mock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            # Mock successful responses
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.elapsed = Mock(total_seconds=Mock(return_value=0.050))
            
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            response = client.get("/mlflow/detailed")
            
            assert response.status_code == 200
            data = response.json()
            assert 'tests' in data
            assert len(data['tests']) > 0
            assert data['overall_health'] is True
            
            # Check that all tests passed
            for test in data['tests']:
                assert test['success'] is True
                assert 'response_time_ms' in test
    
    def test_detailed_health_check_partial_failure(self):
        """Test detailed health check with some endpoints failing."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = Mock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            
            # Mock mixed responses
            responses = [
                Mock(status_code=200, elapsed=Mock(total_seconds=Mock(return_value=0.050))),
                Mock(status_code=500, elapsed=Mock(total_seconds=Mock(return_value=0.100))),
                Mock(status_code=200, elapsed=Mock(total_seconds=Mock(return_value=0.075)))
            ]
            
            mock_client.request = AsyncMock(side_effect=responses)
            mock_client_class.return_value = mock_client
            
            response = client.get("/mlflow/detailed")
            
            assert response.status_code == 200
            data = response.json()
            assert data['overall_health'] is False
            
            # Check mixed results
            success_count = sum(1 for test in data['tests'] if test['success'])
            assert success_count == 2  # Two out of three succeeded