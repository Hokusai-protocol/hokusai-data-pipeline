"""
Circuit breaker pattern implementation for handling Redis failures gracefully.

This module provides a circuit breaker that can wrap Redis operations and prevent
cascading failures when Redis is unavailable.
"""

import logging
import time
from enum import Enum
from typing import Any, Callable, Optional, Type, Union

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Failing, blocking calls
    HALF_OPEN = "HALF_OPEN"  # Testing recovery


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """
    Circuit breaker implementation for handling service failures.
    
    The circuit breaker has three states:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Service is failing, calls are blocked
    - HALF_OPEN: Testing recovery, limited calls allowed
    
    Usage:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
        
        # Use as context manager
        try:
            with cb:
                redis_client.ping()
        except CircuitBreakerError:
            # Circuit is open, use fallback
            pass
            
        # Or wrap functions
        @cb
        def redis_operation():
            return redis_client.get("key")
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Union[Type[Exception], tuple] = Exception,
        success_threshold: int = 1,
        name: Optional[str] = None
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception types that trigger circuit breaker
            success_threshold: Successful calls needed to close circuit in half-open state
            name: Optional name for logging/monitoring
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.success_threshold = success_threshold
        self.name = name or f"CircuitBreaker-{id(self)}"
        
        # State tracking
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitBreakerState.CLOSED
        
        logger.info(
            f"Initialized {self.name}: failure_threshold={failure_threshold}, "
            f"recovery_timeout={recovery_timeout}s"
        )
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to wrap functions with circuit breaker."""
        def wrapper(*args, **kwargs):
            with self:
                return func(*args, **kwargs)
        return wrapper
    
    def __enter__(self):
        """Context manager entry - check if call should be allowed."""
        current_time = time.time()
        
        if self.state == CircuitBreakerState.CLOSED:
            # Normal operation
            return self
        
        elif self.state == CircuitBreakerState.OPEN:
            # Check if we should transition to half-open
            if (self.last_failure_time and 
                current_time - self.last_failure_time >= self.recovery_timeout):
                
                self._transition_to_half_open()
                return self
            else:
                # Circuit is still open
                remaining_time = self.recovery_timeout - (current_time - (self.last_failure_time or 0))
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.name}' is OPEN. "
                    f"Recovery attempt in {remaining_time:.1f}s"
                )
        
        elif self.state == CircuitBreakerState.HALF_OPEN:
            # Allow limited testing
            return self
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - handle success/failure."""
        if exc_type is None:
            # Success case
            self._record_success()
        elif isinstance(exc_val, self.expected_exception):
            # Expected failure case
            self._record_failure()
            # Re-raise the original exception, not CircuitBreakerError
            return False
        # For unexpected exceptions, don't interfere
        return False
    
    def _record_success(self):
        """Record a successful operation."""
        current_time = time.time()
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self._transition_to_closed()
        elif self.state == CircuitBreakerState.CLOSED:
            # Reset failure count on success
            if self.failure_count > 0:
                logger.debug(f"{self.name}: Success - resetting failure count")
                self.failure_count = 0
    
    def _record_failure(self):
        """Record a failed operation."""
        current_time = time.time()
        self.failure_count += 1
        self.last_failure_time = current_time
        
        logger.warning(
            f"{self.name}: Failure recorded ({self.failure_count}/{self.failure_threshold})"
        )
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            # Failed during recovery test - back to open
            self._transition_to_open()
        elif (self.state == CircuitBreakerState.CLOSED and 
              self.failure_count >= self.failure_threshold):
            # Too many failures - open the circuit
            self._transition_to_open()
    
    def _transition_to_closed(self):
        """Transition to CLOSED state (normal operation)."""
        previous_state = self.state
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        
        logger.info(f"{self.name}: {previous_state.value} -> CLOSED (recovered)")
    
    def _transition_to_open(self):
        """Transition to OPEN state (blocking calls)."""
        previous_state = self.state
        self.state = CircuitBreakerState.OPEN
        self.success_count = 0
        
        logger.warning(
            f"{self.name}: {previous_state.value} -> OPEN "
            f"(recovery in {self.recovery_timeout}s)"
        )
    
    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state (testing recovery)."""
        previous_state = self.state
        self.state = CircuitBreakerState.HALF_OPEN
        self.success_count = 0
        
        logger.info(f"{self.name}: {previous_state.value} -> HALF_OPEN (testing recovery)")
    
    @property
    def is_closed(self) -> bool:
        """Check if circuit is in CLOSED state."""
        return self.state == CircuitBreakerState.CLOSED
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is in OPEN state."""
        return self.state == CircuitBreakerState.OPEN
    
    @property
    def is_half_open(self) -> bool:
        """Check if circuit is in HALF_OPEN state."""
        return self.state == CircuitBreakerState.HALF_OPEN
    
    def reset(self):
        """Manually reset the circuit breaker to CLOSED state."""
        previous_state = self.state
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        
        logger.info(f"{self.name}: Manually reset from {previous_state.value} to CLOSED")
    
    def get_stats(self) -> dict:
        """Get circuit breaker statistics for monitoring."""
        current_time = time.time()
        
        stats = {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "recovery_timeout": self.recovery_timeout
        }
        
        if self.last_failure_time:
            stats["last_failure_time"] = self.last_failure_time
            stats["time_since_last_failure"] = current_time - self.last_failure_time
            
            if self.state == CircuitBreakerState.OPEN:
                remaining_time = self.recovery_timeout - (current_time - self.last_failure_time)
                stats["recovery_time_remaining"] = max(0, remaining_time)
        
        return stats


class RedisCircuitBreaker(CircuitBreaker):
    """Circuit breaker specifically configured for Redis operations."""
    
    def __init__(self, **kwargs):
        """Initialize Redis circuit breaker with Redis-specific defaults."""
        from redis.exceptions import ConnectionError, TimeoutError, RedisError
        
        defaults = {
            "failure_threshold": 3,
            "recovery_timeout": 30,
            "expected_exception": (ConnectionError, TimeoutError, RedisError),
            "success_threshold": 2,
            "name": "Redis-CircuitBreaker"
        }
        
        # Override defaults with provided kwargs
        defaults.update(kwargs)
        super().__init__(**defaults)


# Global registry for circuit breakers (for monitoring/management)
_circuit_breakers = {}


def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    """
    Get or create a named circuit breaker.
    
    This ensures singleton behavior for circuit breakers with the same name,
    which is useful for shared resources like Redis connections.
    
    Args:
        name: Circuit breaker name
        **kwargs: Circuit breaker configuration
        
    Returns:
        CircuitBreaker instance
    """
    if name not in _circuit_breakers:
        kwargs["name"] = name
        _circuit_breakers[name] = CircuitBreaker(**kwargs)
        
    return _circuit_breakers[name]


def get_redis_circuit_breaker() -> RedisCircuitBreaker:
    """Get the singleton Redis circuit breaker."""
    if "redis" not in _circuit_breakers:
        _circuit_breakers["redis"] = RedisCircuitBreaker()
    
    return _circuit_breakers["redis"]


def reset_all_circuit_breakers():
    """Reset all registered circuit breakers (useful for testing)."""
    for cb in _circuit_breakers.values():
        cb.reset()
    logger.info(f"Reset {len(_circuit_breakers)} circuit breakers")


def get_all_circuit_breaker_stats() -> dict:
    """Get statistics for all registered circuit breakers."""
    return {name: cb.get_stats() for name, cb in _circuit_breakers.items()}


def cleanup_circuit_breakers():
    """Clean up circuit breaker registry (useful for testing)."""
    global _circuit_breakers
    _circuit_breakers.clear()
    logger.debug("Cleaned up circuit breaker registry")