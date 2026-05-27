"""Canonical MLflow URL resolution."""

from __future__ import annotations

import logging
import os
from urllib.parse import ParseResult, urlparse

logger = logging.getLogger(__name__)

_WARNED_HTTP_URLS: set[str] = set()


def _get_env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _describe_url(parsed_url: ParseResult) -> str:
    host = parsed_url.hostname or "<unknown-host>"
    if parsed_url.port is not None:
        return f"{parsed_url.scheme}://{host}:{parsed_url.port}"
    return f"{parsed_url.scheme}://{host}"


def get_mlflow_url() -> str:
    """Return the canonical MLflow URL from environment configuration."""
    tracking_uri = _get_env_value("MLFLOW_TRACKING_URI")
    server_url = _get_env_value("MLFLOW_SERVER_URL")
    mlflow_url = tracking_uri or server_url

    if mlflow_url is None:
        raise RuntimeError(
            "MLflow URL is not configured; set MLFLOW_TRACKING_URI or MLFLOW_SERVER_URL."
        )

    parsed_url = urlparse(mlflow_url)
    if not parsed_url.scheme or not parsed_url.netloc:
        raise ValueError(f"Invalid MLflow URL: {mlflow_url!r}")

    if parsed_url.scheme == "https":
        return mlflow_url

    if parsed_url.scheme == "http":
        if mlflow_url not in _WARNED_HTTP_URLS:
            logger.warning(
                "MLflow URL uses insecure HTTP: %s. Configure HTTPS for deployed environments.",
                _describe_url(parsed_url),
            )
            _WARNED_HTTP_URLS.add(mlflow_url)
        return mlflow_url

    raise ValueError(
        f"Unsupported MLflow URL scheme {parsed_url.scheme!r}; expected http or https."
    )


def reset_mlflow_url_warning_cache() -> None:
    """Clear cached HTTP warnings for tests."""
    _WARNED_HTTP_URLS.clear()
