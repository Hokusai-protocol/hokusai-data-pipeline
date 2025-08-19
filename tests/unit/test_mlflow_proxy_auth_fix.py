"""Test to verify MLflow proxy forwards authentication headers correctly."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import Request, Response
from fastapi.testclient import TestClient
import httpx

# Import the proxy module
from src.api.routes.mlflow_proxy_improved import proxy_request, router


@pytest.mark.asyncio
async def test_proxy_should_forward_auth_headers():
    """Test that authentication headers are forwarded to MLflow."""
    
    # Create a mock request with auth headers
    mock_request = Mock(spec=Request)
    mock_request.method = "GET"
    mock_request.headers = {
        "authorization": "Bearer hk_live_test_api_key",
        "x-api-key": "hk_live_test_api_key",
        "content-type": "application/json",
        "host": "registry.hokus.ai"
    }
    mock_request.query_params = {}
    mock_request.state = Mock()
    mock_request.state.user_id = "test_user_123"
    mock_request.state.api_key_id = "key_456"
    
    # Mock the request body
    async def mock_body():
        return b'{"test": "data"}'
    mock_request.body = mock_body
    
    # Mock httpx client to capture the forwarded request
    with patch('src.api.routes.mlflow_proxy_improved.httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Create a mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'{"success": true}'
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"success": true}'
        
        mock_client.request.return_value = mock_response
        
        # Call the proxy function
        result = await proxy_request(
            request=mock_request,
            path="api/2.0/mlflow/experiments/search",
            mlflow_base_url="http://mlflow:5000"
        )
        
        # Verify the request was made
        mock_client.request.assert_called_once()
        
        # Get the actual call arguments
        call_args = mock_client.request.call_args
        forwarded_headers = call_args.kwargs['headers']
        
        # CRITICAL ASSERTION: Auth headers should be forwarded
        # This test will FAIL with current implementation
        assert 'authorization' in forwarded_headers, "Authorization header was not forwarded to MLflow!"
        assert forwarded_headers['authorization'] == "Bearer hk_live_test_api_key"
        
        # Alternative auth header should also be forwarded
        assert 'x-api-key' in forwarded_headers, "X-API-Key header was not forwarded to MLflow!"
        assert forwarded_headers['x-api-key'] == "hk_live_test_api_key"


@pytest.mark.asyncio
async def test_api_mlflow_route_should_be_accessible():
    """Test that /api/mlflow routes are properly mounted and accessible."""
    
    from src.api.main import app
    
    client = TestClient(app)
    
    # Mock the auth middleware to allow the request through
    with patch('src.middleware.auth.APIKeyAuthMiddleware.dispatch') as mock_auth:
        async def mock_dispatch(request, call_next):
            # Add mock user state
            request.state.user_id = "test_user"
            request.state.api_key_id = "test_key"
            response = await call_next(request)
            return response
        mock_auth.side_effect = mock_dispatch
        
        # Mock the MLflow backend response
        with patch('src.api.routes.mlflow_proxy_improved.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b'{"experiments": []}'
            mock_response.headers = {"content-type": "application/json"}
            mock_response.text = '{"experiments": []}'
            
            mock_client.request.return_value = mock_response
            
            # This should work but will return 404 with current routing
            response = client.get(
                "/api/mlflow/api/2.0/mlflow/experiments/search",
                headers={"Authorization": "Bearer hk_live_test_key"}
            )
            
            # This test will FAIL - /api/mlflow is not mounted
            assert response.status_code != 404, "/api/mlflow route returned 404 - route not mounted!"
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"


def test_current_headers_to_remove_config():
    """Document the current broken configuration."""
    
    # Import the actual module to check current config
    import src.api.routes.mlflow_proxy_improved as proxy_module
    
    # Check if the code is stripping auth headers (it shouldn't)
    code = open(proxy_module.__file__).read()
    
    # These assertions document the CURRENT BROKEN behavior
    assert '"authorization"' in code, "Authorization header is in headers_to_remove list"
    assert '"x-api-key"' in code, "X-API-Key header is in headers_to_remove list"
    
    # This is what we need to fix
    print("CURRENT BUG: Authorization headers are being stripped!")
    print("Fix required: Remove auth headers from headers_to_remove list")


if __name__ == "__main__":
    # Run the tests to show they fail
    import asyncio
    
    print("Running tests to demonstrate the bug...")
    print("-" * 60)
    
    try:
        asyncio.run(test_proxy_should_forward_auth_headers())
        print("❌ Test should have failed but passed - unexpected!")
    except AssertionError as e:
        print(f"✅ Test failed as expected: {e}")
    
    print("-" * 60)
    
    try:
        test_current_headers_to_remove_config()
        print("✅ Current configuration confirmed - auth headers are being stripped")
    except Exception as e:
        print(f"❌ Error checking configuration: {e}")