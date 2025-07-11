"""Authenticated client for Hokusai SDK."""

import os
from typing import Optional, Dict, Any

import requests

from .config import AuthConfig
from .exceptions import AuthenticationError, AuthorizationError, RateLimitError


class HokusaiAuth:
    """Authentication handler for Hokusai SDK."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_endpoint: Optional[str] = None
    ):
        """Initialize authentication."""
        self.config = AuthConfig(api_key=api_key, api_endpoint=api_endpoint)
        self.config.validate()
    
    @property
    def api_key(self) -> str:
        """Get API key."""
        return self.config.api_key
    
    @property
    def api_endpoint(self) -> str:
        """Get API endpoint."""
        return self.config.api_endpoint
    
    def get_headers(self) -> Dict[str, str]:
        """Get authentication headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "hokusai-sdk/1.0.0"
        }


class AuthenticatedClient:
    """Base client with authentication for Hokusai SDK."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_endpoint: Optional[str] = None,
        auth: Optional[HokusaiAuth] = None,
        timeout: int = 30,
        retry_count: int = 3
    ):
        """Initialize authenticated client."""
        if auth:
            self._auth = auth
        else:
            self._auth = HokusaiAuth(api_key=api_key, api_endpoint=api_endpoint)
        
        self.timeout = timeout
        self.retry_count = retry_count
        self.session = requests.Session()
        self.session.headers.update(self._auth.get_headers())
    
    @property
    def api_endpoint(self) -> str:
        """Get API endpoint."""
        return self._auth.api_endpoint
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Make authenticated API request."""
        url = f"{self.api_endpoint}{endpoint}"
        
        # Merge any additional headers
        headers = kwargs.pop("headers", {})
        headers.update(self._auth.get_headers())
        
        # Make request with retries
        last_exception = None
        for attempt in range(self.retry_count):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    json=json,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                    **kwargs
                )
                
                # Handle response
                if response.status_code == 401:
                    raise AuthenticationError("Invalid API key")
                elif response.status_code == 403:
                    raise AuthorizationError("Insufficient permissions")
                elif response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    raise RateLimitError(
                        "Rate limit exceeded",
                        retry_after=int(retry_after) if retry_after else None
                    )
                
                response.raise_for_status()
                
                # Return JSON response
                if response.content:
                    return response.json()
                return {}
                
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_exception = e
                if attempt < self.retry_count - 1:
                    # Exponential backoff
                    import time
                    time.sleep(2 ** attempt)
                    continue
                raise
            
            except requests.exceptions.HTTPError as e:
                if e.response.status_code >= 500 and attempt < self.retry_count - 1:
                    # Retry on server errors
                    import time
                    time.sleep(2 ** attempt)
                    continue
                raise
        
        # If we get here, all retries failed
        if last_exception:
            raise last_exception
    
    def get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make GET request."""
        return self._make_request("GET", endpoint, **kwargs)
    
    def post(self, endpoint: str, json: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Make POST request."""
        return self._make_request("POST", endpoint, json=json, **kwargs)
    
    def put(self, endpoint: str, json: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Make PUT request."""
        return self._make_request("PUT", endpoint, json=json, **kwargs)
    
    def delete(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make DELETE request."""
        return self._make_request("DELETE", endpoint, **kwargs)


# Global configuration
_global_auth = None


def configure(api_key: str, api_endpoint: str = None) -> None:
    """Configure global authentication for Hokusai SDK."""
    global _global_auth
    _global_auth = HokusaiAuth(api_key=api_key, api_endpoint=api_endpoint)


def get_global_auth() -> Optional[HokusaiAuth]:
    """Get global authentication configuration."""
    return _global_auth


def setup(api_key: str, api_endpoint: str = None) -> None:
    """Setup Hokusai SDK (alias for configure)."""
    configure(api_key, api_endpoint)