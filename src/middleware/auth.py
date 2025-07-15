"""API key authentication middleware."""

import asyncio
import json
import time
from typing import Optional, Dict, Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import redis

from src.auth.api_key_service import APIKeyService
from src.database.connection import DatabaseConnection
from src.database.operations import APIKeyDatabaseOperations


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
    """Middleware for API key authentication."""
    
    def __init__(
        self,
        app: ASGIApp,
        api_key_service: Optional[APIKeyService] = None,
        cache: Optional[redis.Redis] = None,
        excluded_paths: Optional[list[str]] = None
    ):
        """Initialize authentication middleware."""
        super().__init__(app)
        
        # Initialize services if not provided
        if api_key_service is None:
            db_conn = DatabaseConnection()
            db_ops = APIKeyDatabaseOperations(db_conn)
            self.api_key_service = APIKeyService(db_ops)
        else:
            self.api_key_service = api_key_service
        
        # Initialize cache if not provided
        if cache is None:
            try:
                self.cache = redis.Redis(
                    host='localhost',
                    port=6379,
                    decode_responses=True
                )
                # Test connection
                self.cache.ping()
            except Exception:
                # Cache is optional - continue without it
                self.cache = None
        else:
            self.cache = cache
        
        # Paths that don't require authentication
        self.excluded_paths = excluded_paths or [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/favicon.ico"
            # MLflow endpoints now require authentication for security
        ]
    
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
                    validation_result = json.loads(cached_data)
                    # Convert to proper object
                    from src.auth.api_key_service import ValidationResult
                    validation_result = ValidationResult(**validation_result)
            except Exception:
                # Continue without cache
                pass
        
        # Validate API key if not cached
        if validation_result is None:
            try:
                validation_result = self.api_key_service.validate_api_key(
                    api_key,
                    client_ip=client_ip
                )
                
                # Cache successful validation for 5 minutes
                if self.cache and validation_result.is_valid:
                    try:
                        cache_data = {
                            "is_valid": validation_result.is_valid,
                            "key_id": validation_result.key_id,
                            "user_id": validation_result.user_id,
                            "rate_limit_per_hour": validation_result.rate_limit_per_hour
                        }
                        self.cache.setex(
                            cache_key,
                            300,  # 5 minute TTL
                            json.dumps(cache_data)
                        )
                    except Exception:
                        # Continue without caching
                        pass
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Internal server error"}
                )
        
        # Check validation result
        if not validation_result.is_valid:
            return JSONResponse(
                status_code=401,
                content={"detail": validation_result.error or "Invalid API key"}
            )
        
        # Set request state for downstream use
        request.state.user_id = validation_result.user_id
        request.state.api_key_id = validation_result.key_id
        request.state.rate_limit_per_hour = validation_result.rate_limit_per_hour
        
        # Track request start time
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)
        
        # Log usage asynchronously
        if validation_result.key_id:
            # Create background task for usage logging
            asyncio.create_task(
                self._log_usage(
                    validation_result.key_id,
                    request.url.path,
                    response_time_ms,
                    response.status_code
                )
            )
            
            # Update last used timestamp asynchronously
            asyncio.create_task(
                self._update_last_used(validation_result.key_id)
            )
        
        return response
    
    async def _log_usage(
        self,
        key_id: str,
        endpoint: str,
        response_time_ms: int,
        status_code: int
    ) -> None:
        """Log API key usage asynchronously."""
        try:
            from datetime import datetime, timezone
            
            usage_data = {
                "api_key_id": key_id,
                "endpoint": endpoint,
                "timestamp": datetime.now(timezone.utc),
                "response_time_ms": response_time_ms,
                "status_code": status_code
            }
            
            # This would normally use the database operations
            # For now, we'll just log it
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"API usage: {usage_data}")
            
        except Exception:
            # Don't fail on logging errors
            pass
    
    async def _update_last_used(self, key_id: str) -> None:
        """Update last used timestamp asynchronously."""
        try:
            self.api_key_service.update_last_used(key_id)
        except Exception:
            # Don't fail on update errors
            pass