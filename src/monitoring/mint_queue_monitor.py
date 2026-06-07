"""Background CloudWatch metric emission for the mint request queues."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import boto3
import redis

from src.events.publishers.mint_request_publisher import QUEUE_NAME

logger = logging.getLogger(__name__)

DLQ_QUEUE_NAME = f"{QUEUE_NAME}:dlq"


@dataclass(slots=True)
class MintQueueDepthEmitter:
    """Emit queue depth metrics for the mint request queue and DLQ."""

    redis_client: redis.Redis
    cloudwatch_client: Any | None = None
    namespace: str = "Hokusai/MintQueue"
    region: str = "us-east-1"

    def __post_init__(self: MintQueueDepthEmitter) -> None:
        if self.cloudwatch_client is None:
            self.cloudwatch_client = boto3.client("cloudwatch", region_name=self.region)

    @classmethod
    def from_env(cls: type[MintQueueDepthEmitter]) -> MintQueueDepthEmitter:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            redis_client = redis.from_url(redis_url, decode_responses=True)
        else:
            host = os.getenv("REDIS_HOST")
            if not host:
                raise RuntimeError("MintQueueDepthEmitter requires REDIS_URL or REDIS_HOST")
            port = os.getenv("REDIS_PORT", "6379")
            auth_token = os.getenv("REDIS_AUTH_TOKEN")
            tls_enabled = os.getenv("REDIS_TLS_ENABLED", "false").lower() == "true"
            scheme = "rediss" if tls_enabled else "redis"
            if auth_token:
                redis_url = f"{scheme}://:{auth_token}@{host}:{port}/0"
            else:
                redis_url = f"{scheme}://{host}:{port}/0"
            redis_client = redis.from_url(redis_url, decode_responses=True)
        return cls(
            redis_client=redis_client,
            namespace=os.getenv("MINT_QUEUE_CLOUDWATCH_NAMESPACE", "Hokusai/MintQueue"),
            region=os.getenv("AWS_REGION", "us-east-1"),
        )

    def emit_once(self: MintQueueDepthEmitter) -> dict[str, int]:
        """Read queue depths and emit a single CloudWatch datapoint batch."""
        try:
            queue_depth = int(self.redis_client.llen(QUEUE_NAME))
            dlq_depth = int(self.redis_client.llen(DLQ_QUEUE_NAME))
        except redis.RedisError as exc:
            logger.warning("event=mint_queue_depth_read_failed error=%s", exc)
            return {}

        metrics = {
            "MintRequestsQueueDepth": queue_depth,
            "MintRequestsDLQDepth": dlq_depth,
        }
        self.cloudwatch_client.put_metric_data(
            Namespace=self.namespace,
            MetricData=[
                {"MetricName": name, "Value": value, "Unit": "Count"}
                for name, value in metrics.items()
            ],
        )
        logger.info(
            "event=mint_queue_metrics_emitted queue_depth=%s dlq_depth=%s namespace=%s",
            queue_depth,
            dlq_depth,
            self.namespace,
        )
        return metrics

    def close(self: MintQueueDepthEmitter) -> None:
        """Close the underlying Redis connection."""
        try:
            self.redis_client.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("event=mint_queue_monitor_close_failed error=%s", exc)
