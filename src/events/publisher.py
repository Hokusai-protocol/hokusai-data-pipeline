"""
Event publisher for Hokusai ML Platform
"""
import json
import logging
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of events in the system"""
    TOKEN_READY_FOR_DEPLOY = "token_ready_for_deploy"
    MODEL_REGISTERED = "model_registered"
    MODEL_VALIDATION_FAILED = "model_validation_failed"
    MODEL_DEPLOYED = "model_deployed"
    METRIC_IMPROVED = "metric_improved"
    DELTAONE_ACHIEVED = "deltaone_achieved"
    

class Event:
    """Represents an event in the system"""
    
    def __init__(self, event_type: EventType, payload: Dict[str, Any], 
                 source: str = "hokusai-ml-platform"):
        self.event_id = self._generate_event_id()
        self.event_type = event_type
        self.payload = payload
        self.source = source
        self.timestamp = datetime.utcnow()
        
    def _generate_event_id(self) -> str:
        """Generate unique event ID"""
        import uuid
        return str(uuid.uuid4())
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload
        }
        
    def to_json(self) -> str:
        """Convert event to JSON string"""
        return json.dumps(self.to_dict(), default=str)


class EventHandler(ABC):
    """Abstract base class for event handlers"""
    
    @abstractmethod
    def handle(self, event: Event) -> bool:
        """Handle an event and return success status"""
        pass
        
    @abstractmethod
    def can_handle(self, event_type: EventType) -> bool:
        """Check if handler can handle this event type"""
        pass


class EventPublisher:
    """Publishes events to multiple handlers"""
    
    def __init__(self):
        self.handlers: List[EventHandler] = []
        
    def register_handler(self, handler: EventHandler):
        """Register an event handler"""
        self.handlers.append(handler)
        logger.info(f"Registered event handler: {handler.__class__.__name__}")
        
    def publish(self, event_type: EventType, payload: Dict[str, Any]) -> bool:
        """
        Publish an event to all registered handlers
        
        Args:
            event_type: Type of event to publish
            payload: Event payload data
            
        Returns:
            True if at least one handler successfully processed the event
        """
        event = Event(event_type, payload)
        
        logger.info(f"Publishing event: {event_type.value}")
        logger.debug(f"Event payload: {json.dumps(payload, default=str)}")
        
        success_count = 0
        for handler in self.handlers:
            if handler.can_handle(event_type):
                try:
                    if handler.handle(event):
                        success_count += 1
                        logger.debug(f"Handler {handler.__class__.__name__} processed event successfully")
                    else:
                        logger.warning(f"Handler {handler.__class__.__name__} failed to process event")
                except Exception as e:
                    logger.error(f"Error in handler {handler.__class__.__name__}: {str(e)}")
                    
        if success_count == 0:
            logger.warning(f"No handlers successfully processed event {event_type.value}")
            
        return success_count > 0
        
    def publish_token_ready(self, token_id: str, mlflow_run_id: str, 
                          metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Convenience method to publish token_ready_for_deploy event"""
        payload = {
            "token_id": token_id,
            "mlflow_run_id": mlflow_run_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        if metadata:
            payload["metadata"] = metadata
            
        return self.publish(EventType.TOKEN_READY_FOR_DEPLOY, payload)
        
    def publish_model_registered(self, token_id: str, mlflow_run_id: str,
                               metric_name: str, metric_value: float,
                               baseline_value: float) -> bool:
        """Convenience method to publish model_registered event"""
        payload = {
            "token_id": token_id,
            "mlflow_run_id": mlflow_run_id,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "baseline_value": baseline_value,
            "improvement": metric_value - baseline_value,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return self.publish(EventType.MODEL_REGISTERED, payload)