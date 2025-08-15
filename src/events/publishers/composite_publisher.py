"""Composite publisher that publishes to multiple publishers simultaneously."""

import logging
from typing import Any, Dict, List, Optional

from .base import AbstractPublisher, PublisherException

logger = logging.getLogger(__name__)


class CompositePublisher(AbstractPublisher):
    """Publisher that delegates to multiple publishers for dual publishing.
    
    This is useful during migration periods where messages need to be
    published to both old and new systems simultaneously.
    """
    
    def __init__(self, publishers: List[AbstractPublisher]):
        """Initialize with list of publishers.
        
        Args:
            publishers: List of publisher instances to delegate to
        """
        if not publishers:
            raise ValueError("At least one publisher must be provided")
        
        self.publishers = publishers
        logger.info(f"Created composite publisher with {len(publishers)} publishers")
    
    def publish(self, message: Dict[str, Any]) -> bool:
        """Publish message to all configured publishers.
        
        Args:
            message: Message to publish
            
        Returns:
            True if at least one publisher succeeded
        """
        successes = 0
        failures = []
        
        for publisher in self.publishers:
            try:
                if publisher.publish(message):
                    successes += 1
                    logger.debug(f"Published to {type(publisher).__name__}")
                else:
                    failures.append(f"{type(publisher).__name__}: returned False")
            except Exception as e:
                failures.append(f"{type(publisher).__name__}: {str(e)}")
                logger.warning(f"Failed to publish to {type(publisher).__name__}: {e}")
        
        if failures:
            logger.warning(f"Some publishers failed: {', '.join(failures)}")
        
        # Return True if at least one publisher succeeded
        return successes > 0
    
    def publish_model_ready(
        self,
        model_id: str,
        token_symbol: str,
        metric_name: str,
        baseline_value: float,
        current_value: float,
        **kwargs
    ) -> bool:
        """Publish model ready message to all publishers.
        
        Args:
            model_id: Model identifier
            token_symbol: Token symbol
            metric_name: Metric name
            baseline_value: Baseline value
            current_value: Current value
            **kwargs: Additional message fields
            
        Returns:
            True if at least one publisher succeeded
        """
        successes = 0
        failures = []
        
        for publisher in self.publishers:
            try:
                if publisher.publish_model_ready(
                    model_id=model_id,
                    token_symbol=token_symbol,
                    metric_name=metric_name,
                    baseline_value=baseline_value,
                    current_value=current_value,
                    **kwargs
                ):
                    successes += 1
                    logger.debug(f"Published model_ready to {type(publisher).__name__}")
                else:
                    failures.append(f"{type(publisher).__name__}: returned False")
            except Exception as e:
                failures.append(f"{type(publisher).__name__}: {str(e)}")
                logger.warning(f"Failed to publish model_ready to {type(publisher).__name__}: {e}")
        
        if failures:
            logger.warning(f"Some publishers failed for model_ready: {', '.join(failures)}")
        
        return successes > 0
    
    def health_check(self) -> Dict[str, Any]:
        """Check health of all publishers.
        
        Returns:
            Composite health status
        """
        health_statuses = {}
        all_healthy = True
        
        for publisher in self.publishers:
            publisher_name = type(publisher).__name__
            try:
                health = publisher.health_check()
                health_statuses[publisher_name] = health
                if health.get("status") != "healthy":
                    all_healthy = False
            except Exception as e:
                health_statuses[publisher_name] = {
                    "status": "error",
                    "error": str(e)
                }
                all_healthy = False
        
        return {
            "status": "healthy" if all_healthy else "degraded",
            "publishers": health_statuses,
            "total_publishers": len(self.publishers),
            "healthy_publishers": sum(
                1 for h in health_statuses.values()
                if h.get("status") == "healthy"
            )
        }
    
    def close(self) -> None:
        """Close all publishers."""
        for publisher in self.publishers:
            try:
                publisher.close()
                logger.debug(f"Closed {type(publisher).__name__}")
            except Exception as e:
                logger.warning(f"Error closing {type(publisher).__name__}: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()