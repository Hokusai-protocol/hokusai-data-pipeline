"""Unit tests for improved MLflow proxy routing."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import httpx
from fastapi import Request, HTTPException
from src.api.routes.mlflow_proxy_improved import proxy_request, mlflow_health_check


@pytest.mark.asyncio
class TestMLflowProxyImproved:
    """Test cases for improved MLflow proxy functionality."""
    
    @pytest.fixture
    def mock_request(self):
        """Create a mock FastAPI request."""
        request = Mock(spec=Request)
        request.method = "GET"
        request.headers = {"content-type": "application/json"}
        request.query_params = {}
        request.state = Mock()
        request.state.user_id = "test-user-123"
        request.state.api_key_id = "key-456"
        request.body = AsyncMock(return_value=b"")
        return request
    
    @pytest.mark.asyncio
    async def test_proxy_request_internal_mlflow(self, mock_request):
        """Test proxying to internal MLflow service."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b'{"experiments": []}'
            mock_response.headers = {}
            mock_client.request.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Test with internal MLflow URL
            with patch('src.api.routes.mlflow_proxy_improved.MLFLOW_SERVER_URL', 
                      'http://mlflow.hokusai-development.local:5000'):
                response = await proxy_request(
                    mock_request, 
                    "api/2.0/mlflow/experiments/search"
                )
            
            # Verify the request was made to the correct URL
            mock_client.request.assert_called_once()
            call_args = mock_client.request.call_args
            assert call_args[1]['url'] == 'http://mlflow.hokusai-development.local:5000/api/2.0/mlflow/experiments/search'
            assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_proxy_request_external_mlflow(self, mock_request):
        """Test proxying to external MLflow with ajax-api conversion."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b'{"experiments": []}'
            mock_response.headers = {}
            mock_client.request.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Test with external MLflow URL
            with patch('src.api.routes.mlflow_proxy_improved.MLFLOW_SERVER_URL', 
                      'https://registry.hokus.ai/mlflow'):
                response = await proxy_request(
                    mock_request, 
                    "api/2.0/mlflow/experiments/search"
                )
            
            # Verify ajax-api conversion happened
            mock_client.request.assert_called_once()
            call_args = mock_client.request.call_args
            assert call_args[1]['url'] == 'https://registry.hokus.ai/mlflow/ajax-api/2.0/mlflow/experiments/search'
            assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_proxy_artifact_request(self, mock_request):
        """Test proxying artifact requests."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b'artifact data'
            mock_response.headers = {}
            mock_client.request.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            response = await proxy_request(
                mock_request, 
                "api/2.0/mlflow-artifacts/artifacts/123"
            )
            
            # Verify artifact request was proxied
            mock_client.request.assert_called_once()
            assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_proxy_removes_auth_headers(self, mock_request):
        """Test that authentication headers are removed before proxying."""
        mock_request.headers = {
            "authorization": "Bearer hokusai-api-key",
            "x-api-key": "hokusai-key",
            "content-type": "application/json",
            "user-agent": "test-client"
        }
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b'{}'
            mock_response.headers = {}
            mock_client.request.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            await proxy_request(mock_request, "api/2.0/mlflow/experiments/search")
            
            # Verify auth headers were removed
            call_args = mock_client.request.call_args
            headers = call_args[1]['headers']
            assert 'authorization' not in headers
            assert 'x-api-key' not in headers
            assert 'content-type' in headers  # Other headers preserved
    
    @pytest.mark.asyncio
    async def test_proxy_adds_user_context(self, mock_request):
        """Test that user context headers are added."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b'{}'
            mock_response.headers = {}
            mock_client.request.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            await proxy_request(mock_request, "api/2.0/mlflow/experiments/search")
            
            # Verify user context headers were added
            call_args = mock_client.request.call_args
            headers = call_args[1]['headers']
            assert headers['X-Hokusai-User-Id'] == 'test-user-123'
            assert headers['X-Hokusai-API-Key-Id'] == 'key-456'
    
    @pytest.mark.asyncio
    async def test_proxy_timeout_error(self, mock_request):
        """Test handling of timeout errors."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.TimeoutException("Request timed out")
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            with pytest.raises(HTTPException) as exc_info:
                await proxy_request(mock_request, "api/2.0/mlflow/experiments/search")
            
            assert exc_info.value.status_code == 504
            assert "timeout" in str(exc_info.value.detail).lower()
    
    @pytest.mark.asyncio
    async def test_proxy_connection_error(self, mock_request):
        """Test handling of connection errors."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.ConnectError("Connection refused")
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            with pytest.raises(HTTPException) as exc_info:
                await proxy_request(mock_request, "api/2.0/mlflow/experiments/search")
            
            assert exc_info.value.status_code == 502
            assert "Failed to connect" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_health_check_all_healthy(self):
        """Test health check when all services are healthy."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            
            # Mock responses for health checks
            mock_client.get.side_effect = [
                Mock(status_code=200),  # Basic connectivity
                Mock(status_code=200, text='{"experiments": []}')  # Experiments API
            ]
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            result = await mlflow_health_check()
            
            assert result['status'] == 'healthy'
            assert result['checks']['connectivity']['status'] == 'healthy'
            assert result['checks']['experiments_api']['status'] == 'healthy'
    
    @pytest.mark.asyncio
    async def test_health_check_partial_failure(self):
        """Test health check with partial failures."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            
            # Mock responses - connectivity OK but API fails
            mock_client.get.side_effect = [
                Mock(status_code=200),  # Basic connectivity OK
                Mock(status_code=500)   # Experiments API error
            ]
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            result = await mlflow_health_check()
            
            assert result['status'] == 'unhealthy'
            assert result['checks']['connectivity']['status'] == 'healthy'
            assert result['checks']['experiments_api']['status'] == 'unhealthy'