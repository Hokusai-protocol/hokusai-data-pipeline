"""Unit tests for DSPy API endpoints."""

import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from src.api.main import app
from src.services.dspy_pipeline_executor import ExecutionResult, ExecutionMode


# Mock authentication for tests
@pytest.fixture
def mock_auth():
    """Mock authentication to bypass token verification."""
    with patch('src.api.middleware.auth.require_auth') as mock_verify:
        mock_verify.return_value = {"sub": "test-user", "email": "test@example.com"}
        yield mock_verify


@pytest.fixture
def client(mock_auth):
    """Create test client with mocked auth."""
    return TestClient(app)


class TestDSPyAPI:
    """Test cases for DSPy API endpoints."""
    
    def test_execute_dspy_program_success(self, client):
        """Test successful DSPy program execution."""
        # Mock the executor
        mock_result = ExecutionResult(
            success=True,
            outputs={"email": "Generated email content"},
            error=None,
            execution_time=0.5,
            program_name="email-assistant",
            metadata={"mode": "normal"}
        )
        
        with patch('src.api.routes.dspy.get_executor') as mock_get_executor:
            mock_executor = MagicMock()
            mock_executor.execute.return_value = mock_result
            mock_get_executor.return_value = mock_executor
            
            response = client.post(
                "/api/v1/dspy/execute",
                json={
                    "program_id": "email-assistant-v1",
                    "inputs": {
                        "recipient": "john@example.com",
                        "subject": "Test"
                    }
                },
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["outputs"]["email"] == "Generated email content"
            assert data["program_name"] == "email-assistant"
            assert "execution_id" in data
            
            # Verify executor was called correctly
            mock_executor.execute.assert_called_once()
            call_args = mock_executor.execute.call_args
            assert call_args.kwargs["model_id"] == "email-assistant-v1"
            assert call_args.kwargs["inputs"]["recipient"] == "john@example.com"
    
    def test_execute_dspy_program_failure(self, client):
        """Test DSPy program execution failure."""
        mock_result = ExecutionResult(
            success=False,
            outputs=None,
            error="Model not found",
            execution_time=0.1,
            program_name="unknown",
            metadata={}
        )
        
        with patch('src.api.routes.dspy.get_executor') as mock_get_executor:
            mock_executor = MagicMock()
            mock_executor.execute.return_value = mock_result
            mock_get_executor.return_value = mock_executor
            
            response = client.post(
                "/api/v1/dspy/execute",
                json={
                    "program_id": "non-existent",
                    "inputs": {"test": "data"}
                },
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert data["error"] == "Model not found"
            assert data["outputs"] is None
    
    def test_execute_dspy_batch_success(self, client):
        """Test successful batch DSPy execution."""
        # Mock results for batch
        mock_results = [
            ExecutionResult(
                success=True,
                outputs={"email": "Email 1"},
                error=None,
                execution_time=0.3,
                program_name="email-assistant",
                metadata={}
            ),
            ExecutionResult(
                success=True,
                outputs={"email": "Email 2"},
                error=None,
                execution_time=0.4,
                program_name="email-assistant",
                metadata={}
            )
        ]
        
        with patch('src.api.routes.dspy.get_executor') as mock_get_executor:
            mock_executor = MagicMock()
            mock_executor.execute_batch.return_value = mock_results
            mock_get_executor.return_value = mock_executor
            
            response = client.post(
                "/api/v1/dspy/execute/batch",
                json={
                    "program_id": "email-assistant-v1",
                    "inputs_list": [
                        {"recipient": "john@example.com", "subject": "Test 1"},
                        {"recipient": "jane@example.com", "subject": "Test 2"}
                    ]
                },
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 2
            assert data["successful"] == 2
            assert data["failed"] == 0
            assert len(data["results"]) == 2
            assert data["results"][0]["outputs"]["email"] == "Email 1"
            assert data["results"][1]["outputs"]["email"] == "Email 2"
    
    def test_execute_dspy_batch_with_failures(self, client):
        """Test batch execution with some failures."""
        mock_results = [
            ExecutionResult(
                success=True,
                outputs={"email": "Success"},
                error=None,
                execution_time=0.3,
                program_name="email-assistant",
                metadata={}
            ),
            ExecutionResult(
                success=False,
                outputs=None,
                error="Invalid input",
                execution_time=0.1,
                program_name="email-assistant",
                metadata={}
            )
        ]
        
        with patch('src.api.routes.dspy.get_executor') as mock_get_executor:
            mock_executor = MagicMock()
            mock_executor.execute_batch.return_value = mock_results
            mock_get_executor.return_value = mock_executor
            
            response = client.post(
                "/api/v1/dspy/execute/batch",
                json={
                    "program_id": "email-assistant-v1",
                    "inputs_list": [
                        {"recipient": "john@example.com"},
                        {"invalid": "data"}
                    ]
                },
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 2
            assert data["successful"] == 1
            assert data["failed"] == 1
            assert data["results"][1]["error"] == "Invalid input"
    
    def test_list_dspy_programs(self, client):
        """Test listing available DSPy programs."""
        mock_models = [
            {
                "id": "email-assistant-v1",
                "name": "Email Assistant",
                "version": "1.0.0",
                "signatures": [{"name": "generate_email"}],
                "description": "Generate professional emails"
            },
            {
                "id": "summarizer-v2",
                "name": "Text Summarizer",
                "version": "2.0.0",
                "signatures": [{"name": "summarize"}],
                "description": "Summarize long texts"
            }
        ]
        
        with patch('src.api.routes.dspy.HokusaiModelRegistry') as mock_registry_class:
            mock_registry = MagicMock()
            mock_registry.list_models.return_value = mock_models
            mock_registry_class.return_value = mock_registry
            
            response = client.get(
                "/api/v1/dspy/programs",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["program_id"] == "email-assistant-v1"
            assert data[0]["name"] == "Email Assistant"
            assert data[1]["program_id"] == "summarizer-v2"
    
    def test_get_execution_stats(self, client):
        """Test getting execution statistics."""
        mock_stats = {
            "total_executions": 100,
            "successful_executions": 95,
            "failed_executions": 5,
            "success_rate": 0.95,
            "average_execution_time": 0.45,
            "p95_execution_time": 0.89
        }
        
        with patch('src.api.routes.dspy.get_executor') as mock_get_executor:
            mock_executor = MagicMock()
            mock_executor.get_execution_stats.return_value = mock_stats
            mock_executor.cache_enabled = True
            mock_executor.mlflow_tracking = True
            mock_get_executor.return_value = mock_executor
            
            response = client.get(
                "/api/v1/dspy/stats",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["statistics"]["total_executions"] == 100
            assert data["statistics"]["success_rate"] == 0.95
            assert data["cache_enabled"] is True
            assert data["mlflow_tracking"] is True
    
    def test_clear_cache(self, client):
        """Test clearing the DSPy cache."""
        with patch('src.api.routes.dspy.get_executor') as mock_get_executor:
            mock_executor = MagicMock()
            mock_get_executor.return_value = mock_executor
            
            response = client.post(
                "/api/v1/dspy/cache/clear",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Cache cleared successfully"
            
            # Verify clear_cache was called
            mock_executor.clear_cache.assert_called_once()
    
    def test_dspy_health_check(self, client):
        """Test DSPy health check endpoint."""
        mock_stats = {
            "total_executions": 50,
            "success_rate": 0.98
        }
        
        with patch('src.api.routes.dspy.get_executor') as mock_get_executor:
            mock_executor = MagicMock()
            mock_executor.get_execution_stats.return_value = mock_stats
            mock_get_executor.return_value = mock_executor
            
            response = client.get("/api/v1/dspy/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["total_executions"] == 50
            assert data["success_rate"] == 0.98
    
    def test_execute_with_debug_mode(self, client):
        """Test execution with debug mode."""
        mock_result = ExecutionResult(
            success=True,
            outputs={"result": "debug output"},
            error=None,
            execution_time=0.6,
            program_name="test-program",
            metadata={"mode": "debug", "debug_trace": {"steps": 3}}
        )
        
        with patch('src.api.routes.dspy.get_executor') as mock_get_executor:
            mock_executor = MagicMock()
            mock_executor.execute.return_value = mock_result
            mock_get_executor.return_value = mock_executor
            
            response = client.post(
                "/api/v1/dspy/execute",
                json={
                    "program_id": "test-program",
                    "inputs": {"data": "test"},
                    "mode": "debug"
                },
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["metadata"]["mode"] == "debug"
            assert "debug_trace" in data["metadata"]
            
            # Verify debug mode was passed
            call_args = mock_executor.execute.call_args
            assert call_args.kwargs["mode"] == ExecutionMode.DEBUG
    
    def test_execute_missing_auth(self, client):
        """Test execution without authentication."""
        # Remove the mock auth for this test
        with patch('src.api.middleware.auth.require_auth', side_effect=Exception("No token")):
            response = client.post(
                "/api/v1/dspy/execute",
                json={
                    "program_id": "test",
                    "inputs": {"data": "test"}
                }
            )
            
            # Should fail due to auth middleware
            assert response.status_code == 401 or response.status_code == 403
    
    def test_execute_invalid_mode(self, client):
        """Test execution with invalid mode."""
        response = client.post(
            "/api/v1/dspy/execute",
            json={
                "program_id": "test",
                "inputs": {"data": "test"},
                "mode": "invalid_mode"
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        # Should fail with 500 due to invalid enum value
        assert response.status_code == 500