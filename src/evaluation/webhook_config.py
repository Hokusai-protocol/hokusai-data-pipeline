"""Configuration loader for DeltaOne webhook endpoints."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DELTAONE_EVENT_TYPE = "deltaone.achieved"
DELTAONE_MINTED_EVENT_TYPE = "deltaone.minted"


@dataclass(frozen=True)
class WebhookEndpoint:
    """Webhook endpoint configuration."""

    url: str
    secret: str
    event_types: tuple[str, ...]
    active: bool = True
    description: str = ""


def _parse_endpoints_from_env(raw_value: str) -> list[WebhookEndpoint]:
    parsed = json.loads(raw_value)
    if not isinstance(parsed, list):
        raise ValueError("DELTAONE_WEBHOOK_ENDPOINTS must be a JSON array")

    endpoints: list[WebhookEndpoint] = []
    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            logger.warning("Skipping webhook endpoint index %s: expected object", index)
            continue

        url = str(item.get("url", "")).strip()
        if not url:
            logger.warning("Skipping webhook endpoint index %s: missing url", index)
            continue

        secret = str(item.get("secret", ""))
        event_types_raw = item.get("event_types", [DELTAONE_EVENT_TYPE])
        if isinstance(event_types_raw, list):
            event_types = tuple(str(evt) for evt in event_types_raw)
        else:
            event_types = (DELTAONE_EVENT_TYPE,)

        active = bool(item.get("active", True))
        description = str(item.get("description", ""))

        endpoints.append(
            WebhookEndpoint(
                url=url,
                secret=secret,
                event_types=event_types,
                active=active,
                description=description,
            )
        )

    return endpoints


def load_deltaone_webhook_endpoints(
    event_type: str = DELTAONE_EVENT_TYPE,
    legacy_webhook_url: str | None = None,
    legacy_secret: str | None = None,
) -> list[WebhookEndpoint]:
    """Load active webhook endpoints configured for the DeltaOne event type."""
    configured = os.getenv("DELTAONE_WEBHOOK_ENDPOINTS")
    endpoints: list[WebhookEndpoint] = []

    if configured:
        try:
            endpoints = _parse_endpoints_from_env(configured)
        except json.JSONDecodeError as exc:
            logger.error("Invalid DELTAONE_WEBHOOK_ENDPOINTS JSON: %s", exc)

    if not endpoints:
        fallback_url = legacy_webhook_url or os.getenv("WEBHOOK_URL")
        if fallback_url:
            endpoints = [
                WebhookEndpoint(
                    url=fallback_url,
                    secret=(
                        legacy_secret
                        if legacy_secret is not None
                        else os.getenv("WEBHOOK_SECRET", "")
                    ),
                    event_types=(event_type,),
                    active=True,
                    description="legacy_single_endpoint",
                )
            ]

    return [
        endpoint for endpoint in endpoints if endpoint.active and event_type in endpoint.event_types
    ]
