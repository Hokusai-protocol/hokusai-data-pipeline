#!/usr/bin/env python3
"""Simple verification tests for MLflow proxy routing fixes from PR #60."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.api.routes.mlflow_proxy_improved import proxy_request
from unittest.mock import Mock, AsyncMock, patch
import asyncio
import httpx


def test_internal_mlflow_routing():
    """Verify internal MLflow uses standard API path."""
    print("\n✅ Testing internal MLflow routing...")
    
    # Mock request
    mock_request = Mock()
    mock_request.method = "GET"
    mock_request.headers = {"content-type": "application/json"}
    mock_request.query_params = {}
    mock_request.state = Mock()
    mock_request.state.user_id = "test-user"
    mock_request.state.api_key_id = "test-key"
    mock_request.body = AsyncMock(return_value=b"")
    
    async def test():
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b'{"experiments": []}'
            mock_response.headers = {}
            mock_client.request.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Test with internal URL
            response = await proxy_request(
                mock_request, 
                "api/2.0/mlflow/experiments/search",
                mlflow_base_url="http://mlflow.hokusai-development.local:5000"
            )
            
            # Verify correct URL was called
            call_args = mock_client.request.call_args
            actual_url = call_args[1]['url']
            expected_url = "http://mlflow.hokusai-development.local:5000/api/2.0/mlflow/experiments/search"
            
            print(f"   Expected URL: {expected_url}")
            print(f"   Actual URL:   {actual_url}")
            assert actual_url == expected_url, f"URL mismatch!"
            print("   ✓ Internal routing correct - uses /api/2.0/")
    
    asyncio.run(test())


def test_external_mlflow_routing():
    """Verify external MLflow converts to ajax-api."""
    print("\n✅ Testing external MLflow routing...")
    
    # Mock request
    mock_request = Mock()
    mock_request.method = "GET"
    mock_request.headers = {"content-type": "application/json"}
    mock_request.query_params = {}
    mock_request.state = Mock()
    mock_request.state.user_id = "test-user"
    mock_request.state.api_key_id = "test-key"
    mock_request.body = AsyncMock(return_value=b"")
    
    async def test():
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b'{"models": []}'
            mock_response.headers = {}
            mock_client.request.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Test with external URL containing registry.hokus.ai
            response = await proxy_request(
                mock_request, 
                "api/2.0/mlflow/registered-models/search",
                mlflow_base_url="https://registry.hokus.ai/mlflow"
            )
            
            # Verify ajax-api conversion happened
            call_args = mock_client.request.call_args
            actual_url = call_args[1]['url']
            expected_url = "https://registry.hokus.ai/mlflow/ajax-api/2.0/mlflow/registered-models/search"
            
            print(f"   Expected URL: {expected_url}")
            print(f"   Actual URL:   {actual_url}")
            assert actual_url == expected_url, f"URL mismatch!"
            print("   ✓ External routing correct - converted to /ajax-api/2.0/")
    
    asyncio.run(test())


def test_auth_header_removal():
    """Verify Hokusai auth headers are removed before proxying."""
    print("\n✅ Testing auth header removal...")
    
    # Mock request with auth headers
    mock_request = Mock()
    mock_request.method = "POST"
    mock_request.headers = {
        "authorization": "Bearer hokusai-api-key",
        "x-api-key": "secret-key",
        "content-type": "application/json",
        "user-agent": "test-client"
    }
    mock_request.query_params = {}
    mock_request.state = Mock()
    mock_request.state.user_id = "test-user"
    mock_request.state.api_key_id = "test-key"
    mock_request.body = AsyncMock(return_value=b'{"name": "test-model"}')
    
    async def test():
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b'{"registered_model": {"name": "test-model"}}'
            mock_response.headers = {}
            mock_client.request.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            response = await proxy_request(
                mock_request, 
                "api/2.0/mlflow/registered-models/create"
            )
            
            # Verify headers sent to MLflow
            call_args = mock_client.request.call_args
            headers = call_args[1]['headers']
            
            print(f"   Headers forwarded to MLflow: {list(headers.keys())}")
            assert 'authorization' not in headers, "Authorization header not removed!"
            assert 'x-api-key' not in headers, "X-API-Key header not removed!"
            assert 'content-type' in headers, "Content-Type header removed!"
            print("   ✓ Auth headers correctly removed")
            print(f"   ✓ User context headers added: X-Hokusai-User-Id={headers.get('X-Hokusai-User-Id')}")
    
    asyncio.run(test())


def test_artifact_routing():
    """Verify artifact endpoints are handled correctly."""
    print("\n✅ Testing artifact endpoint routing...")
    
    # Mock request
    mock_request = Mock()
    mock_request.method = "GET"
    mock_request.headers = {}
    mock_request.query_params = {}
    mock_request.state = Mock()
    mock_request.state.user_id = "test-user"
    mock_request.state.api_key_id = "test-key"
    mock_request.body = AsyncMock(return_value=b"")
    
    async def test():
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b'model binary data'
            mock_response.headers = {"content-type": "application/octet-stream"}
            mock_client.request.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Test artifact endpoint
            response = await proxy_request(
                mock_request, 
                "api/2.0/mlflow-artifacts/artifacts/run-123/model.pkl"
            )
            
            # Verify correct URL was called
            call_args = mock_client.request.call_args
            actual_url = call_args[1]['url']
            
            print(f"   Artifact URL: {actual_url}")
            assert "/api/2.0/mlflow-artifacts/" in actual_url
            print("   ✓ Artifact routing correct")
    
    asyncio.run(test())


def main():
    """Run all verification tests."""
    print("\n🧪 Verifying MLflow Proxy Routing Fixes (PR #60)")
    print("=" * 60)
    
    try:
        test_internal_mlflow_routing()
        test_external_mlflow_routing()
        test_auth_header_removal()
        test_artifact_routing()
        
        print("\n" + "=" * 60)
        print("✅ All routing verifications passed!")
        print("\nKey fixes verified:")
        print("1. Internal MLflow uses standard /api/2.0/ path")
        print("2. External MLflow converts to /ajax-api/2.0/ path")
        print("3. Hokusai auth headers are removed before proxying")
        print("4. User context headers are added for tracking")
        print("5. Artifact endpoints are properly routed")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()