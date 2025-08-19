"""
Integration tests for proxy authentication handling.
"""

import pytest
import requests
import os
from unittest.mock import patch, Mock, MagicMock
import json
from typing import Dict


class TestProxyAuthIntegration:
    """Integration tests for proxy with authentication."""
    
    @pytest.fixture
    def auth_headers(self) -> Dict[str, str]:
        """Get auth headers for testing."""
        return {
            'Authorization': 'Bearer test-integration-token',
            'X-User-ID': 'integration-test-user',
            'X-Request-ID': 'test-request-123'
        }
    
    @pytest.fixture
    def mlflow_url(self) -> str:
        """Get MLflow URL for testing."""
        return os.environ.get('MLFLOW_URL', 'http://mlflow.hokusai-development.local:5000')
    
    def test_proxy_forwards_to_mlflow_with_auth(self, auth_headers, mlflow_url):
        """Test proxy forwards requests to MLflow with auth headers."""
        from src.api.proxy import proxy_to_mlflow
        
        # Create mock request
        request = MagicMock()
        request.headers = auth_headers
        request.method = 'GET'
        request.get_data = MagicMock(return_value=b'')
        
        with patch('requests.request') as mock_request:
            # Setup mock response
            mock_response = Mock()
            mock_response.content = b'{"experiments": []}'
            mock_response.status_code = 200
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_request.return_value = mock_response
            
            # Make proxy call
            result = proxy_to_mlflow('api/2.0/mlflow/experiments/list', request)
            
            # Verify request was made with auth
            assert mock_request.called
            call_kwargs = mock_request.call_args.kwargs
            
            # Check headers were forwarded
            assert 'headers' in call_kwargs
            headers = call_kwargs['headers']
            assert headers['Authorization'] == 'Bearer test-integration-token'
            assert headers['X-User-ID'] == 'integration-test-user'
    
    def test_proxy_handles_mlflow_auth_errors(self, auth_headers):
        """Test proxy properly handles MLflow auth errors."""
        from src.api.proxy import proxy_to_mlflow
        
        request = MagicMock()
        request.headers = {'Authorization': 'Bearer invalid-token'}
        request.method = 'GET'
        request.get_data = MagicMock(return_value=b'')
        
        with patch('requests.request') as mock_request:
            # Simulate 401 from MLflow
            mock_response = Mock()
            mock_response.content = b'{"error": "Unauthorized"}'
            mock_response.status_code = 401
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_request.return_value = mock_response
            
            # Make proxy call
            result = proxy_to_mlflow('api/2.0/mlflow/experiments/list', request)
            
            # Should return 401
            assert result[1] == 401
    
    def test_proxy_preserves_all_custom_headers(self, auth_headers):
        """Test that proxy preserves custom headers beyond auth."""
        from src.api.proxy import proxy_request
        
        # Add custom headers
        custom_headers = auth_headers.copy()
        custom_headers.update({
            'X-Custom-Header': 'custom-value',
            'X-Tenant-ID': 'tenant-123',
            'X-Correlation-ID': 'corr-456'
        })
        
        request = MagicMock()
        request.headers = custom_headers
        request.method = 'POST'
        request.get_data = MagicMock(return_value=b'{"data": "test"}')
        
        with patch('requests.request') as mock_request:
            mock_response = Mock()
            mock_response.content = b'{"success": true}'
            mock_response.status_code = 200
            mock_response.headers = {}
            mock_request.return_value = mock_response
            
            # Make proxy call
            proxy_request('test/endpoint', request)
            
            # Verify all custom headers were forwarded
            forwarded_headers = mock_request.call_args.kwargs['headers']
            assert forwarded_headers['X-Custom-Header'] == 'custom-value'
            assert forwarded_headers['X-Tenant-ID'] == 'tenant-123'
            assert forwarded_headers['X-Correlation-ID'] == 'corr-456'
    
    def test_service_discovery_auth_flow(self, auth_headers):
        """Test auth flow through service discovery."""
        from src.api.proxy import make_internal_request
        
        with patch('requests.request') as mock_request:
            mock_response = Mock()
            mock_response.json.return_value = {'status': 'ok'}
            mock_response.status_code = 200
            mock_request.return_value = mock_response
            
            # Make internal service call
            result = make_internal_request(
                'mlflow.hokusai-development.local',
                '/api/2.0/mlflow/experiments/list',
                headers=auth_headers
            )
            
            # Verify auth headers were included
            call_headers = mock_request.call_args.kwargs['headers']
            assert call_headers['Authorization'] == auth_headers['Authorization']
    
    @pytest.mark.integration
    def test_real_mlflow_connection_with_auth(self):
        """Test real MLflow connection with authentication (if available)."""
        mlflow_url = os.environ.get('MLFLOW_URL', 'http://localhost:5000')
        token = os.environ.get('TEST_MLFLOW_TOKEN')
        
        if not token:
            pytest.skip("No MLflow test token available")
        
        headers = {'Authorization': f'Bearer {token}'}
        
        try:
            response = requests.get(
                f'{mlflow_url}/api/2.0/mlflow/experiments/list',
                headers=headers,
                timeout=5
            )
            
            # Should not get 401
            assert response.status_code != 401
            
            if response.status_code == 200:
                # Verify response structure
                data = response.json()
                assert 'experiments' in data or 'error' in data
                
        except requests.exceptions.ConnectionError:
            pytest.skip("MLflow service not available")
    
    def test_proxy_timeout_handling(self, auth_headers):
        """Test proxy handles timeouts gracefully."""
        from src.api.proxy import proxy_request
        
        request = MagicMock()
        request.headers = auth_headers
        request.method = 'GET'
        request.get_data = MagicMock(return_value=b'')
        
        with patch('requests.request') as mock_request:
            # Simulate timeout
            mock_request.side_effect = requests.exceptions.Timeout("Connection timed out")
            
            # Make proxy call
            result = proxy_request('slow/endpoint', request)
            
            # Should return 504 Gateway Timeout or 503 Service Unavailable
            assert result[1] in [503, 504]
    
    def test_concurrent_requests_maintain_separate_auth(self, auth_headers):
        """Test that concurrent requests don't mix up auth headers."""
        from src.api.proxy import proxy_request
        import threading
        import time
        
        results = []
        
        def make_request(user_id):
            headers = auth_headers.copy()
            headers['X-User-ID'] = f'user-{user_id}'
            
            request = MagicMock()
            request.headers = headers
            request.method = 'GET'
            request.get_data = MagicMock(return_value=b'')
            
            with patch('requests.request') as mock_request:
                mock_response = Mock()
                mock_response.content = b'{"ok": true}'
                mock_response.status_code = 200
                mock_response.headers = {}
                mock_request.return_value = mock_response
                
                proxy_request('test', request)
                
                # Store the headers that were used
                used_headers = mock_request.call_args.kwargs['headers']
                results.append(used_headers['X-User-ID'])
        
        # Start multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=make_request, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all to complete
        for t in threads:
            t.join()
        
        # Verify each request maintained its own user ID
        assert len(results) == 5
        assert set(results) == {f'user-{i}' for i in range(5)}


