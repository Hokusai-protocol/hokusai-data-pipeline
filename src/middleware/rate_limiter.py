"""Rate limiting middleware."""

import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import redis


class RateLimitExceeded(Exception):
    """Rate limit exceeded exception."""
    pass


@dataclass
class RateLimitResult:
    """Result of rate limit check."""
    allowed: bool
    current_requests: int
    limit: int
    remaining: int
    reset_time: int
    burst_limit: Optional[int] = None


def get_request_state(request: Request):
    """Get request state if authenticated."""
    if hasattr(request.state, "api_key_id"):
        return request.state
    return None


def format_rate_limit_headers(result: RateLimitResult) -> dict:
    """Format rate limit headers for response."""
    headers = {
        "X-RateLimit-Limit": str(result.limit),
        "X-RateLimit-Remaining": str(result.remaining),
        "X-RateLimit-Reset": str(result.reset_time),
    }
    
    if not result.allowed:
        retry_after = result.reset_time - int(time.time())
        if retry_after > 0:
            headers["Retry-After"] = str(retry_after)
    
    return headers


class RateLimiter:
    """Rate limiter implementation."""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize rate limiter."""
        if redis_client is None:
            try:
                self.redis = redis.Redis(
                    host='localhost',
                    port=6379,
                    decode_responses=True
                )
                self.redis.ping()
            except Exception:
                # Rate limiting requires Redis
                self.redis = None
        else:
            self.redis = redis_client
    
    def check_rate_limit(
        self,
        key_id: str,
        limit: int,
        burst_limit: Optional[int] = None
    ) -> RateLimitResult:
        """Check if request is within rate limit."""
        if not self.redis:
            # No Redis, allow all requests
            return RateLimitResult(
                allowed=True,
                current_requests=0,
                limit=limit,
                remaining=limit,
                reset_time=int(time.time()) + 3600
            )
        
        # Use fixed window rate limiting (simpler than sliding window)
        window_key = f"rate_limit:hourly:{key_id}"
        
        try:
            # Use pipeline for atomic operations
            pipe = self.redis.pipeline()
            pipe.incr(window_key)
            pipe.expire(window_key, 3600)  # 1 hour expiration
            results = pipe.execute()
            
            current_requests = results[0]
            
            # Calculate remaining requests
            effective_limit = limit + (burst_limit or 0)
            remaining = max(0, effective_limit - current_requests)
            
            # Check if allowed
            allowed = current_requests <= effective_limit
            
            # Calculate reset time (next hour)
            current_hour = int(time.time() // 3600)
            reset_time = (current_hour + 1) * 3600
            
            return RateLimitResult(
                allowed=allowed,
                current_requests=current_requests,
                limit=limit,
                remaining=remaining,
                reset_time=reset_time,
                burst_limit=burst_limit
            )
            
        except Exception as e:
            # On error, allow request (fail open)
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Rate limit check failed: {str(e)}")
            
            return RateLimitResult(
                allowed=True,
                current_requests=0,
                limit=limit,
                remaining=limit,
                reset_time=int(time.time()) + 3600
            )
    
    def check_sliding_window(
        self,
        key_id: str,
        limit: int,
        window_seconds: int = 3600
    ) -> RateLimitResult:
        """Check rate limit using sliding window algorithm."""
        if not self.redis:
            return RateLimitResult(
                allowed=True,
                current_requests=0,
                limit=limit,
                remaining=limit,
                reset_time=int(time.time()) + window_seconds
            )
        
        now = time.time()
        window_start = now - window_seconds
        window_key = f"rate_limit:sliding:{key_id}"
        
        try:
            # Remove old entries
            self.redis.zremrangebyscore(window_key, 0, window_start)
            
            # Add current request
            request_id = f"{now}:{id(now)}"
            self.redis.zadd(window_key, {request_id: now})
            
            # Count requests in window
            current_requests = self.redis.zcard(window_key)
            
            # Set expiration
            self.redis.expire(window_key, window_seconds + 60)
            
            # Check if allowed
            allowed = current_requests <= limit
            remaining = max(0, limit - current_requests)
            
            return RateLimitResult(
                allowed=allowed,
                current_requests=current_requests,
                limit=limit,
                remaining=remaining,
                reset_time=int(now + window_seconds)
            )
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Sliding window rate limit failed: {str(e)}")
            
            return RateLimitResult(
                allowed=True,
                current_requests=0,
                limit=limit,
                remaining=limit,
                reset_time=int(time.time()) + window_seconds
            )
    
    def get_rate_limit_info(self, key_id: str) -> dict:
        """Get current rate limit information."""
        if not self.redis:
            return {
                "current_requests": 0,
                "reset_in_seconds": 3600
            }
        
        window_key = f"rate_limit:hourly:{key_id}"
        
        try:
            current_requests = self.redis.get(window_key)
            ttl = self.redis.ttl(window_key)
            
            return {
                "current_requests": int(current_requests) if current_requests else 0,
                "reset_in_seconds": ttl if ttl > 0 else 3600
            }
        except Exception:
            return {
                "current_requests": 0,
                "reset_in_seconds": 3600
            }
    
    def reset_rate_limit(self, key_id: str) -> None:
        """Reset rate limit for a key."""
        if not self.redis:
            return
        
        window_key = f"rate_limit:hourly:{key_id}"
        
        try:
            self.redis.delete(window_key)
        except Exception:
            pass


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for rate limiting."""
    
    def __init__(
        self,
        app: ASGIApp,
        rate_limiter: Optional[RateLimiter] = None
    ):
        """Initialize rate limit middleware."""
        super().__init__(app)
        self.rate_limiter = rate_limiter or RateLimiter()
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        # Get request state from auth middleware
        state = get_request_state(request)
        
        # Skip rate limiting if not authenticated
        if not state:
            response = await call_next(request)
            return response
        
        # Check rate limit
        try:
            result = self.rate_limiter.check_rate_limit(
                state.api_key_id,
                state.rate_limit_per_hour
            )
            
            # Add rate limit headers
            headers = format_rate_limit_headers(result)
            
            if not result.allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers=headers
                )
            
            # Process request
            response = await call_next(request)
            
            # Add rate limit headers to response
            for header, value in headers.items():
                response.headers[header] = value
            
            return response
            
        except Exception as e:
            # On error, allow request (fail open)
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Rate limiting error: {str(e)}")
            
            response = await call_next(request)
            return response