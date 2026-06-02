"""Middleware to reject common scanner/noise paths early."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from src.api.utils.config import get_settings

logger = logging.getLogger(__name__)

SCANNER_EXACT_PATHS = frozenset(
    {
        "/.env",
        "/api/jsonws",
        "/boaform/admin/formlogin",
        "/login.action",
        "/manager/html",
        "/server-status",
        "/ui/login",
    }
)

SCANNER_PATH_PREFIXES = (
    "/.git/",
    "/.aws/",
    "/actuator/",
    "/api/jsonws/",
    "/autodiscover/",
    "/cgi-bin/",
    "/console/",
    "/geoserver/",
    "/hudson/",
    "/jenkins/",
    "/mgmt/",
    "/nifi/",
    "/owa/",
    "/phpmyadmin/",
    "/solr/",
    "/wp-admin/",
)

ALLOWLIST_PREFIXES = (
    "/health",
    "/ready",
    "/live",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/",
    "/api/2.0/mlflow/",
    "/api/2.0/preview/mlflow/",
    "/api/mlflow/",
    "/mlflow/",
    "/api/models",
    "/models",
    "/api/health",
)


class ScannerFilterMiddleware(BaseHTTPMiddleware):
    """Reject known scanner paths before they hit the application."""

    def __init__(self: ScannerFilterMiddleware, app: ASGIApp) -> None:
        super().__init__(app)
        settings = get_settings()
        self.enabled = settings.scanner_filter_enabled
        self.extra_exact_paths = tuple(
            pattern.strip().lower()
            for pattern in settings.scanner_filter_extra_patterns.split(",")
            if pattern.strip()
        )

    async def dispatch(
        self: ScannerFilterMiddleware,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not self.enabled:
            return await call_next(request)

        path = request.url.path.lower()

        if path.startswith(ALLOWLIST_PREFIXES):
            return await call_next(request)

        if path in SCANNER_EXACT_PATHS or path in self.extra_exact_paths:
            self._log_rejection(request, path)
            return Response(status_code=404, content=b"", headers={"Cache-Control": "no-store"})

        if path.startswith(SCANNER_PATH_PREFIXES):
            self._log_rejection(request, path)
            return Response(status_code=404, content=b"", headers={"Cache-Control": "no-store"})

        return await call_next(request)

    @staticmethod
    def _client_ip(request: Request) -> str | None:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            first_hop = forwarded_for.split(",", 1)[0].strip()
            if first_hop:
                return first_hop
        if request.client:
            return request.client.host
        return None

    def _log_rejection(self: ScannerFilterMiddleware, request: Request, path: str) -> None:
        user_agent = (request.headers.get("user-agent") or "")[:200] or None
        logger.info(
            "scanner_request_rejected",
            extra={
                "event_type": "scanner_request_rejected",
                "path": path,
                "method": request.method,
                "client_ip": self._client_ip(request),
                "user_agent": user_agent,
            },
        )