class TestAuthUtilsIntegration:
    """Test authentication utility functions."""
    
    def test_get_auth_headers_from_request(self):
        """Test extracting auth headers from request."""
        from src.api.auth_utils import get_auth_headers
        
        request = MagicMock()
        request.headers = {
            'Authorization': 'Bearer token-123',
            'X-User-ID': 'user-456',
            'Other-Header': 'value'
        }
        
        headers = get_auth_headers(request)
        
        assert 'Authorization' in headers
        assert headers['Authorization'] == 'Bearer token-123'
        assert 'X-User-ID' in headers
        assert 'X-Request-ID' in headers  # Should add request ID
    
    def test_get_auth_headers_service_account(self):
        """Test getting auth headers for service account."""
        from src.api.auth_utils import get_auth_headers
        
        with patch.dict(os.environ, {'SERVICE_AUTH_TOKEN': 'service-token-789'}):
            headers = get_auth_headers(None)  # No request
            
            assert 'Authorization' in headers
            assert headers['Authorization'] == 'Bearer service-token-789'
            assert 'X-Request-ID' in headers
    
    def test_validate_auth_token(self):
        """Test token validation function."""
        from src.api.auth_utils import validate_token
        
        # Valid token format
        valid_token = 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature'
        assert validate_token(valid_token) is not None
        
        # Invalid formats
        assert validate_token('InvalidToken') is None
        assert validate_token('') is None
        assert validate_token(None) is None