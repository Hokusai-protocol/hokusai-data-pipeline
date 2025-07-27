"""Base classes for message publishers."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PublisherException(Exception):
    """Exception raised by publishers."""
    pass


class AbstractPublisher(ABC):
    """Abstract base class for message publishers."""
    
    @abstractmethod
    def publish(self, message: Dict[str, Any], queue_name: str) -> bool:
        """Publish a message to the specified queue.
        
        Args:
            message: Message to publish
            queue_name: Name of the queue/topic
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Check health of the publisher connection.
        
        Returns:
            Dict with health status information
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close publisher connections and clean up resources."""
        pass
    
    @abstractmethod
    def get_queue_depth(self, queue_name: str) -> Optional[int]:
        """Get number of messages in queue.
        
        Args:
            queue_name: Name of the queue
            
        Returns:
            Number of messages or None if unavailable
        """
        pass
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()