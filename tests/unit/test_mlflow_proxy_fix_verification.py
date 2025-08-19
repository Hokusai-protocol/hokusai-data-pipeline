"""Test to verify the MLflow proxy auth fix is working correctly."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import Request
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from src.api.routes.mlflow_proxy_improved import proxy_request


@pytest.mark.asyncio
async def test_auth_headers_are_forwarded_after_fix():
    """Test that authentication headers are now properly forwarded to MLflow."""
    
    # Create a mock request with auth headers
    mock_request = Mock(spec=Request)
    mock_request.method = "POST"
    mock_request.headers = {
        "authorization": "Bearer hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN",
        "x-api-key": "hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN",
        "content-type": "application/json",
        "host": "registry.hokus.ai",
        "user-agent": "hokusai-ml-platform/1.0"
    }
    mock_request.query_params = {}
    mock_request.state = Mock()
    mock_request.state.user_id = "gtm_backend_user"
    mock_request.state.api_key_id = "key_pIDV2HHx"
    
    # Mock the request body
    async def mock_body():
        return b'{"name": "LSCOR", "description": "Sales Lead Scoring Model"}'
    mock_request.body = mock_body
    
    # Mock httpx client to capture the forwarded request
    with patch('src.api.routes.mlflow_proxy_improved.httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Create a mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'{"model_id": "123", "status": "success"}'
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"model_id": "123", "status": "success"}'
        
        mock_client.request.return_value = mock_response
        
        # Call the proxy function
        result = await proxy_request(
            request=mock_request,
            path="api/2.0/mlflow/registered-models/create",
            mlflow_base_url="http://mlflow:5000"
        )
        
        # Verify the request was made
        mock_client.request.assert_called_once()
        
        # Get the actual call arguments
        call_args = mock_client.request.call_args
        forwarded_headers = call_args.kwargs['headers']
        
        # CRITICAL ASSERTIONS: Auth headers should NOW be forwarded after the fix
        assert 'authorization' in forwarded_headers, "Authorization header should be forwarded after fix!"
        assert forwarded_headers['authorization'] == "Bearer hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN"
        
        assert 'x-api-key' in forwarded_headers, "X-API-Key header should be forwarded after fix!"
        assert forwarded_headers['x-api-key'] == "hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN"
        
        # Verify user context headers are added
        assert 'X-Hokusai-User-Id' in forwarded_headers
        assert forwarded_headers['X-Hokusai-User-Id'] == "gtm_backend_user"
        
        # Verify host header is removed (as intended)
        assert 'host' not in forwarded_headers
        
        print("✅ SUCCESS: Authentication headers are now properly forwarded to MLflow!")
        print(f"   - Authorization: {forwarded_headers.get('authorization', 'MISSING')}")
        print(f"   - X-API-Key: {forwarded_headers.get('x-api-key', 'MISSING')}")
        print(f"   - User Context: {forwarded_headers.get('X-Hokusai-User-Id', 'MISSING')}")
        
        return True


@pytest.mark.asyncio
async def test_mlflow_request_with_all_auth_formats():
    """Test that various authentication formats are handled correctly."""
    
    test_cases = [
        ("Bearer hk_live_test", "Bearer authentication"),
        ("ApiKey hk_live_test", "ApiKey authentication"),
    ]
    
    for auth_value, description in test_cases:
        mock_request = Mock(spec=Request)
        mock_request.method = "GET"
        mock_request.headers = {
            "authorization": auth_value,
            "content-type": "application/json",
        }
        mock_request.query_params = {}
        mock_request.state = Mock()
        mock_request.state.user_id = "test_user"
        mock_request.state.api_key_id = "test_key"
        
        async def mock_body():
            return b''
        mock_request.body = mock_body
        
        with patch('src.api.routes.mlflow_proxy_improved.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b'{"success": true}'
            mock_response.headers = {"content-type": "application/json"}
            mock_response.text = '{"success": true}'
            
            mock_client.request.return_value = mock_response
            
            await proxy_request(
                request=mock_request,
                path="api/2.0/mlflow/experiments/search",
                mlflow_base_url="http://mlflow:5000"
            )
            
            call_args = mock_client.request.call_args
            forwarded_headers = call_args.kwargs['headers']
            
            assert 'authorization' in forwarded_headers, f"{description} should be forwarded"
            assert forwarded_headers['authorization'] == auth_value
            print(f"✅ {description} forwarded correctly: {auth_value}")


if __name__ == "__main__":
    import asyncio
    
    print("Testing MLflow proxy auth fix...")
    print("=" * 60)
    
    # Run the main test
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(test_auth_headers_are_forwarded_after_fix())
    
    if result:
        print("\n" + "=" * 60)
        print("🎉 FIX VERIFIED: Authentication headers are now being forwarded!")
        print("The model registration issue should be resolved.")
    
    # Test other auth formats
    print("\n" + "=" * 60)
    print("Testing various auth formats...")
    loop.run_until_complete(test_mlflow_request_with_all_auth_formats())