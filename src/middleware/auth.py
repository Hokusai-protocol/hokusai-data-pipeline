"""API key authentication middleware using external auth service."""

import asyncio
import json
import os
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass

import httpx
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import redis
import logging

from src.api.utils.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result from API key validation."""
    is_valid: bool
    user_id: Optional[str] = None
    key_id: Optional[str] = None
    service_id: Optional[str] = None
    scopes: Optional[list[str]] = None
    rate_limit_per_hour: Optional[int] = None
    error: Optional[str] = None


def get_api_key_from_request(request: Request) -> Optional[str]:
    """Extract API key from request headers or query parameters."""
    # Check Authorization header (Bearer token)
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    elif auth_header.startswith("ApiKey "):
        return auth_header[7:]
    
    # Check X-API-Key header
    x_api_key = request.headers.get("x-api-key")
    if x_api_key:
        return x_api_key
    
    # Check query parameter
    api_key = request.query_params.get("api_key")
    if api_key:
        return api_key
    
    return None


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Middleware for API key authentication using external auth service."""
    
    def __init__(
        self,
        app: ASGIApp,
        auth_service_url: Optional[str] = None,
        cache: Optional[redis.Redis] = None,
        excluded_paths: Optional[list[str]] = None,
        timeout: float = 5.0
    ):
        """Initialize authentication middleware.
        
        Args:
            app: The ASGI application
            auth_service_url: URL of the external auth service
            cache: Optional Redis cache instance
            excluded_paths: List of paths that don't require authentication
            timeout: Timeout for auth service requests in seconds
        """
        super().__init__(app)
        
        # Get settings
        self.settings = get_settings()
        
        # Configure auth service URL
        self.auth_service_url = auth_service_url or os.getenv(
            "HOKUSAI_AUTH_SERVICE_URL",
            self.settings.auth_service_url
        )
        self.timeout = timeout or self.settings.auth_service_timeout
        
        # Initialize cache if not provided
        if cache is None:
            try:
                # Build Redis URL from components or use REDIS_URL directly
                redis_url = os.getenv("REDIS_URL")
                if not redis_url:
                    redis_host = os.getenv("REDIS_HOST", "localhost")
                    redis_port = os.getenv("REDIS_PORT", "6379")
                    redis_auth_token = os.getenv("REDIS_AUTH_TOKEN")
                    
                    # Check if we need TLS (ElastiCache with encryption)
                    if redis_host.startswith("master.hokusai") or redis_host.endswith(".cache.amazonaws.com"):
                        # ElastiCache with transit encryption requires rediss://
                        if redis_auth_token:
                            redis_url = f"rediss://:{redis_auth_token}@{redis_host}:{redis_port}/0"
                        else:
                            # ElastiCache without auth but with TLS
                            redis_url = f"rediss://{redis_host}:{redis_port}/0"
                        logger.info(f"Using TLS connection to Redis at {redis_host}")
                    else:
                        # Local Redis without TLS
                        if redis_auth_token:
                            redis_url = f"redis://:{redis_auth_token}@{redis_host}:{redis_port}/0"
                        else:
                            redis_url = f"redis://{redis_host}:{redis_port}/0"
                
                # Only try to connect if not localhost (avoid hanging on local dev)
                if "localhost" not in redis_url and "127.0.0.1" not in redis_url:
                    self.cache = redis.from_url(
                        redis_url, 
                        decode_responses=True,
                        socket_connect_timeout=2,  # 2 second connection timeout
                        socket_timeout=2,  # 2 second operation timeout
                        ssl_cert_reqs=None  # Allow self-signed certs for ElastiCache
                    )
                    # Test connection with timeout
                    self.cache.ping()
                    logger.info("Redis cache connected for auth middleware")
                else:
                    logger.info("Skipping Redis connection for localhost")
                    self.cache = None
            except Exception as e:
                # Cache is optional - continue without it
                logger.warning(f"Redis cache not available: {e}")
                self.cache = None
        else:
            self.cache = cache
        
        # Paths that don't require authentication
        self.excluded_paths = excluded_paths or [
            "/health",
            "/ready",
            "/live",
            "/version",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/favicon.ico",
            "/api/v1/dspy/health",
            "/api/health/mlflow"
        ]
    
    async def validate_with_auth_service(
        self, 
        api_key: str, 
        client_ip: Optional[str] = None
    ) -> ValidationResult:
        """Validate API key with external auth service.
        
        Args:
            api_key: The API key to validate
            client_ip: Optional client IP for IP-based restrictions
            
        Returns:
            ValidationResult with validation details
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # FIXED: Send API key in Authorization header, not JSON body
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                # Only send service_id and client_ip in body
                body = {
                    "service_id": self.settings.auth_service_id  # Configurable service ID
                }
                if client_ip:
                    body["client_ip"] = client_ip
                
                response = await client.post(
                    f"{self.auth_service_url}/api/v1/keys/validate",
                    headers=headers,
                    json=body
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return ValidationResult(
                        is_valid=True,
                        user_id=data.get("user_id"),
                        key_id=data.get("key_id"),
                        service_id=data.get("service_id"),
                        scopes=data.get("scopes", []),
                        rate_limit_per_hour=data.get("rate_limit_per_hour", 1000)
                    )
                elif response.status_code == 401:
                    return ValidationResult(
                        is_valid=False,
                        error="Invalid or expired API key"
                    )
                elif response.status_code == 429:
                    return ValidationResult(
                        is_valid=False,
                        error="Rate limit exceeded"
                    )
                else:
                    logger.error(f"Auth service returned {response.status_code}")
                    return ValidationResult(
                        is_valid=False,
                        error="Authentication service error"
                    )
                    
        except httpx.TimeoutException:
            logger.error("Auth service request timed out")
            return ValidationResult(
                is_valid=False,
                error="Authentication service timeout"
            )
        except Exception as e:
            logger.error(f"Auth service error: {str(e)}")
            return ValidationResult(
                is_valid=False,
                error="Authentication service unavailable"
            )
    
    async def dispatch(self, request: Request, call_next):
        """Process the request and validate API key."""
        # Check if path is excluded
        if any(request.url.path.startswith(path) for path in self.excluded_paths):
            response = await call_next(request)
            return response
        
        # Extract API key
        api_key = get_api_key_from_request(request)
        
        if not api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "API key required"}
            )
        
        # Extract client IP
        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else None
        
        # Check cache first
        validation_result = None
        cache_key = f"api_key:validation:{api_key}"
        
        if self.cache:
            try:
                cached_data = self.cache.get(cache_key)
                if cached_data:
                    cached_result = json.loads(cached_data)
                    validation_result = ValidationResult(**cached_result)
                    logger.debug(f"Using cached validation for key {api_key[:8]}...")
            except Exception as e:
                logger.warning(f"Cache read error: {e}")
        
        # Validate with auth service if not cached
        if validation_result is None:
            validation_result = await self.validate_with_auth_service(api_key, client_ip)
            
            # Cache successful validation for 5 minutes
            if self.cache and validation_result.is_valid:
                try:
                    cache_data = {
                        "is_valid": validation_result.is_valid,
                        "user_id": validation_result.user_id,
                        "key_id": validation_result.key_id,
                        "service_id": validation_result.service_id,
                        "scopes": validation_result.scopes,
                        "rate_limit_per_hour": validation_result.rate_limit_per_hour
                    }
                    self.cache.setex(
                        cache_key,
                        300,  # 5 minute TTL
                        json.dumps(cache_data)
                    )
                except Exception as e:
                    logger.warning(f"Cache write error: {e}")
        
        # Check validation result
        if not validation_result.is_valid:
            return JSONResponse(
                status_code=401,
                content={"detail": validation_result.error or "Invalid API key"}
            )
        
        # Set request state for downstream use
        request.state.user_id = validation_result.user_id
        request.state.api_key_id = validation_result.key_id
        request.state.service_id = validation_result.service_id
        request.state.scopes = validation_result.scopes
        request.state.rate_limit_per_hour = validation_result.rate_limit_per_hour
        
        # Track request start time
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)
        
        # Log usage asynchronously (send to auth service)
        if validation_result.key_id:
            asyncio.create_task(
                self._log_usage_to_auth_service(
                    validation_result.key_id,
                    request.url.path,
                    response_time_ms,
                    response.status_code
                )
            )
        
        return response
    
    async def _log_usage_to_auth_service(
        self,
        key_id: str,
        endpoint: str,
        response_time_ms: int,
        status_code: int
    ) -> None:
        """Log API key usage to auth service asynchronously."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                await client.post(
                    f"{self.auth_service_url}/api/v1/usage/{key_id}",
                    json={
                        "endpoint": endpoint,
                        "response_time_ms": response_time_ms,
                        "status_code": status_code,
                        "service_id": self.settings.auth_service_id
                    }
                )
        except Exception as e:
            # Don't fail on usage logging errors
            logger.debug(f"Failed to log usage: {e}")


# Compatibility functions for routes that expect these functions
from typing import Dict, Any
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()


async def require_auth(request: Request) -> Dict[str, Any]:
    """Dependency for requiring authentication.
    
    This function is used by routes and expects the APIKeyAuthMiddleware
    to have already validated the API key and set request.state attributes.
    """
    # Check if middleware has validated the request
    if not hasattr(request.state, 'user_id'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    # Return user information from request state
    return {
        "user_id": request.state.user_id,
        "api_key_id": getattr(request.state, 'api_key_id', None),
        "service_id": getattr(request.state, 'service_id', None),
        "scopes": getattr(request.state, 'scopes', []),
        "rate_limit_per_hour": getattr(request.state, 'rate_limit_per_hour', None)
    }


async def get_current_user(request: Request) -> Dict[str, Any]:
    """Get current authenticated user - same as require_auth."""
    return await require_auth(request)
