"""Event handlers for different event backends
"""
import json
import logging
import os
from typing import Dict, Any, Optional, List
import requests
from .publisher import Event, EventHandler, EventType

logger = logging.getLogger(__name__)


class WebhookHandler(EventHandler):
    """Handles events by sending webhooks"""

    def __init__(self, webhook_url: str, headers: Optional[Dict[str, str]] = None,
                 timeout: int = 30):
        self.webhook_url = webhook_url
        self.headers = headers or {"Content-Type": "application/json"}
        self.timeout = timeout
        self.supported_events = {EventType.TOKEN_READY_FOR_DEPLOY, EventType.MODEL_REGISTERED}

    def can_handle(self, event_type: EventType) -> bool:
        """Check if handler supports this event type"""
        return event_type in self.supported_events

    def handle(self, event: Event) -> bool:
        """Send event as webhook"""
        try:
            response = requests.post(
                self.webhook_url,
                json=event.to_dict(),
                headers=self.headers,
                timeout=self.timeout
            )

            if response.status_code in [200, 201, 202, 204]:
                logger.info(f"Webhook sent successfully to {self.webhook_url}")
                return True
            else:
                logger.error(f"Webhook failed with status {response.status_code}: {response.text}")
                return False

        except requests.RequestException as e:
            logger.error(f"Failed to send webhook: {str(e)}")
            return False


class PubSubHandler(EventHandler):
    """Handles events using publish/subscribe pattern"""

    def __init__(self, topic_name: str, project_id: Optional[str] = None):
        self.topic_name = topic_name
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.publisher = None
        self.topic_path = None

        # Initialize Google Pub/Sub client if available
        try:
            from google.cloud import pubsub_v1
            self.publisher = pubsub_v1.PublisherClient()
            self.topic_path = self.publisher.topic_path(self.project_id, self.topic_name)
            logger.info(f"Initialized Pub/Sub handler for topic: {self.topic_name}")
        except ImportError:
            logger.warning("Google Cloud Pub/Sub not available. Install google-cloud-pubsub to use this handler.")
        except Exception as e:
            logger.error(f"Failed to initialize Pub/Sub client: {str(e)}")

    def can_handle(self, event_type: EventType) -> bool:
        """All events can be published to Pub/Sub"""
        return self.publisher is not None

    def handle(self, event: Event) -> bool:
        """Publish event to Pub/Sub topic"""
        if not self.publisher:
            logger.error("Pub/Sub client not initialized")
            return False

        try:
            # Convert event to bytes
            message_data = event.to_json().encode("utf-8")

            # Publish message
            future = self.publisher.publish(
                self.topic_path,
                message_data,
                event_type=event.event_type.value,
                event_id=event.event_id
            )

            # Wait for publish to complete
            message_id = future.result()
            logger.info(f"Published event {event.event_id} to Pub/Sub with message ID: {message_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish to Pub/Sub: {str(e)}")
            return False


class DatabaseWatcherHandler(EventHandler):
    """Handles events by writing to database for watchers to poll"""

    def __init__(self, db_connection):
        self.db_connection = db_connection

    def can_handle(self, event_type: EventType) -> bool:
        """All events can be written to database"""
        return True

    def handle(self, event: Event) -> bool:
        """Write event to database events table"""
        try:
            query = """
                INSERT INTO events (event_id, event_type, source, timestamp, payload, processed)
                VALUES (:event_id, :event_type, :source, :timestamp, :payload, :processed)
            """

            params = {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "source": event.source,
                "timestamp": event.timestamp,
                "payload": json.dumps(event.payload),
                "processed": False
            }

            self.db_connection.execute_update(query, params)
            logger.info(f"Event {event.event_id} written to database")
            return True

        except Exception as e:
            logger.error(f"Failed to write event to database: {str(e)}")
            return False


class ConsoleHandler(EventHandler):
    """Simple handler that logs events to console (useful for testing)"""

    def __init__(self):
        self.logger = logging.getLogger("hokusai.events.console")

    def can_handle(self, event_type: EventType) -> bool:
        """Handle all events"""
        return True

    def handle(self, event: Event) -> bool:
        """Log event to console"""
        self.logger.info(f"Event: {event.event_type.value}")
        self.logger.info(f"Event ID: {event.event_id}")
        self.logger.info(f"Timestamp: {event.timestamp}")
        self.logger.info(f"Payload: {json.dumps(event.payload, indent=2, default=str)}")
        return True


class CompositeHandler(EventHandler):
    """Combines multiple handlers"""

    def __init__(self, handlers: List[EventHandler]):
        self.handlers = handlers

    def can_handle(self, event_type: EventType) -> bool:
        """Can handle if any sub-handler can handle"""
        return any(handler.can_handle(event_type) for handler in self.handlers)

    def handle(self, event: Event) -> bool:
        """Handle event with all applicable sub-handlers"""
        results = []
        for handler in self.handlers:
            if handler.can_handle(event.event_type):
                try:
                    results.append(handler.handle(event))
                except Exception as e:
                    logger.error(f"Handler {handler.__class__.__name__} failed: {str(e)}")
                    results.append(False)

        # Return True if at least one handler succeeded
        return any(results)
