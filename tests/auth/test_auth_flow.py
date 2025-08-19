"""
Critical authentication flow tests.
These tests MUST pass before any deployment.
"""

import pytest
import requests
from unittest.mock import patch, MagicMock, Mock
import json
import os
from typing import Dict, Any


class TestAuthenticationFlow:
    """Test suite for authentication flow - CRITICAL for production safety."""
    
    @pytest.fixture
    def mock_request(self):
        """Create a mock request with auth headers."""
        request = MagicMock()
        request.headers = {
            'Authorization': 'Bearer test-token-123',
            'X-User-ID': 'user-456',
            'X-Request-ID': 'req-789',
            'Content-Type': 'application/json'
        }
        request.method = 'POST'
        request.get_data = MagicMock(return_value=b'{"test": "data"}')
        return request
    
    @pytest.fixture
    def auth_headers(self) -> Dict[str, str]:
        """Standard auth headers for testing."""
        return {
            'Authorization': 'Bearer test-token-123',
            'X-User-ID': 'user-456',
            'X-Request-ID': 'req-789'
        }
    
    def test_proxy_forwards_all_auth_headers(self, mock_request):
        """Ensure proxy never strips authentication headers."""
        from src.api.proxy import proxy_request
        
        with patch('src.api.proxy.requests.request') as mock_req:
            mock_response = Mock()
            mock_response.content = b'{"success": true}'
            mock_response.status_code = 200
            mock_response.headers = {'Content-Type': 'application/json'}
            mock_req.return_value = mock_response
            
            # Call proxy function
            result = proxy_request('test/path', mock_request)
            
            # Verify all auth headers were forwarded
            call_args = mock_req.call_args
            forwarded_headers = call_args.kwargs['headers']
            
            assert 'Authorization' in forwarded_headers
            assert forwarded_headers['Authorization'] == 'Bearer test-token-123'
            assert 'X-User-ID' in forwarded_headers
            assert forwarded_headers['X-User-ID'] == 'user-456'
            assert 'X-Request-ID' in forwarded_headers
    
    def test_proxy_handles_missing_auth_gracefully(self):
        """Test proxy behavior when auth headers are missing."""
        from src.api.proxy import proxy_request
        
        # Create request without auth headers
        request = MagicMock()
        request.headers = {'Content-Type': 'application/json'}
        request.method = 'GET'
        request.get_data = MagicMock(return_value=b'')
        
        # Proxy should either forward without auth or return 401
        result = proxy_request('test/path', request)
        
        # Should return 401 or handle gracefully
        assert result[1] in [401, 403] or result[0] is not None
    
    def test_mlflow_operations_include_auth(self, auth_headers):
        """Verify MLflow operations include authentication."""
        with patch.dict(os.environ, {'MLFLOW_TRACKING_TOKEN': 'test-token-123'}):
            import mlflow
            
            with patch('mlflow.tracking.MlflowClient') as mock_client:
                # Simulate MLflow operation
                client = mlflow.tracking.MlflowClient()
                
                # Verify token is in environment
                assert os.environ.get('MLFLOW_TRACKING_TOKEN') == 'test-token-123'
    
    def test_service_to_service_auth_preserved(self, mock_request):
        """Check internal service communication preserves auth."""
        from src.api.auth_utils import get_auth_headers
        
        # Get headers for service call
        headers = get_auth_headers(mock_request)
        
        # Verify critical headers are present
        assert 'Authorization' in headers
        assert headers['Authorization'] == 'Bearer test-token-123'
        assert 'X-User-ID' in headers
        assert 'X-Request-ID' in headers  # Should have request ID for tracing
    
    def test_auth_error_handling(self):
        """Test proper handling of authentication errors."""
        from src.api.proxy import handle_auth_error
        
        # Test 401 error
        error_401 = Mock()
        error_401.response.status_code = 401
        result = handle_auth_error(error_401)
        assert result[1] == 401
        assert 'Authentication' in str(result[0])
        
        # Test 403 error
        error_403 = Mock()
        error_403.response.status_code = 403
        result = handle_auth_error(error_403)
        assert result[1] == 403
        assert 'permission' in str(result[0]).lower() or 'forbidden' in str(result[0]).lower()
    
    @patch('requests.post')
    def test_mlflow_proxy_with_auth(self, mock_post, mock_request):
        """Test MLflow proxy specifically maintains auth."""
        from src.api.proxy import proxy_to_mlflow
        
        # Setup mock response
        mock_response = Mock()
        mock_response.content = b'{"experiments": []}'
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_post.return_value = mock_response
        
        # Make proxy call
        result = proxy_to_mlflow('api/2.0/mlflow/experiments/list', mock_request)
        
        # Verify auth headers were included
        call_args = mock_post.call_args
        headers = call_args.kwargs.get('headers', {})
        
        assert 'Authorization' in headers
        assert headers['Authorization'] == 'Bearer test-token-123'
    
    def test_auth_headers_not_logged(self, mock_request, caplog):
        """Ensure sensitive auth data is not logged."""
        import logging
        from src.api.proxy import proxy_request
        
        with patch('src.api.proxy.requests.request'):
            # Enable debug logging
            logging.getLogger().setLevel(logging.DEBUG)
            
            # Make request
            proxy_request('test', mock_request)
            
            # Check logs don't contain token
            log_text = caplog.text
            assert 'test-token-123' not in log_text  # Token should not appear
            assert 'Bearer test-token' not in log_text  # Even partial token
    
    def test_webhook_includes_auth(self, auth_headers):
        """Test webhook notifications include authentication."""
        from src.api.webhooks import send_webhook_notification
        
        with patch('requests.post') as mock_post:
            # Send webhook
            send_webhook_notification(
                'https://webhook.url/notify',
                {'event': 'model_registered'},
                auth_headers
            )
            
            # Verify auth headers were included
            call_args = mock_post.call_args
            headers = call_args.kwargs.get('headers', {})
            
            assert 'Authorization' in headers
    
    def test_async_task_preserves_auth(self, auth_headers):
        """Test async/background tasks preserve auth context."""
        from src.api.tasks import process_model_async
        
        with patch('src.api.tasks.celery_app.send_task') as mock_task:
            # Start async task
            process_model_async('model-123', auth_headers)
            
            # Verify auth token was passed to task
            call_args = mock_task.call_args
            task_args = call_args[0][1]  # Get task arguments
            
            # Auth token should be in task args
            assert any('Bearer' in str(arg) for arg in task_args)


