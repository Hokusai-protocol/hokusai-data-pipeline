"""Unit tests for rate limiting middleware."""

import time
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.middleware.rate_limiter import RateLimiter, RateLimitExceeded


class TestRateLimiter:
    """Test cases for rate limiter."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis = Mock()
        redis.pipeline = Mock(return_value=Mock(
            incr=Mock(return_value=Mock()),
            expire=Mock(return_value=Mock()),
            execute=Mock(return_value=[1, True])
        ))
        return redis

    @pytest.fixture
    def rate_limiter(self, mock_redis):
        """Create rate limiter instance."""
        return RateLimiter(redis_client=mock_redis)

    def test_check_rate_limit_allows_under_limit(self, rate_limiter, mock_redis):
        """Test rate limiter allows requests under limit."""
        # Arrange
        key_id = "key123"
        limit = 100
        mock_redis.pipeline().execute.return_value = [50, True]  # 50 requests so far
        
        # Act
        result = rate_limiter.check_rate_limit(key_id, limit)
        
        # Assert
        assert result.allowed is True
        assert result.current_requests == 50
        assert result.limit == 100
        assert result.remaining == 50
        assert result.reset_time is not None

    def test_check_rate_limit_blocks_over_limit(self, rate_limiter, mock_redis):
        """Test rate limiter blocks requests over limit."""
        # Arrange
        key_id = "key123"
        limit = 100
        mock_redis.pipeline().execute.return_value = [101, True]  # Over limit
        
        # Act
        result = rate_limiter.check_rate_limit(key_id, limit)
        
        # Assert
        assert result.allowed is False
        assert result.current_requests == 101
        assert result.limit == 100
        assert result.remaining == 0

    def test_check_rate_limit_with_burst(self, rate_limiter, mock_redis):
        """Test rate limiter with burst allowance."""
        # Arrange
        key_id = "key123"
        limit = 100
        burst = 10
        mock_redis.pipeline().execute.return_value = [105, True]  # Within burst
        
        # Act
        result = rate_limiter.check_rate_limit(key_id, limit, burst_limit=burst)
        
        # Assert
        assert result.allowed is True
        assert result.current_requests == 105
        assert result.limit == 100
        assert result.burst_limit == 10

    def test_check_rate_limit_blocks_over_burst(self, rate_limiter, mock_redis):
        """Test rate limiter blocks requests over burst limit."""
        # Arrange
        key_id = "key123"
        limit = 100
        burst = 10
        mock_redis.pipeline().execute.return_value = [111, True]  # Over burst
        
        # Act
        result = rate_limiter.check_rate_limit(key_id, limit, burst_limit=burst)
        
        # Assert
        assert result.allowed is False
        assert result.current_requests == 111

    def test_sliding_window_rate_limit(self, rate_limiter, mock_redis):
        """Test sliding window rate limiting."""
        # Arrange
        key_id = "key123"
        limit = 100
        window_seconds = 3600
        
        # Mock Redis sorted set operations for sliding window
        mock_redis.zremrangebyscore = Mock(return_value=10)  # Removed 10 old entries
        mock_redis.zadd = Mock(return_value=1)
        mock_redis.zcard = Mock(return_value=50)  # 50 requests in window
        mock_redis.expire = Mock(return_value=True)
        
        # Act
        result = rate_limiter.check_sliding_window(key_id, limit, window_seconds)
        
        # Assert
        assert result.allowed is True
        assert result.current_requests == 50
        assert result.limit == 100
        
        # Verify Redis operations
        mock_redis.zremrangebyscore.assert_called_once()
        mock_redis.zadd.assert_called_once()
        mock_redis.zcard.assert_called_once()

    def test_get_rate_limit_info(self, rate_limiter, mock_redis):
        """Test getting rate limit information."""
        # Arrange
        key_id = "key123"
        mock_redis.get = Mock(return_value=b"75")
        mock_redis.ttl = Mock(return_value=1800)  # 30 minutes remaining
        
        # Act
        result = rate_limiter.get_rate_limit_info(key_id)
        
        # Assert
        assert result["current_requests"] == 75
        assert result["reset_in_seconds"] == 1800

    def test_reset_rate_limit(self, rate_limiter, mock_redis):
        """Test resetting rate limit for a key."""
        # Arrange
        key_id = "key123"
        
        # Act
        rate_limiter.reset_rate_limit(key_id)
        
        # Assert
        mock_redis.delete.assert_called_with(f"rate_limit:hourly:{key_id}")


class TestRateLimitMiddleware:
    """Test cases for rate limit middleware integration."""

    @pytest.fixture
    def mock_rate_limiter(self):
        """Mock rate limiter."""
        return Mock()

    @pytest.fixture
    def app(self, mock_rate_limiter):
        """Create FastAPI app with rate limit middleware."""
        from src.middleware.rate_limiter import RateLimitMiddleware
        
        app = FastAPI()
        
        # Add middleware
        app.add_middleware(
            RateLimitMiddleware,
            rate_limiter=mock_rate_limiter
        )
        
        # Add test endpoint
        @app.get("/api/test")
        async def test_endpoint(request: Request):
            return {"message": "Success"}
        
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_middleware_allows_request_under_limit(self, client, mock_rate_limiter):
        """Test middleware allows requests under rate limit."""
        # Arrange
        mock_rate_limiter.check_rate_limit.return_value = Mock(
            allowed=True,
            current_requests=50,
            limit=100,
            remaining=50,
            reset_time=int(time.time()) + 3600
        )
        
        # Need to set request state to simulate authenticated request
        with patch('src.middleware.rate_limiter.get_request_state') as mock_state:
            mock_state.return_value = Mock(
                api_key_id="key123",
                rate_limit_per_hour=100
            )
            
            # Act
            response = client.get("/api/test")
        
        # Assert
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "100"
        assert response.headers["X-RateLimit-Remaining"] == "50"
        assert "X-RateLimit-Reset" in response.headers

    def test_middleware_blocks_request_over_limit(self, client, mock_rate_limiter):
        """Test middleware blocks requests over rate limit."""
        # Arrange
        mock_rate_limiter.check_rate_limit.return_value = Mock(
            allowed=False,
            current_requests=101,
            limit=100,
            remaining=0,
            reset_time=int(time.time()) + 1800
        )
        
        with patch('src.middleware.rate_limiter.get_request_state') as mock_state:
            mock_state.return_value = Mock(
                api_key_id="key123",
                rate_limit_per_hour=100
            )
            
            # Act
            response = client.get("/api/test")
        
        # Assert
        assert response.status_code == 429
        assert response.json()["detail"] == "Rate limit exceeded"
        assert response.headers["X-RateLimit-Limit"] == "100"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert "Retry-After" in response.headers

    def test_middleware_skips_unauthenticated_requests(self, client, mock_rate_limiter):
        """Test middleware skips rate limiting for unauthenticated requests."""
        # Arrange
        with patch('src.middleware.rate_limiter.get_request_state') as mock_state:
            mock_state.return_value = None  # No auth state
            
            # Act
            response = client.get("/api/test")
        
        # Assert
        assert response.status_code == 200
        mock_rate_limiter.check_rate_limit.assert_not_called()
        assert "X-RateLimit-Limit" not in response.headers

    def test_middleware_handles_rate_limiter_errors(self, client, mock_rate_limiter):
        """Test middleware handles rate limiter errors gracefully."""
        # Arrange
        mock_rate_limiter.check_rate_limit.side_effect = Exception("Redis error")
        
        with patch('src.middleware.rate_limiter.get_request_state') as mock_state:
            mock_state.return_value = Mock(
                api_key_id="key123",
                rate_limit_per_hour=100
            )
            
            # Act
            response = client.get("/api/test")
        
        # Assert
        # Should allow request on error (fail open)
        assert response.status_code == 200

    def test_middleware_uses_custom_rate_limit(self, client, mock_rate_limiter):
        """Test middleware uses custom rate limit from API key."""
        # Arrange
        mock_rate_limiter.check_rate_limit.return_value = Mock(
            allowed=True,
            current_requests=10,
            limit=500,  # Custom limit
            remaining=490,
            reset_time=int(time.time()) + 3600
        )
        
        with patch('src.middleware.rate_limiter.get_request_state') as mock_state:
            mock_state.return_value = Mock(
                api_key_id="key123",
                rate_limit_per_hour=500  # Custom limit
            )
            
            # Act
            response = client.get("/api/test")
        
        # Assert
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "500"
        mock_rate_limiter.check_rate_limit.assert_called_with("key123", 500)


class TestRateLimitHeaders:
    """Test cases for rate limit response headers."""

    def test_rate_limit_headers_format(self):
        """Test rate limit headers follow standard format."""
        # Arrange
        from src.middleware.rate_limiter import format_rate_limit_headers
        
        result = Mock(
            allowed=True,
            limit=1000,
            remaining=750,
            reset_time=1609459200  # 2021-01-01 00:00:00 UTC
        )
        
        # Act
        headers = format_rate_limit_headers(result)
        
        # Assert
        assert headers["X-RateLimit-Limit"] == "1000"
        assert headers["X-RateLimit-Remaining"] == "750"
        assert headers["X-RateLimit-Reset"] == "1609459200"

    def test_rate_limit_headers_with_retry_after(self):
        """Test rate limit headers include Retry-After when blocked."""
        # Arrange
        from src.middleware.rate_limiter import format_rate_limit_headers
        
        current_time = int(time.time())
        result = Mock(
            allowed=False,
            limit=100,
            remaining=0,
            reset_time=current_time + 1800  # 30 minutes from now
        )
        
        # Act
        with patch('time.time', return_value=current_time):
            headers = format_rate_limit_headers(result)
        
        # Assert
        assert headers["Retry-After"] == "1800"