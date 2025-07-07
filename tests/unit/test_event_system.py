"""
Unit tests for the event system
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from events import EventPublisher, EventType, WebhookHandler, ConsoleHandler
from events.publisher import Event
from events.handlers import PubSubHandler, DatabaseWatcherHandler, CompositeHandler


class TestEvent:
    """Test the Event class"""
    
    def test_event_creation(self):
        """Test creating an event"""
        payload = {"token_id": "XRAY", "status": "ready"}
        event = Event(EventType.TOKEN_READY_FOR_DEPLOY, payload)
        
        assert event.event_type == EventType.TOKEN_READY_FOR_DEPLOY
        assert event.payload == payload
        assert event.source == "hokusai-ml-platform"
        assert isinstance(event.timestamp, datetime)
        assert event.event_id is not None
    
    def test_event_to_dict(self):
        """Test converting event to dictionary"""
        payload = {"token_id": "XRAY"}
        event = Event(EventType.MODEL_REGISTERED, payload)
        
        event_dict = event.to_dict()
        assert event_dict["event_type"] == "model_registered"
        assert event_dict["payload"] == payload
        assert "timestamp" in event_dict
        assert "event_id" in event_dict
    
    def test_event_to_json(self):
        """Test converting event to JSON"""
        payload = {"token_id": "XRAY", "value": 0.85}
        event = Event(EventType.METRIC_IMPROVED, payload)
        
        event_json = event.to_json()
        parsed = json.loads(event_json)
        assert parsed["event_type"] == "metric_improved"
        assert parsed["payload"]["value"] == 0.85


class TestEventPublisher:
    """Test the EventPublisher class"""
    
    @pytest.fixture
    def publisher(self):
        return EventPublisher()
    
    def test_register_handler(self, publisher):
        """Test registering event handlers"""
        handler = Mock()
        publisher.register_handler(handler)
        assert handler in publisher.handlers
    
    def test_publish_no_handlers(self, publisher):
        """Test publishing with no handlers"""
        result = publisher.publish(EventType.TOKEN_READY_FOR_DEPLOY, {"token_id": "XRAY"})
        assert result is False
    
    def test_publish_with_handler(self, publisher):
        """Test publishing with a handler"""
        handler = Mock()
        handler.can_handle.return_value = True
        handler.handle.return_value = True
        
        publisher.register_handler(handler)
        result = publisher.publish(EventType.TOKEN_READY_FOR_DEPLOY, {"token_id": "XRAY"})
        
        assert result is True
        handler.can_handle.assert_called_once()
        handler.handle.assert_called_once()
    
    def test_publish_multiple_handlers(self, publisher):
        """Test publishing with multiple handlers"""
        handler1 = Mock()
        handler1.can_handle.return_value = True
        handler1.handle.return_value = True
        
        handler2 = Mock()
        handler2.can_handle.return_value = False
        handler2.handle.return_value = True
        
        publisher.register_handler(handler1)
        publisher.register_handler(handler2)
        
        result = publisher.publish(EventType.MODEL_REGISTERED, {"token_id": "XRAY"})
        
        assert result is True
        handler1.handle.assert_called_once()
        handler2.handle.assert_not_called()  # Should not be called as can_handle is False
    
    def test_publish_token_ready(self, publisher):
        """Test convenience method for token ready event"""
        handler = Mock()
        handler.can_handle.return_value = True
        handler.handle.return_value = True
        
        publisher.register_handler(handler)
        result = publisher.publish_token_ready("XRAY", "run-123", {"extra": "data"})
        
        assert result is True
        # Verify the event was created with correct payload
        call_args = handler.handle.call_args
        event = call_args[0][0]
        assert event.payload["token_id"] == "XRAY"
        assert event.payload["mlflow_run_id"] == "run-123"
        assert event.payload["metadata"]["extra"] == "data"


class TestWebhookHandler:
    """Test the WebhookHandler class"""
    
    @patch('events.handlers.requests.post')
    def test_webhook_success(self, mock_post):
        """Test successful webhook delivery"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        handler = WebhookHandler("https://example.com/webhook")
        event = Event(EventType.TOKEN_READY_FOR_DEPLOY, {"token_id": "XRAY"})
        
        result = handler.handle(event)
        assert result is True
        mock_post.assert_called_once()
    
    @patch('events.handlers.requests.post')
    def test_webhook_failure(self, mock_post):
        """Test failed webhook delivery"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        handler = WebhookHandler("https://example.com/webhook")
        event = Event(EventType.TOKEN_READY_FOR_DEPLOY, {"token_id": "XRAY"})
        
        result = handler.handle(event)
        assert result is False
    
    def test_webhook_can_handle(self):
        """Test webhook event type filtering"""
        handler = WebhookHandler("https://example.com/webhook")
        
        assert handler.can_handle(EventType.TOKEN_READY_FOR_DEPLOY) is True
        assert handler.can_handle(EventType.MODEL_REGISTERED) is True
        assert handler.can_handle(EventType.DELTAONE_ACHIEVED) is False  # Not in default supported list


class TestConsoleHandler:
    """Test the ConsoleHandler class"""
    
    def test_console_handler(self, caplog):
        """Test console handler logging"""
        handler = ConsoleHandler()
        event = Event(EventType.MODEL_REGISTERED, {
            "token_id": "XRAY",
            "metric": "accuracy",
            "value": 0.85
        })
        
        result = handler.handle(event)
        assert result is True
        
        # Check that event was logged
        assert "Event: model_registered" in caplog.text
        assert "XRAY" in caplog.text
    
    def test_console_can_handle_all(self):
        """Test console handler accepts all events"""
        handler = ConsoleHandler()
        
        for event_type in EventType:
            assert handler.can_handle(event_type) is True


class TestDatabaseWatcherHandler:
    """Test the DatabaseWatcherHandler class"""
    
    def test_database_handler(self):
        """Test database watcher handler"""
        mock_db = Mock()
        mock_db.execute_update.return_value = 1
        
        handler = DatabaseWatcherHandler(mock_db)
        event = Event(EventType.TOKEN_READY_FOR_DEPLOY, {"token_id": "XRAY"})
        
        result = handler.handle(event)
        assert result is True
        mock_db.execute_update.assert_called_once()
    
    def test_database_handler_failure(self):
        """Test database handler with failure"""
        mock_db = Mock()
        mock_db.execute_update.side_effect = Exception("Database error")
        
        handler = DatabaseWatcherHandler(mock_db)
        event = Event(EventType.TOKEN_READY_FOR_DEPLOY, {"token_id": "XRAY"})
        
        result = handler.handle(event)
        assert result is False


class TestCompositeHandler:
    """Test the CompositeHandler class"""
    
    def test_composite_handler(self):
        """Test composite handler with multiple sub-handlers"""
        handler1 = Mock()
        handler1.can_handle.return_value = True
        handler1.handle.return_value = True
        
        handler2 = Mock()
        handler2.can_handle.return_value = True
        handler2.handle.return_value = False
        
        composite = CompositeHandler([handler1, handler2])
        event = Event(EventType.MODEL_REGISTERED, {"token_id": "XRAY"})
        
        # Should return True if at least one handler succeeds
        result = composite.handle(event)
        assert result is True
        
        handler1.handle.assert_called_once()
        handler2.handle.assert_called_once()