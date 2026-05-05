"""Publisher for MintRequest messages to the hokusai:mint_requests Redis queue."""

from __future__ import annotations

import logging
import os

import redis
from redis.exceptions import RedisError

from src.events.schemas import MintRequest

logger = logging.getLogger(__name__)

QUEUE_NAME = "hokusai:mint_requests"


class MintRequestPublisher:
    """Publishes validated MintRequest messages to the hokusai:mint_requests Redis queue.

    Each message is serialized as raw JSON (no envelope) via LPUSH so consumers
    RPOP from the right in FIFO order.

    Redis failures are re-raised after logging so the caller can decide whether
    to abort the mint path. No retries or DLQ are implemented here — the
    downstream consumer owns that concern.
    """

    def __init__(
        self: MintRequestPublisher,
        redis_client: redis.Redis | None = None,
        redis_url: str | None = None,
    ) -> None:
        if redis_client is not None:
            self._client = redis_client
        else:
            url = redis_url or self._resolve_redis_url()
            self._client = redis.from_url(url, decode_responses=True)

    @staticmethod
    def _resolve_redis_url() -> str:
        """Resolve Redis URL from environment without triggering full settings validation."""
        url = os.getenv("REDIS_URL")
        if url:
            tls_enabled = os.getenv("REDIS_TLS_ENABLED", "false").lower() == "true"
            if not url.startswith(("redis://", "rediss://", "unix://")):
                scheme = "rediss" if tls_enabled else "redis"
                auth_token = os.getenv("REDIS_AUTH_TOKEN")
                port = os.getenv("REDIS_PORT", "6379")
                if auth_token:
                    url = f"{scheme}://:{auth_token}@{url}:{port}/0"
                else:
                    url = f"{scheme}://{url}:{port}"
            return url

        host = os.getenv("REDIS_HOST")
        if not host:
            raise RuntimeError(
                "MintRequestPublisher: Redis configuration missing. "
                "Set REDIS_URL or REDIS_HOST environment variable."
            )
        port = os.getenv("REDIS_PORT", "6379")
        auth_token = os.getenv("REDIS_AUTH_TOKEN")
        tls_enabled = os.getenv("REDIS_TLS_ENABLED", "false").lower() == "true"
        scheme = "rediss" if tls_enabled else "redis"
        if auth_token:
            return f"{scheme}://:{auth_token}@{host}:{port}/0"
        return f"{scheme}://{host}:{port}/0"

    def publish(self: MintRequestPublisher, message: MintRequest) -> None:
        """Serialize and publish a MintRequest to hokusai:mint_requests via LPUSH.

        Redis errors propagate to the caller — a failed publish must prevent
        canonical baseline advancement (HOK-1276 recovery contract).
        """
        payload = message.model_dump_json()
        try:
            self._client.lpush(QUEUE_NAME, payload)
        except RedisError:
            logger.error(
                "event=mint_request_publish_failed model_id=%s eval_id=%s idempotency_key=%s",
                message.model_id,
                message.eval_id,
                message.idempotency_key,
            )
            raise
        logger.info(
            "event=mint_request_published queue=%s model_id=%s eval_id=%s idempotency_key=%s",
            QUEUE_NAME,
            message.model_id,
            message.eval_id,
            message.idempotency_key,
        )

    def get_queue_depth(self: MintRequestPublisher) -> int:
        """Return the current number of messages in hokusai:mint_requests."""
        return self._client.llen(QUEUE_NAME)

    def close(self: MintRequestPublisher) -> None:
        """Close the underlying Redis connection."""
        try:
            self._client.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("event=mint_request_publisher_close_error error=%s", exc)
