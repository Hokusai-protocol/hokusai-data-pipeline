"""Authenticated client for Hokusai SDK with external auth service support."""

import os
from typing import Optional, Dict, Any
import logging

import requests

from .config import AuthConfig
from .exceptions import AuthenticationError, AuthorizationError, RateLimitError

logger = logging.getLogger(__name__)


class HokusaiAuth:
    """Authentication handler for Hokusai SDK."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_endpoint: Optional[str] = None,
        auth_service_url: Optional[str] = None,
        validate_with_auth_service: bool = False
    ):
        """Initialize authentication.
        
        Args:
            api_key: API key for authentication
            api_endpoint: API endpoint URL
            auth_service_url: Optional external auth service URL
            validate_with_auth_service: Whether to validate key with auth service
        """
        self.config = AuthConfig(api_key=api_key, api_endpoint=api_endpoint)
        self.config.validate()
        
        # Auth service configuration
        self.auth_service_url = auth_service_url or os.getenv(
            "HOKUSAI_AUTH_SERVICE_URL",
            "https://auth.hokus.ai"
        )
        self.validate_with_auth_service = validate_with_auth_service or os.getenv(
            "HOKUSAI_VALIDATE_API_KEY", "false"
        ).lower() == "true"
        
        # Cache validation result
        self._validation_result = None
        
        # Validate API key with auth service if enabled
        if self.validate_with_auth_service:
            self._validate_api_key()
    
    def _validate_api_key(self) -> None:
        """Validate API key with external auth service."""
        try:
            response = requests.post(
                f"{self.auth_service_url}/api/v1/keys/validate",
                json={
                    "api_key": self.config.api_key,
                    "service_id": "ml-platform"
                },
                timeout=5.0
            )
            
            if response.status_code == 200:
                self._validation_result = response.json()
                logger.info(f"API key validated successfully with auth service")
            elif response.status_code == 401:
                raise AuthenticationError("Invalid or expired API key")
            elif response.status_code == 429:
                raise RateLimitError("Rate limit exceeded for API key validation")
            else:
                logger.warning(f"Auth service returned {response.status_code}, proceeding without validation")
                
        except requests.exceptions.Timeout:
            logger.warning("Auth service timeout, proceeding without validation")
        except requests.exceptions.ConnectionError:
            logger.warning("Could not connect to auth service, proceeding without validation")
        except (AuthenticationError, RateLimitError):
            raise
        except Exception as e:
            logger.warning(f"Auth service error: {e}, proceeding without validation")
    
    @property
    def api_key(self) -> str:
        """Get API key."""
        return self.config.api_key
    
    @property
    def api_endpoint(self) -> str:
        """Get API endpoint."""
        return self.config.api_endpoint
    
    @property
    def user_id(self) -> Optional[str]:
        """Get user ID from validation result."""
        return self._validation_result.get("user_id") if self._validation_result else None
    
    @property
    def scopes(self) -> Optional[list]:
        """Get scopes from validation result."""
        return self._validation_result.get("scopes", []) if self._validation_result else None
    
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
        retry_count: int = 3,
        auth_service_url: Optional[str] = None,
        validate_with_auth_service: bool = False
    ):
        """Initialize authenticated client.
        
        Args:
            api_key: API key for authentication
            api_endpoint: API endpoint URL
            auth: Optional pre-configured auth instance
            timeout: Request timeout in seconds
            retry_count: Number of retries for failed requests
            auth_service_url: Optional external auth service URL
            validate_with_auth_service: Whether to validate key with auth service
        """
        if auth:
            self._auth = auth
        else:
            self._auth = HokusaiAuth(
                api_key=api_key,
                api_endpoint=api_endpoint,
                auth_service_url=auth_service_url,
                validate_with_auth_service=validate_with_auth_service
            )
        
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


def configure(
    api_key: str,
    api_endpoint: str = None,
    auth_service_url: str = None,
    validate_with_auth_service: bool = False
) -> None:
    """Configure global authentication for Hokusai SDK.
    
    Args:
        api_key: API key for authentication
        api_endpoint: API endpoint URL
        auth_service_url: Optional external auth service URL
        validate_with_auth_service: Whether to validate key with auth service
    """
    global _global_auth
    _global_auth = HokusaiAuth(
        api_key=api_key,
        api_endpoint=api_endpoint,
        auth_service_url=auth_service_url,
        validate_with_auth_service=validate_with_auth_service
    )


def get_global_auth() -> Optional[HokusaiAuth]:
    """Get global authentication configuration."""
    return _global_auth


def setup(
    api_key: str,
    api_endpoint: str = None,
    auth_service_url: str = None,
    validate_with_auth_service: bool = False
) -> None:
    """Setup Hokusai SDK (alias for configure).
    
    Args:
        api_key: API key for authentication
        api_endpoint: API endpoint URL
        auth_service_url: Optional external auth service URL
        validate_with_auth_service: Whether to validate key with auth service
    """
    configure(api_key, api_endpoint, auth_service_url, validate_with_auth_service)