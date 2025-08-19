"""
Proxy module for forwarding requests to upstream services.
CRITICAL: This module MUST preserve all authentication headers.
"""

import requests
import logging
from typing import Any, Dict, Tuple, Optional
from .auth_utils import get_auth_headers

logger = logging.getLogger(__name__)


def proxy_request(path: str, request: Any) -> Tuple[Any, int, Dict]:
    """
    Proxy a request to an upstream service.
    
    IMPORTANT: This function MUST preserve all authentication headers!
    
    Args:
        path: Path to proxy to
        request: Incoming request object
        
    Returns:
        Tuple of (content, status_code, headers)
    """
    # CRITICAL: Preserve ALL headers from the original request
    headers = dict(request.headers)
    headers.pop('Host', None)  # Only remove Host header
    
    # Ensure auth headers are present
    if 'Authorization' not in headers:
        logger.warning("No Authorization header in proxy request")
        # In production, might want to return 401 here
    
    # Determine upstream URL based on path
    upstream_url = get_upstream_url(path)
    
    try:
        # Make the upstream request with ALL headers preserved
        response = requests.request(
            method=request.method,
            url=upstream_url,
            headers=headers,  # All auth headers preserved!
            data=request.get_data(),
            stream=True,
            timeout=30
        )
        
        # Log request ID for tracing (not the auth token!)
        if 'X-Request-ID' in headers:
            logger.info(f"Proxied request {headers['X-Request-ID']} to {path}")
        
        return response.content, response.status_code, dict(response.headers)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Proxy request failed: {e}")
        return {"error": "Service unavailable"}, 503, {}


def proxy_to_mlflow(path: str, request: Any) -> Tuple[Any, int, Dict]:
    """
    Proxy requests specifically to MLflow service.
    
    Args:
        path: MLflow API path
        request: Incoming request
        
    Returns:
        Tuple of (content, status_code, headers)
    """
    # CRITICAL: Preserve ALL headers
    headers = dict(request.headers)
    headers.pop('Host', None)
    
    # MLflow internal URL
    mlflow_url = f"http://mlflow.hokusai-development.local:5000/{path}"
    
    # Ensure auth is present for MLflow
    if 'Authorization' not in headers:
        return {"error": "Authentication required for MLflow"}, 401, {}
    
    try:
        response = requests.request(
            method=request.method,
            url=mlflow_url,
            headers=headers,
            data=request.get_data(),
            stream=True,
            timeout=30
        )
        
        return response.content, response.status_code, dict(response.headers)
        
    except requests.exceptions.Timeout:
        return {"error": "MLflow service timeout"}, 504, {}
    except requests.exceptions.RequestException as e:
        logger.error(f"MLflow proxy failed: {e}")
        return {"error": "MLflow service unavailable"}, 503, {}


def handle_auth_error(error: Any) -> Tuple[Dict, int]:
    """
    Handle authentication errors appropriately.
    
    Args:
        error: The error object
        
    Returns:
        Tuple of (error_response, status_code)
    """
    if hasattr(error, 'response') and hasattr(error.response, 'status_code'):
        if error.response.status_code == 401:
            return {"error": "Authentication failed"}, 401
        elif error.response.status_code == 403:
            return {"error": "Insufficient permissions"}, 403
    
    return {"error": "Authentication error"}, 500


def get_upstream_url(path: str) -> str:
    """
    Determine the upstream URL based on the path.
    
    Args:
        path: Request path
        
    Returns:
        Full upstream URL
    """
    # In production, this would map paths to services
    # For now, return a default
    return f"http://upstream-service/{path}"


def make_internal_request(
    service_host: str,
    path: str,
    method: str = "GET",
    headers: Optional[Dict] = None,
    **kwargs
) -> requests.Response:
    """
    Make an internal service-to-service request.
    
    Args:
        service_host: Internal service hostname
        path: API path
        method: HTTP method
        headers: Request headers (auth headers should be included!)
        **kwargs: Additional request parameters
        
    Returns:
        Response object
    """
    url = f"http://{service_host}/{path.lstrip('/')}"
    
    # Ensure we have headers
    if headers is None:
        headers = get_auth_headers()
    
    return requests.request(
        method=method,
        url=url,
        headers=headers,
        **kwargs
    )