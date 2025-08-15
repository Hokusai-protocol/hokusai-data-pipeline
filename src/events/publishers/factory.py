"""Factory for creating message publishers with fallback support."""

import logging
import os
from typing import Optional

from .base import AbstractPublisher
from .redis_publisher import RedisPublisher, RedisPublisherWithCircuitBreaker
from .fallback_publisher import FallbackPublisher
from .webhook_publisher import WebhookPublisher

logger = logging.getLogger(__name__)


def create_publisher(
    publisher_type: Optional[str] = None,
    **kwargs
) -> AbstractPublisher:
    """Create a message publisher based on configuration.
    
    Args:
        publisher_type: Type of publisher ("redis", "webhook", "sqs", etc.)
        **kwargs: Additional arguments for the publisher
        
    Returns:
        Publisher instance
        
    Raises:
        ValueError: Unknown publisher type
    """
    # Default to environment variable or Redis
    if publisher_type is None:
        publisher_type = os.getenv("MESSAGE_QUEUE_TYPE", "redis").lower()
    
    if publisher_type == "redis":
        # Check Redis configuration from settings
        from src.api.utils.config import get_settings
        try:
            settings = get_settings()
            if not settings.redis_enabled:
                logger.warning("Redis not enabled - check configuration")
                raise ValueError("Redis not enabled")
                
            redis_url = kwargs.get("redis_url") or settings.redis_url
            logger.info(f"Creating Redis publisher with URL: {redis_url}")
            return RedisPublisherWithCircuitBreaker(redis_url=redis_url, **kwargs)
            
        except Exception as e:
            logger.error(f"Failed to create Redis publisher: {e}")
            raise
    
    elif publisher_type == "webhook":
        webhook_url = kwargs.get("webhook_url")
        if not webhook_url:
            webhook_url = os.getenv("WEBHOOK_URL")
        
        if not webhook_url:
            raise ValueError("webhook_url is required for webhook publisher")
        
        secret_key = kwargs.get("secret_key") or os.getenv("WEBHOOK_SECRET_KEY")
        config = kwargs.get("config", {})
        
        logger.info(f"Creating webhook publisher for URL: {webhook_url}")
        return WebhookPublisher(
            webhook_url=webhook_url,
            secret_key=secret_key,
            config=config
        )
    
    elif publisher_type == "fallback":
        return FallbackPublisher(**kwargs)
    
    elif publisher_type == "sqs":
        # Placeholder for future SQS implementation
        raise NotImplementedError("SQS publisher not yet implemented")
    
    else:
        raise ValueError(f"Unknown publisher type: {publisher_type}")


def create_publisher_with_fallback(**kwargs) -> AbstractPublisher:
    """
    Create a publisher with automatic fallback to FallbackPublisher if Redis fails.
    
    This function implements the circuit breaker pattern and graceful degradation:
    1. Try to create Redis publisher
    2. Test connection with circuit breaker
    3. Fall back to FallbackPublisher if Redis unavailable
    
    Args:
        **kwargs: Publisher configuration arguments
        
    Returns:
        Publisher instance (Redis or Fallback)
    """
    # Try Redis first
    try:
        from src.utils.circuit_breaker import get_redis_circuit_breaker
        
        # Get circuit breaker for Redis
        circuit_breaker = get_redis_circuit_breaker()
        
        # If circuit breaker is open, use fallback immediately
        if circuit_breaker.is_open:
            logger.warning("Redis circuit breaker is OPEN - using fallback publisher")
            return FallbackPublisher(**kwargs)
        
        # Try to create Redis publisher
        try:
            redis_publisher = create_publisher("redis", **kwargs)
            
            # Test the connection through circuit breaker
            with circuit_breaker:
                health = redis_publisher.health_check()
                if health.get("status") != "healthy":
                    raise Exception(f"Redis health check failed: {health}")
            
            logger.info("Redis publisher created successfully")
            return redis_publisher
            
        except Exception as e:
            logger.warning(f"Redis publisher creation/test failed: {e}")
            # Circuit breaker will record this failure
            # Fall through to create fallback publisher
            
    except ImportError as e:
        logger.error(f"Failed to import Redis dependencies: {e}")
    except Exception as e:
        logger.error(f"Unexpected error creating Redis publisher: {e}")
    
    # Create fallback publisher
    logger.info("Creating fallback publisher due to Redis unavailability")
    return FallbackPublisher(**kwargs)


# Singleton instance for application-wide use
_publisher_instance: Optional[AbstractPublisher] = None


def get_publisher() -> AbstractPublisher:
    """Get the singleton publisher instance.
    
    Priority order:
    1. Webhook (if configured) - PRIMARY
    2. Redis (if webhook not configured and Redis available) - LEGACY
    3. Fallback (if nothing else available)
    
    Returns:
        Publisher instance (Webhook, Redis, or Fallback)
    """
    global _publisher_instance
    
    if _publisher_instance is None:
        # Check for webhook configuration first (this is the new preferred method)
        webhook_url = os.getenv("WEBHOOK_URL")
        if webhook_url:
            try:
                webhook_secret = os.getenv("WEBHOOK_SECRET")
                _publisher_instance = WebhookPublisher(
                    webhook_url=webhook_url,
                    secret_key=webhook_secret,
                    config={
                        "timeout": int(os.getenv("WEBHOOK_TIMEOUT", "30")),
                        "max_retries": int(os.getenv("WEBHOOK_MAX_RETRIES", "5")),
                        "retry_delay": int(os.getenv("WEBHOOK_RETRY_DELAY", "2")),
                        "circuit_breaker_failure_threshold": int(
                            os.getenv("WEBHOOK_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")
                        ),
                        "circuit_breaker_recovery_time": int(
                            os.getenv("WEBHOOK_CIRCUIT_BREAKER_RECOVERY_TIME", "60")
                        ),
                    }
                )
                logger.info(f"Created webhook publisher for: {webhook_url}")
                
            except Exception as e:
                logger.error(f"Failed to create webhook publisher: {e}")
                # Fall back to fallback publisher (not Redis since no consumers exist)
                logger.info("Using fallback publisher due to webhook failure")
                _publisher_instance = FallbackPublisher()
        else:
            # No webhook configured, try Redis for backward compatibility
            # Note: Since no Redis consumers exist in production, this is temporary
            logger.warning(
                "No WEBHOOK_URL configured. Please configure webhooks as Redis pub/sub "
                "is deprecated and has no active consumers."
            )
            _publisher_instance = create_publisher_with_fallback()
        
        logger.info(f"Created publisher instance: {type(_publisher_instance).__name__}")
    
    return _publisher_instance


def close_publisher() -> None:
    """Close the singleton publisher instance."""
    global _publisher_instance
    
    if _publisher_instance is not None:
        _publisher_instance.close()
        _publisher_instance = None
        logger.info("Closed publisher instance")