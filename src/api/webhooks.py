"""
Webhook notification module.
"""

import requests
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def send_webhook_notification(
    webhook_url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str]
) -> None:
    """
    Send a webhook notification.
    
    Args:
        webhook_url: URL to send webhook to
        payload: Webhook payload
        headers: Request headers (including auth)
    """
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers=headers,  # Auth headers included!
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"Webhook sent successfully to {webhook_url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send webhook: {e}")