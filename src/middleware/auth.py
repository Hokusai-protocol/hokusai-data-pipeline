"""API key authentication middleware using external auth service."""

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx
import redis
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

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
    has_sufficient_balance: bool = True
    balance: float = 0.0


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

    def __init__(  # noqa: ANN204
        self,  # noqa: ANN101
        app: ASGIApp,
        auth_service_url: Optional[str] = None,
        cache: Optional[redis.Redis] = None,
        excluded_paths: Optional[list[str]] = None,
        timeout: float = 5.0,
    ) -> None:
        """Initialize authentication middleware.

        Args:
        ----
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
            "HOKUSAI_AUTH_SERVICE_URL", self.settings.auth_service_url
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
                    if redis_host.startswith("master.hokusai") or redis_host.endswith(
                        ".cache.amazonaws.com"
                    ):
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
                        ssl_cert_reqs=None,  # Allow self-signed certs for ElastiCache
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
            "/api/health/mlflow",
        ]

    async def validate_with_auth_service(
        self,  # noqa: ANN101
        api_key: str,
        client_ip: Optional[str] = None,
    ) -> ValidationResult:
        """Validate API key with external auth service.

        Args:
        ----
            api_key: The API key to validate
            client_ip: Optional client IP for IP-based restrictions

        Returns:
        -------
            ValidationResult with validation details

        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # FIXED: Send API key in Authorization header, not JSON body
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

                # Only send service_id and client_ip in body
                body = {
                    "service_id": self.settings.auth_service_id  # Configurable service ID
                }
                if client_ip:
                    body["client_ip"] = client_ip

                response = await client.post(
                    f"{self.auth_service_url}/api/v1/keys/validate", headers=headers, json=body
                )

                if response.status_code == 200:
                    data = response.json()
                    return ValidationResult(
                        is_valid=True,
                        user_id=data.get("user_id"),
                        key_id=data.get("key_id"),
                        service_id=data.get("service_id"),
                        scopes=data.get("scopes", []),
                        rate_limit_per_hour=data.get("rate_limit_per_hour", 1000),
                        has_sufficient_balance=data.get("has_sufficient_balance", True),
                        balance=data.get("balance", 0.0),
                    )
                elif response.status_code == 401:
                    return ValidationResult(is_valid=False, error="Invalid or expired API key")
                elif response.status_code == 429:
                    return ValidationResult(is_valid=False, error="Rate limit exceeded")
                else:
                    logger.error(f"Auth service returned {response.status_code}")
                    return ValidationResult(is_valid=False, error="Authentication service error")

        except httpx.TimeoutException:
            logger.error("Auth service request timed out")
            return ValidationResult(is_valid=False, error="Authentication service timeout")
        except Exception as e:
            logger.error(f"Auth service error: {str(e)}")
            return ValidationResult(is_valid=False, error="Authentication service unavailable")

    def is_mlflow_write_operation(self, request: Request) -> bool:  # noqa: ANN101
        """Check if the request is for an MLflow write operation.

        Args:
        ----
            request: The incoming request

        Returns:
        -------
            True if this is a write operation requiring write permissions

        """
        path = request.url.path.lower()
        method = request.method.upper()

        # MLflow write operation patterns
        write_patterns = [
            # Run operations
            "/mlflow/runs/create",
            "/mlflow/runs/update",
            "/mlflow/runs/delete",
            "/mlflow/runs/restore",
            "/mlflow/runs/log-metric",
            "/mlflow/runs/log-parameter",
            "/mlflow/runs/log-batch",
            "/mlflow/runs/set-tag",
            "/mlflow/runs/delete-tag",
            # Experiment operations
            "/mlflow/experiments/create",
            "/mlflow/experiments/update",
            "/mlflow/experiments/delete",
            "/mlflow/experiments/restore",
            "/mlflow/experiments/set-experiment-tag",
            # Model registry operations
            "/mlflow/registered-models/create",
            "/mlflow/registered-models/update",
            "/mlflow/registered-models/delete",
            "/mlflow/registered-models/rename",
            "/mlflow/registered-models/set-tag",
            "/mlflow/registered-models/delete-tag",
            # Model version operations
            "/mlflow/model-versions/create",
            "/mlflow/model-versions/update",
            "/mlflow/model-versions/delete",
            "/mlflow/model-versions/set-tag",
            "/mlflow/model-versions/delete-tag",
            "/mlflow/model-versions/transition-stage",
            # Artifact operations
            "/mlflow-artifacts/",
        ]

        # Check if path contains any write pattern
        for pattern in write_patterns:
            if pattern in path:
                return True

        # Also check HTTP method for certain endpoints
        # POST, PUT, PATCH, DELETE are generally write operations for MLflow
        if method in ["POST", "PUT", "PATCH", "DELETE"]:
            # Check if this is an MLflow endpoint
            if "/mlflow/" in path or "/api/mlflow/" in path:
                # Exclude read operations that use POST
                read_post_patterns = [
                    "/search",
                    "/get",
                    "/list",
                    "/download",
                    "/get-by-name",
                ]
                # If it's a POST to a read endpoint, it's not a write operation
                for read_pattern in read_post_patterns:
                    if read_pattern in path:
                        return False
                # Otherwise, POST/PUT/PATCH/DELETE to MLflow is a write operation
                return True

        return False

    def check_scope_for_write_operation(
        self,  # noqa: ANN101
        scopes: Optional[list[str]],
    ) -> bool:
        """Check if the provided scopes include write permissions.

        Args:
        ----
            scopes: List of permission scopes

        Returns:
        -------
            True if write permission is present

        """
        if not scopes:
            return False

        # List of scopes that grant write permission
        write_scopes = [
            "model:write",
            "mlflow:write",
            "mlflow:access",  # Full access scope
            "admin",
            "mlflow:admin",
            "write",
            "full_access",
        ]

        # Check if any write scope is present
        for scope in scopes:
            if scope in write_scopes:
                return True

        return False

    def _is_internal_request(self, client_ip: str) -> bool:  # noqa: ANN101
        """Detect if request is from internal service.

        Internal requests are identified by private IP ranges used by ECS services.

        Args:
        ----
            client_ip: Client IP address

        Returns:
        -------
            True if request is from internal ECS service

        """
        if not client_ip:
            return False

        # Internal requests come from ECS private subnet (10.0.0.0/8)
        if client_ip.startswith("10."):
            return True

        return False

    def _verify_mtls_certificate(self, request: Request) -> bool:  # noqa: ANN101
        """Verify mTLS client certificate from request.

        Checks if a valid client certificate was presented and verified
        during the TLS handshake.

        Args:
        ----
            request: The incoming request

        Returns:
        -------
            True if valid mTLS certificate is present

        """
        # Check if request has state attribute
        if not hasattr(request, "state"):
            return False

        # Check if peer certificate was verified by TLS layer
        # This would be set by the ASGI server (uvicorn/gunicorn)
        if hasattr(request.state, "peer_cert_verified"):
            return bool(request.state.peer_cert_verified)

        # Default to False if certificate verification info not available
        return False

    async def dispatch(  # noqa: C901, ANN201
        self,  # noqa: ANN101
        request: Request,
        call_next,  # noqa: ANN001
    ):
        """Process the request and validate API key."""
        # Allow CORS preflight requests to pass through without authentication
        # OPTIONS requests are used by browsers to check CORS headers before the actual request
        if request.method == "OPTIONS":
            response = await call_next(request)
            return response

        # Check if path is excluded
        if any(request.url.path.startswith(path) for path in self.excluded_paths):
            response = await call_next(request)
            return response

        # Extract client IP for internal request detection
        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else None

        # NEW: Check if this is an internal mTLS request
        if self._is_internal_request(client_ip):
            if self._verify_mtls_certificate(request):
                # Trust mTLS, bypass external auth service
                request.state.user_id = "internal_service"
                request.state.api_key_id = "mtls_cert"
                request.state.service_id = "hokusai_internal"
                request.state.scopes = ["mlflow:write", "mlflow:read"]
                request.state.rate_limit_per_hour = None  # No rate limit for internal

                logger.debug("Internal mTLS request authenticated")
                response = await call_next(request)
                return response
            else:
                logger.warning(f"Internal request from {client_ip} without valid mTLS certificate")
                # Fall through to API key auth

        # EXISTING: Extract API key for external authentication
        api_key = get_api_key_from_request(request)

        if not api_key:
            return JSONResponse(status_code=401, content={"detail": "API key required"})

        # Check cache first (client_ip already extracted above)
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

            # Cache successful validation for 60 seconds
            if self.cache and validation_result.is_valid:
                try:
                    cache_data = {
                        "is_valid": validation_result.is_valid,
                        "user_id": validation_result.user_id,
                        "key_id": validation_result.key_id,
                        "service_id": validation_result.service_id,
                        "scopes": validation_result.scopes,
                        "rate_limit_per_hour": validation_result.rate_limit_per_hour,
                        "has_sufficient_balance": validation_result.has_sufficient_balance,
                        "balance": validation_result.balance,
                    }
                    self.cache.setex(
                        cache_key,
                        60,  # 60 second TTL
                        json.dumps(cache_data),
                    )
                except Exception as e:
                    logger.warning(f"Cache write error: {e}")

        # Check validation result
        if not validation_result.is_valid:
            return JSONResponse(
                status_code=401, content={"detail": validation_result.error or "Invalid API key"}
            )

        # Check balance
        if not validation_result.has_sufficient_balance:
            return JSONResponse(status_code=402, content={"detail": "Insufficient balance"})

        # Check authorization for write operations
        if self.is_mlflow_write_operation(request):
            if not self.check_scope_for_write_operation(validation_result.scopes):
                logger.warning(
                    f"Authorization denied: user_id={validation_result.user_id}, "
                    f"key_id={validation_result.key_id}, "
                    f"path={request.url.path}, method={request.method}, "
                    f"scopes={validation_result.scopes}"
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Insufficient permissions for this operation",
                        "error": "FORBIDDEN",
                        "message": (
                            "This operation requires write permissions. "
                            f"Your API key has scopes: {validation_result.scopes or []}. "
                            "Required: 'model:write' or 'mlflow:write'"
                        ),
                        "required_scope": "model:write or mlflow:write",
                        "current_scopes": validation_result.scopes or [],
                    },
                )
            else:
                logger.info(
                    "Authorization granted for write operation: "
                    f"user_id={validation_result.user_id}, "
                    f"path={request.url.path}, method={request.method}"
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

        # Debit usage asynchronously for non-5xx responses
        if validation_result.key_id and response.status_code < 500:
            model_id = self._extract_model_id(request.url.path)
            asyncio.create_task(
                self._debit_usage(
                    validation_result.key_id,
                    model_id,
                    request.url.path,
                    response_time_ms,
                    response.status_code,
                )
            )

        return response

    def _extract_model_id(self, path: str) -> Optional[str]:  # noqa: ANN101
        """Extract model ID from the request URL path.

        Args:
        ----
            path: The request URL path

        Returns:
        -------
            The model ID if found, None otherwise

        """
        match = re.search(r"/api/v1/models/([^/]+)", path)
        return match.group(1) if match else None

    async def _debit_usage(
        self,  # noqa: ANN101
        key_id: str,
        model_id: Optional[str],
        endpoint: str,
        response_time_ms: int,
        status_code: int,
        max_retries: int = 3,
    ) -> None:
        """Debit usage to auth service with retry logic.

        Args:
        ----
            key_id: The API key ID
            model_id: The model ID from the request path
            endpoint: The request endpoint path
            response_time_ms: Response time in milliseconds
            status_code: HTTP status code of the response
            max_retries: Maximum number of retry attempts

        """
        idempotency_key = f"{key_id}-{int(time.time() * 1000)}"
        payload = {
            "model_id": model_id,
            "endpoint": endpoint,
            "response_time_ms": response_time_ms,
            "status_code": status_code,
            "service_id": self.settings.auth_service_id,
            "idempotency_key": idempotency_key,
        }

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.auth_service_url}/api/v1/usage/{key_id}/debit",
                        json=payload,
                    )
                    if response.status_code < 500:
                        return  # Success or client error — don't retry
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.warning(
                        f"Failed to debit usage after {max_retries} attempts "
                        f"for key_id={key_id}: {e}"
                    )
                    return
            # Exponential backoff: 1s, 2s, 4s
            await asyncio.sleep(2**attempt)


# Compatibility functions for routes that expect these functions
from fastapi import HTTPException, status  # noqa: E402, F811
from fastapi.security import HTTPBearer  # noqa: E402

security = HTTPBearer()


async def require_auth(request: Request) -> dict[str, Any]:
    """Dependency for requiring authentication.

    This function is used by routes and expects the APIKeyAuthMiddleware
    to have already validated the API key and set request.state attributes.
    """
    # Check if middleware has validated the request
    if not hasattr(request.state, "user_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    # Return user information from request state
    return {
        "user_id": request.state.user_id,
        "api_key_id": getattr(request.state, "api_key_id", None),
        "service_id": getattr(request.state, "service_id", None),
        "scopes": getattr(request.state, "scopes", []),
        "rate_limit_per_hour": getattr(request.state, "rate_limit_per_hour", None),
    }


async def get_current_user(request: Request) -> dict[str, Any]:
    """Get current authenticated user - same as require_auth."""
    return await require_auth(request)
