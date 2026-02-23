"""Structured audit logging utilities for governance controls."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import wraps
from threading import Lock
from typing import Any, Callable
from uuid import uuid4


@dataclass
class AuditEntry:
    """Single audit event record."""

    id: str
    timestamp: datetime
    user_id: str
    action: str
    resource_type: str
    resource_id: str
    details: dict[str, Any]
    ip_address: str | None
    outcome: str


class AuditLogger:
    """Async-safe logger that stores audit events and supports filtering."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=2)

    def log(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        user_id: str,
        details: dict[str, Any] | None = None,
        outcome: str = "success",
        ip_address: str | None = None,
    ) -> None:
        """Write an audit log entry in background to avoid request blocking."""
        payload = AuditEntry(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
            outcome=outcome,
        )
        self._executor.submit(self._append_entry, payload)

    def get_logs(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Return audit entries filtered by user, action, resource type, and date range."""
        filters = filters or {}
        user_id = filters.get("user_id")
        action = filters.get("action")
        resource_type = filters.get("resource_type")
        start = filters.get("start")
        end = filters.get("end")

        with self._lock:
            rows = list(self._entries)

        results: list[dict[str, Any]] = []
        for item in rows:
            if user_id and item.user_id != user_id:
                continue
            if action and item.action != action:
                continue
            if resource_type and item.resource_type != resource_type:
                continue
            if start and item.timestamp < start:
                continue
            if end and item.timestamp > end:
                continue
            encoded = asdict(item)
            encoded["timestamp"] = item.timestamp.isoformat()
            results.append(encoded)
        return results

    def _append_entry(self, entry: AuditEntry) -> None:
        with self._lock:
            self._entries.append(entry)


def audit_logged(
    action: str, resource_type: str, get_resource_id: Callable[..., str] | None = None
):
    """Decorator that automatically logs success/error outcomes for route handlers."""

    def decorator(func):
        if not callable(func):
            return func

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger: AuditLogger | None = kwargs.get("audit_logger")
            user = kwargs.get("_auth") or kwargs.get("auth") or {}
            user_id = user.get("user_id", "unknown") if isinstance(user, dict) else "unknown"
            resource_id = "unknown"
            if get_resource_id:
                try:
                    resource_id = get_resource_id(*args, **kwargs)
                except Exception:
                    resource_id = "unknown"
            try:
                result = await func(*args, **kwargs)
                if logger:
                    logger.log(
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        user_id=user_id,
                        outcome="success",
                    )
                return result
            except Exception:
                if logger:
                    logger.log(
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        user_id=user_id,
                        outcome="error",
                    )
                raise

        return async_wrapper

    return decorator
