"""
Fallback message publisher for when Redis is unavailable.

This publisher provides graceful degradation by:
1. Logging messages when Redis is down
2. Queuing messages locally for potential replay
3. Providing health status indicating fallback mode
"""

import json
import logging
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from .base import AbstractPublisher
except ImportError:
    # Fallback for when running tests
    from src.events.publishers.base import AbstractPublisher

logger = logging.getLogger(__name__)


class FallbackPublisher(AbstractPublisher):
    """
    Fallback publisher that operates when primary messaging system is unavailable.
    
    Features:
    - Logs all messages for debugging/audit purposes
    - Queues messages in memory for potential replay
    - Provides degraded health status
    - Thread-safe operations
    - Configurable queue limits to prevent memory issues
    """
    
    def __init__(
        self,
        max_queued_messages: int = 1000,
        queue_ttl_seconds: int = 3600,
        enable_message_logging: bool = True
    ):
        """
        Initialize fallback publisher.
        
        Args:
            max_queued_messages: Maximum messages to queue in memory
            queue_ttl_seconds: Time to keep messages in queue (for replay)
            enable_message_logging: Whether to log message contents
        """
        self.max_queued_messages = max_queued_messages
        self.queue_ttl_seconds = queue_ttl_seconds
        self.enable_message_logging = enable_message_logging
        
        # Thread-safe queue for storing messages
        self.queued_messages = deque(maxlen=max_queued_messages)
        self._lock = threading.RLock()
        
        # Statistics
        self.messages_published = 0
        self.messages_dropped = 0
        self.started_at = datetime.utcnow()
        
        logger.warning(
            f"Initialized FallbackPublisher: max_queued={max_queued_messages}, "
            f"ttl={queue_ttl_seconds}s, logging_enabled={enable_message_logging}"
        )
    
    def publish(self, message: Dict[str, Any], queue_name: str) -> bool:
        """
        Publish message to fallback system (log and queue).
        
        Args:
            message: Message to publish
            queue_name: Target queue name (used for logging only)
            
        Returns:
            Always True (fallback always "succeeds")
        """
        current_time = datetime.utcnow()
        
        # Create enhanced message envelope for queuing
        envelope = {
            "message_id": f"fallback-{int(time.time() * 1000000)}",
            "queue_name": queue_name,
            "payload": message,
            "timestamp": current_time,
            "queued_at": current_time,
            "source": "fallback_publisher"
        }
        
        with self._lock:
            # Add to queue (will auto-evict old messages if at capacity)
            was_full = len(self.queued_messages) >= self.max_queued_messages
            self.queued_messages.append(envelope)
            
            if was_full:
                self.messages_dropped += 1
                logger.warning(
                    f"Message queue full, dropped oldest message. "
                    f"Queue size: {len(self.queued_messages)}, "
                    f"Total dropped: {self.messages_dropped}"
                )
            
            self.messages_published += 1
        
        # Log message details if enabled
        if self.enable_message_logging:
            logger.info(
                f"FALLBACK: Published message to '{queue_name}' "
                f"(ID: {envelope['message_id']}, "
                f"Total queued: {len(self.queued_messages)})",
                extra={
                    "message_id": envelope["message_id"],
                    "queue_name": queue_name,
                    "message_type": message.get("message_type", "unknown"),
                    "fallback_mode": True
                }
            )
            
            # Log message payload at debug level
            logger.debug(f"Message payload: {json.dumps(message, default=str, indent=2)}")
        else:
            logger.info(
                f"FALLBACK: Published message to '{queue_name}' "
                f"(ID: {envelope['message_id']})"
            )
        
        return True
    
    def health_check(self) -> Dict[str, Any]:
        """
        Return health status indicating fallback mode.
        
        Returns:
            Health status with degraded state
        """
        current_time = datetime.utcnow()
        uptime = (current_time - self.started_at).total_seconds()
        
        with self._lock:
            queue_size = len(self.queued_messages)
            
            # Clean up expired messages
            self._cleanup_expired_messages()
            cleaned_queue_size = len(self.queued_messages)
        
        return {
            "status": "degraded",
            "message": "Using fallback publisher - primary messaging system unavailable",
            "mode": "fallback",
            "uptime_seconds": uptime,
            "statistics": {
                "messages_published": self.messages_published,
                "messages_dropped": self.messages_dropped,
                "current_queue_size": cleaned_queue_size,
                "max_queue_size": self.max_queued_messages,
                "messages_cleaned": queue_size - cleaned_queue_size
            },
            "configuration": {
                "max_queued_messages": self.max_queued_messages,
                "queue_ttl_seconds": self.queue_ttl_seconds,
                "message_logging_enabled": self.enable_message_logging
            }
        }
    
    def close(self) -> None:
        """
        Clean up fallback publisher resources.
        """
        with self._lock:
            queue_size = len(self.queued_messages)
            self.queued_messages.clear()
        
        logger.info(
            f"Closed FallbackPublisher: published={self.messages_published}, "
            f"dropped={self.messages_dropped}, queue_cleared={queue_size}"
        )
    
    def get_queue_depth(self, queue_name: str) -> Optional[int]:
        """
        Get number of messages for a specific queue.
        
        Args:
            queue_name: Name of the queue
            
        Returns:
            Number of messages for this queue (or None if unavailable)
        """
        with self._lock:
            # Count messages for specific queue
            count = sum(
                1 for msg in self.queued_messages 
                if msg.get("queue_name") == queue_name
            )
            return count
    
    def get_all_queued_messages(self) -> List[Dict[str, Any]]:
        """
        Get all queued messages (for debugging or replay).
        
        Returns:
            List of all queued message envelopes
        """
        with self._lock:
            return list(self.queued_messages)
    
    def get_messages_for_queue(self, queue_name: str) -> List[Dict[str, Any]]:
        """
        Get all queued messages for a specific queue.
        
        Args:
            queue_name: Name of the queue
            
        Returns:
            List of message envelopes for the specified queue
        """
        with self._lock:
            return [
                msg for msg in self.queued_messages 
                if msg.get("queue_name") == queue_name
            ]
    
    def replay_messages(self, target_publisher: AbstractPublisher) -> Dict[str, Any]:
        """
        Replay queued messages to a target publisher (when primary system recovers).
        
        Args:
            target_publisher: Publisher to replay messages to
            
        Returns:
            Replay statistics
        """
        if not target_publisher:
            raise ValueError("Target publisher is required for replay")
        
        replay_stats = {
            "total_messages": 0,
            "successful_replays": 0,
            "failed_replays": 0,
            "started_at": datetime.utcnow(),
            "completed_at": None,
            "errors": []
        }
        
        with self._lock:
            messages_to_replay = list(self.queued_messages)
            replay_stats["total_messages"] = len(messages_to_replay)
        
        logger.info(f"Starting message replay: {replay_stats['total_messages']} messages")
        
        for message_envelope in messages_to_replay:
            try:
                success = target_publisher.publish(
                    message_envelope["payload"],
                    message_envelope["queue_name"]
                )
                
                if success:
                    replay_stats["successful_replays"] += 1
                else:
                    replay_stats["failed_replays"] += 1
                    replay_stats["errors"].append(
                        f"Replay failed for message {message_envelope['message_id']}"
                    )
            
            except Exception as e:
                replay_stats["failed_replays"] += 1
                error_msg = f"Exception replaying message {message_envelope['message_id']}: {str(e)}"
                replay_stats["errors"].append(error_msg)
                logger.error(error_msg)
        
        replay_stats["completed_at"] = datetime.utcnow()
        
        # Clear successfully replayed messages
        if replay_stats["successful_replays"] > 0:
            with self._lock:
                # Remove replayed messages (keep failed ones for potential retry)
                failed_message_ids = set()
                for error in replay_stats["errors"]:
                    if "message" in error:
                        # Extract message ID from error (simplified)
                        pass
                
                # For simplicity, clear all messages on partial success
                # In production, you might want more sophisticated tracking
                if replay_stats["failed_replays"] == 0:
                    self.queued_messages.clear()
                    logger.info("Cleared all replayed messages from fallback queue")
        
        logger.info(
            f"Message replay completed: {replay_stats['successful_replays']} successful, "
            f"{replay_stats['failed_replays']} failed"
        )
        
        return replay_stats
    
    def _cleanup_expired_messages(self):
        """Remove expired messages from the queue."""
        if not self.queue_ttl_seconds:
            return  # No TTL configured
        
        current_time = datetime.utcnow()
        cutoff_time = current_time.timestamp() - self.queue_ttl_seconds
        
        # Filter out expired messages
        original_length = len(self.queued_messages)
        self.queued_messages = deque(
            (msg for msg in self.queued_messages 
             if msg["queued_at"].timestamp() > cutoff_time),
            maxlen=self.max_queued_messages
        )
        
        cleaned_count = original_length - len(self.queued_messages)
        if cleaned_count > 0:
            logger.debug(f"Cleaned up {cleaned_count} expired messages from fallback queue")
    
    def clear_queue(self) -> int:
        """
        Clear all queued messages manually.
        
        Returns:
            Number of messages that were cleared
        """
        with self._lock:
            count = len(self.queued_messages)
            self.queued_messages.clear()
            
        logger.info(f"Manually cleared {count} messages from fallback queue")
        return count
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get detailed publisher statistics.
        
        Returns:
            Detailed statistics dictionary
        """
        current_time = datetime.utcnow()
        uptime = (current_time - self.started_at).total_seconds()
        
        with self._lock:
            queue_size = len(self.queued_messages)
            
            # Calculate queue age statistics
            if self.queued_messages:
                oldest_message_age = (
                    current_time - self.queued_messages[0]["queued_at"]
                ).total_seconds()
                newest_message_age = (
                    current_time - self.queued_messages[-1]["queued_at"]
                ).total_seconds()
            else:
                oldest_message_age = 0
                newest_message_age = 0
        
        return {
            "uptime_seconds": uptime,
            "messages_published": self.messages_published,
            "messages_dropped": self.messages_dropped,
            "current_queue_size": queue_size,
            "max_queue_size": self.max_queued_messages,
            "queue_utilization_percent": (queue_size / self.max_queued_messages) * 100,
            "oldest_message_age_seconds": oldest_message_age,
            "newest_message_age_seconds": newest_message_age,
            "publish_rate_per_second": self.messages_published / max(uptime, 1),
            "configuration": {
                "max_queued_messages": self.max_queued_messages,
                "queue_ttl_seconds": self.queue_ttl_seconds,
                "message_logging_enabled": self.enable_message_logging
            }
        }