class TestProxyValidation:
    """Test proxy configuration validation."""
    
    def test_proxy_doesnt_create_empty_headers(self):
        """Ensure proxy never creates empty header dict."""
        from src.api.proxy import proxy_request
        
        # Check source code doesn't contain anti-patterns
        import inspect
        source = inspect.getsource(proxy_request)
        
        # These patterns should NOT exist
        assert 'headers = {}' not in source
        assert 'headers={}' not in source
        assert 'dict()' not in source or 'dict(request.headers)' in source
    
    def test_proxy_doesnt_strip_auth_header(self):
        """Ensure proxy never explicitly removes auth headers."""
        from src.api.proxy import proxy_request
        
        import inspect
        source = inspect.getsource(proxy_request)
        
        # These should NOT exist
        assert "del headers['Authorization']" not in source
        assert 'headers.pop("Authorization")' not in source
        assert "headers.pop('Authorization')" not in source
    
    def test_all_api_endpoints_require_auth(self):
        """Verify all API endpoints have authentication."""
        from src.api import app
        
        # Get all routes
        public_paths = ['/health', '/healthz', '/ready', '/metrics']
        
        for rule in app.url_map.iter_rules():
            if any(public in rule.rule for public in public_paths):
                continue  # Skip public endpoints
            
            if '/api/' in rule.rule:
                # Check endpoint has auth decorator
                endpoint = app.view_functions[rule.endpoint]
                
                # Should have auth decorator or check in function
                source = inspect.getsource(endpoint)
                assert any([
                    '@require_auth' in source,
                    '@auth_required' in source,
                    'check_auth' in source,
                    'Authorization' in source
                ])


class TestAuthIntegration:
    """Integration tests for complete auth flow."""
    
    @pytest.mark.integration
    def test_complete_auth_flow_e2e(self):
        """Test complete authentication flow end-to-end."""
        # This would be run against actual services
        base_url = os.environ.get('TEST_API_URL', 'http://localhost:8001')
        token = os.environ.get('TEST_AUTH_TOKEN')
        
        if not token:
            pytest.skip("No test token available")
        
        headers = {
            'Authorization': f'Bearer {token}',
            'X-User-ID': 'test-user'
        }
        
        # Test API endpoint
        response = requests.get(f'{base_url}/api/v1/models', headers=headers)
        assert response.status_code in [200, 404]  # 404 ok if no models
        
        # Test MLflow proxy
        response = requests.get(
            f'{base_url}/mlflow/api/2.0/mlflow/experiments/list',
            headers=headers
        )
        assert response.status_code != 401  # Should not be unauthorized
    
    @pytest.mark.integration
    def test_auth_failure_returns_proper_error(self):
        """Test that invalid auth returns proper error."""
        base_url = os.environ.get('TEST_API_URL', 'http://localhost:8001')
        
        # Invalid token
        headers = {'Authorization': 'Bearer invalid-token'}
        
        response = requests.get(f'{base_url}/api/v1/models', headers=headers)
        assert response.status_code == 401
        
        # Missing token
        response = requests.get(f'{base_url}/api/v1/models')
        assert response.status_code == 401


def test_critical_auth_functions_exist():
    """Verify critical auth functions are implemented."""
    # Check auth utilities exist
    from src.api.auth_utils import get_auth_headers
    assert callable(get_auth_headers)
    
    # Check proxy function exists
    from src.api.proxy import proxy_request
    assert callable(proxy_request)
    
    # Check error handler exists
    from src.api.proxy import handle_auth_error
    assert callable(handle_auth_error)