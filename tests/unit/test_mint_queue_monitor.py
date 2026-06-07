"""Unit tests for mint queue CloudWatch emission."""

from __future__ import annotations

from unittest.mock import Mock

import fakeredis
from redis.exceptions import RedisError

from src.events.publishers.mint_request_publisher import QUEUE_NAME
from src.monitoring.mint_queue_monitor import DLQ_QUEUE_NAME, MintQueueDepthEmitter


def test_emit_once_emits_correct_depth() -> None:
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    redis_client.lpush(QUEUE_NAME, "msg-1")
    redis_client.lpush(QUEUE_NAME, "msg-2")
    redis_client.lpush(DLQ_QUEUE_NAME, "dead-letter")
    cloudwatch_client = Mock()
    emitter = MintQueueDepthEmitter(
        redis_client=redis_client,
        cloudwatch_client=cloudwatch_client,
    )

    result = emitter.emit_once()

    assert result == {"MintRequestsQueueDepth": 2, "MintRequestsDLQDepth": 1}
    cloudwatch_client.put_metric_data.assert_called_once()


def test_emit_once_redis_error_does_not_raise() -> None:
    redis_client = Mock()
    redis_client.llen.side_effect = RedisError("boom")
    cloudwatch_client = Mock()
    emitter = MintQueueDepthEmitter(
        redis_client=redis_client,
        cloudwatch_client=cloudwatch_client,
    )

    result = emitter.emit_once()

    assert result == {}
    cloudwatch_client.put_metric_data.assert_not_called()
