"""Factory for creating message publishers."""

import logging
import os
from typing import Optional

from .base import AbstractPublisher
from .redis_publisher import RedisPublisher

logger = logging.getLogger(__name__)


def create_publisher(
    publisher_type: Optional[str] = None,
    **kwargs
) -> AbstractPublisher:
    """Create a message publisher based on configuration.
    
    Args:
        publisher_type: Type of publisher ("redis", "sqs", etc.)
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
        redis_url = kwargs.get("redis_url") or os.getenv(
            "REDIS_URL", "redis://localhost:6379/0"
        )
        return RedisPublisher(redis_url=redis_url, **kwargs)
    
    elif publisher_type == "sqs":
        # Placeholder for future SQS implementation
        raise NotImplementedError("SQS publisher not yet implemented")
    
    else:
        raise ValueError(f"Unknown publisher type: {publisher_type}")


# Singleton instance for application-wide use
_publisher_instance: Optional[AbstractPublisher] = None


def get_publisher() -> AbstractPublisher:
    """Get the singleton publisher instance.
    
    Returns:
        Publisher instance
    """
    global _publisher_instance
    
    if _publisher_instance is None:
        _publisher_instance = create_publisher()
        logger.info(f"Created publisher instance: {type(_publisher_instance).__name__}")
    
    return _publisher_instance


def close_publisher() -> None:
    """Close the singleton publisher instance."""
    global _publisher_instance
    
    if _publisher_instance is not None:
        _publisher_instance.close()
        _publisher_instance = None
        logger.info("Closed publisher instance")