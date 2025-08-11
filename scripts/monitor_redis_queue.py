#!/usr/bin/env python3
"""Monitor Redis queue health and send metrics to CloudWatch.

This script should be run periodically (e.g., via cron or ECS scheduled task)
to monitor queue health and send metrics to CloudWatch for alerting.
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any

import boto3
import redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RedisQueueMonitor:
    """Monitor Redis queue health and publish CloudWatch metrics."""
    
    def __init__(self):
        """Initialize monitor with Redis and CloudWatch clients."""
        # Redis configuration
        redis_host = os.getenv("REDIS_HOST", "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_auth_token = os.getenv("REDIS_AUTH_TOKEN")
        
        if redis_auth_token:
            redis_url = f"redis://:{redis_auth_token}@{redis_host}:{redis_port}/0"
        else:
            redis_url = f"redis://{redis_host}:{redis_port}/0"
        
        self.redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        
        # CloudWatch configuration
        self.cloudwatch = boto3.client('cloudwatch', region_name=os.getenv("AWS_REGION", "us-east-1"))
        self.namespace = "Hokusai/Redis"
        self.environment = os.getenv("ENVIRONMENT", "development")
        
        # Queue names
        self.main_queue = "hokusai:model_ready_queue"
        self.processing_queue = f"{self.main_queue}:processing"
        self.dlq = f"{self.main_queue}:dlq"
        
        # Thresholds for alerting
        self.queue_depth_threshold = int(os.getenv("QUEUE_DEPTH_THRESHOLD", "1000"))
        self.dlq_threshold = int(os.getenv("DLQ_THRESHOLD", "10"))
        self.processing_lag_threshold = int(os.getenv("PROCESSING_LAG_THRESHOLD", "100"))
    
    def check_redis_health(self) -> Dict[str, Any]:
        """Check Redis connectivity and basic health."""
        try:
            start_time = datetime.utcnow()
            self.redis_client.ping()
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            info = self.redis_client.info()
            
            return {
                "healthy": True,
                "latency_ms": round(latency_ms, 2),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_mb": info.get("used_memory", 0) / (1024 * 1024),
                "ops_per_sec": info.get("instantaneous_ops_per_sec", 0)
            }
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {
                "healthy": False,
                "error": str(e)
            }
    
    def get_queue_metrics(self) -> Dict[str, int]:
        """Get queue depth metrics."""
        try:
            return {
                "main_queue_depth": self.redis_client.llen(self.main_queue),
                "processing_queue_depth": self.redis_client.llen(self.processing_queue),
                "dlq_depth": self.redis_client.llen(self.dlq)
            }
        except Exception as e:
            logger.error(f"Failed to get queue metrics: {e}")
            return {
                "main_queue_depth": -1,
                "processing_queue_depth": -1,
                "dlq_depth": -1
            }
    
    def analyze_message_age(self) -> Dict[str, Any]:
        """Analyze age of oldest messages in queues."""
        results = {}
        
        for queue_name in [self.main_queue, self.processing_queue]:
            try:
                # Get oldest message without removing it
                oldest = self.redis_client.lindex(queue_name, -1)
                if oldest:
                    envelope = json.loads(oldest)
                    timestamp = envelope.get("timestamp")
                    if timestamp:
                        message_age = (datetime.utcnow() - datetime.fromisoformat(timestamp)).total_seconds()
                        results[f"{queue_name}_oldest_message_age_seconds"] = message_age
                    else:
                        results[f"{queue_name}_oldest_message_age_seconds"] = 0
                else:
                    results[f"{queue_name}_oldest_message_age_seconds"] = 0
            except Exception as e:
                logger.error(f"Failed to analyze message age for {queue_name}: {e}")
                results[f"{queue_name}_oldest_message_age_seconds"] = -1
        
        return results
    
    def send_cloudwatch_metrics(self, metrics: Dict[str, Any]):
        """Send metrics to CloudWatch."""
        try:
            metric_data = []
            timestamp = datetime.utcnow()
            
            for metric_name, value in metrics.items():
                if isinstance(value, (int, float)) and value >= 0:
                    metric_data.append({
                        'MetricName': metric_name,
                        'Value': value,
                        'Unit': self._get_unit(metric_name),
                        'Timestamp': timestamp,
                        'Dimensions': [
                            {'Name': 'Environment', 'Value': self.environment},
                            {'Name': 'Queue', 'Value': self.main_queue}
                        ]
                    })
            
            if metric_data:
                self.cloudwatch.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=metric_data
                )
                logger.info(f"Sent {len(metric_data)} metrics to CloudWatch")
        except Exception as e:
            logger.error(f"Failed to send CloudWatch metrics: {e}")
    
    def _get_unit(self, metric_name: str) -> str:
        """Get CloudWatch unit for metric."""
        if "depth" in metric_name or "count" in metric_name:
            return "Count"
        elif "latency" in metric_name or "age" in metric_name:
            return "Milliseconds" if "latency" in metric_name else "Seconds"
        elif "memory" in metric_name:
            return "Megabytes"
        elif "per_sec" in metric_name:
            return "Count/Second"
        else:
            return "None"
    
    def check_thresholds(self, metrics: Dict[str, Any]) -> Dict[str, bool]:
        """Check if any metrics exceed thresholds."""
        alerts = {}
        
        # Check queue depth
        if metrics.get("main_queue_depth", 0) > self.queue_depth_threshold:
            alerts["high_queue_depth"] = True
            logger.warning(f"Main queue depth ({metrics['main_queue_depth']}) exceeds threshold ({self.queue_depth_threshold})")
        
        # Check DLQ
        if metrics.get("dlq_depth", 0) > self.dlq_threshold:
            alerts["dlq_has_messages"] = True
            logger.warning(f"Dead letter queue has {metrics['dlq_depth']} messages")
        
        # Check processing lag
        processing_depth = metrics.get("processing_queue_depth", 0)
        if processing_depth > self.processing_lag_threshold:
            alerts["processing_lag"] = True
            logger.warning(f"Processing queue depth ({processing_depth}) indicates processing lag")
        
        # Check message age
        oldest_age = metrics.get(f"{self.main_queue}_oldest_message_age_seconds", 0)
        if oldest_age > 3600:  # 1 hour
            alerts["old_messages"] = True
            logger.warning(f"Oldest message is {oldest_age/3600:.1f} hours old")
        
        return alerts
    
    def run(self):
        """Run monitoring cycle."""
        logger.info("Starting Redis queue monitoring cycle")
        
        # Check Redis health
        health = self.check_redis_health()
        if not health.get("healthy"):
            logger.error("Redis is unhealthy, skipping metrics collection")
            self.send_cloudwatch_metrics({"redis_healthy": 0})
            return
        
        # Collect all metrics
        metrics = {
            "redis_healthy": 1,
            "redis_latency_ms": health.get("latency_ms", 0),
            "redis_connected_clients": health.get("connected_clients", 0),
            "redis_used_memory_mb": health.get("used_memory_mb", 0),
            "redis_ops_per_sec": health.get("ops_per_sec", 0)
        }
        
        # Get queue metrics
        queue_metrics = self.get_queue_metrics()
        metrics.update(queue_metrics)
        
        # Analyze message age
        age_metrics = self.analyze_message_age()
        metrics.update(age_metrics)
        
        # Log summary
        logger.info(f"Queue metrics: Main={queue_metrics['main_queue_depth']}, "
                   f"Processing={queue_metrics['processing_queue_depth']}, "
                   f"DLQ={queue_metrics['dlq_depth']}")
        
        # Check thresholds
        alerts = self.check_thresholds(metrics)
        if alerts:
            logger.warning(f"Threshold alerts: {alerts}")
            metrics["alerts_active"] = len(alerts)
        else:
            metrics["alerts_active"] = 0
        
        # Send to CloudWatch
        self.send_cloudwatch_metrics(metrics)
        
        logger.info("Monitoring cycle complete")


def main():
    """Main entry point."""
    try:
        monitor = RedisQueueMonitor()
        monitor.run()
    except Exception as e:
        logger.error(f"Monitor failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()