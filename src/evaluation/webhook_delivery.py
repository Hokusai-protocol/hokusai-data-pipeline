"""Delivery helpers for DeltaOne webhooks."""

from __future__ import annotations

import json
import logging
import random
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

import requests

from src.evaluation.webhook_config import WebhookEndpoint
from src.evaluation.webhook_security import generate_nonce, sign_payload

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebhookDeliveryResult:
    """Single endpoint delivery result."""

    endpoint_url: str
    event_type: str
    success: bool
    status_code: int | None
    attempts: int
    nonce: str


DELIVERY_LOG_MAX_SIZE = 512
_delivery_log: deque[WebhookDeliveryResult] = deque(maxlen=DELIVERY_LOG_MAX_SIZE)


def redact_webhook_url(webhook_url: str) -> str:
    """Redact webhook URL for logs by keeping only scheme and host."""
    parsed = urlparse(webhook_url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return "[invalid-webhook-url]"


def _compute_backoff_seconds(
    attempt_index: int,
    base_delay: float = 1.0,
    factor: float = 4.0,
    jitter_ratio: float = 0.25,
) -> float:
    delay = base_delay * (factor**attempt_index)
    jitter_multiplier = random.uniform(1.0 - jitter_ratio, 1.0 + jitter_ratio)
    return delay * jitter_multiplier


def get_recent_webhook_delivery_results() -> list[WebhookDeliveryResult]:
    """Return recent in-memory delivery results for debugging."""
    return list(_delivery_log)


def send_webhook_with_retry(
    endpoint: WebhookEndpoint,
    event_type: str,
    payload: dict[str, object],
    max_retries: int = 3,
    timeout: int = 10,
    base_delay: float = 1.0,
    backoff_factor: float = 4.0,
    jitter_ratio: float = 0.25,
    sleep: Callable[[float], None] = time.sleep,
) -> WebhookDeliveryResult:
    """Send signed webhook to one endpoint with exponential backoff and jitter."""
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    redacted_url = redact_webhook_url(endpoint.url)

    last_status_code: int | None = None
    last_nonce = ""

    for attempt in range(1, max_retries + 1):
        timestamp = str(int(time.time()))
        nonce = generate_nonce()
        last_nonce = nonce
        signature = sign_payload(payload_bytes, endpoint.secret, timestamp, nonce)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Hokusai-DeltaOne/1.0",
            "X-Hokusai-Signature": signature,
            "X-Hokusai-Timestamp": timestamp,
            "X-Hokusai-Nonce": nonce,
        }

        try:
            response = requests.post(
                endpoint.url,
                data=payload_bytes,
                headers=headers,
                timeout=timeout,
            )
            last_status_code = response.status_code
            if 200 <= response.status_code < 300:
                logger.info(
                    "DeltaOne webhook delivered",
                    extra={
                        "event_type": event_type,
                        "endpoint": redacted_url,
                        "status_code": response.status_code,
                        "attempt": attempt,
                        "nonce": nonce,
                    },
                )
                result = WebhookDeliveryResult(
                    endpoint_url=endpoint.url,
                    event_type=event_type,
                    success=True,
                    status_code=response.status_code,
                    attempts=attempt,
                    nonce=nonce,
                )
                _delivery_log.append(result)
                return result

            logger.warning(
                "DeltaOne webhook failed with non-success status",
                extra={
                    "event_type": event_type,
                    "endpoint": redacted_url,
                    "status_code": response.status_code,
                    "attempt": attempt,
                    "nonce": nonce,
                },
            )
        except requests.RequestException as exc:
            logger.warning(
                "DeltaOne webhook request exception",
                extra={
                    "event_type": event_type,
                    "endpoint": redacted_url,
                    "status_code": last_status_code,
                    "attempt": attempt,
                    "nonce": nonce,
                    "error": str(exc),
                },
            )

        if attempt < max_retries:
            backoff = _compute_backoff_seconds(
                attempt_index=attempt - 1,
                base_delay=base_delay,
                factor=backoff_factor,
                jitter_ratio=jitter_ratio,
            )
            sleep(backoff)

    result = WebhookDeliveryResult(
        endpoint_url=endpoint.url,
        event_type=event_type,
        success=False,
        status_code=last_status_code,
        attempts=max_retries,
        nonce=last_nonce,
    )
    _delivery_log.append(result)
    logger.error(
        "DeltaOne webhook delivery exhausted retries",
        extra={
            "event_type": event_type,
            "endpoint": redacted_url,
            "status_code": last_status_code,
            "attempts": max_retries,
            "nonce": last_nonce,
        },
    )
    return result
