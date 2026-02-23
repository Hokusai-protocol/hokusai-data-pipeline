"""Retention policy manager for governance-controlled resource cleanup."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Callable


@dataclass
class RetentionPolicyRecord:
    """Retention policy definition for a resource type."""

    resource_type: str
    retention_days: int
    delete_action: str
    enabled: bool
    created_at: str
    updated_at: str


class RetentionManager:
    """Applies configurable retention policies via injectable delete handlers."""

    def __init__(self) -> None:
        self._policies: dict[str, RetentionPolicyRecord] = {}
        self._handlers: dict[str, Callable[[datetime, str], int]] = {}
        self._lock = Lock()

    def register_handler(self, resource_type: str, handler: Callable[[datetime, str], int]) -> None:
        """Register resource-specific cleanup callback.

        Handler receives cutoff timestamp and delete_action, returns affected count.
        """
        self._handlers[resource_type] = handler

    def get_policy(self, resource_type: str) -> dict[str, Any] | None:
        """Get policy for a resource type."""
        with self._lock:
            policy = self._policies.get(resource_type)
        return asdict(policy) if policy else None

    def list_policies(self) -> list[dict[str, Any]]:
        """List all retention policies."""
        with self._lock:
            rows = list(self._policies.values())
        return [asdict(item) for item in rows]

    def set_policy(
        self, resource_type: str, retention_days: int, delete_action: str
    ) -> dict[str, Any]:
        """Create or update policy by resource type."""
        if delete_action not in {"hard_delete", "soft_delete", "archive"}:
            raise ValueError("delete_action must be one of hard_delete, soft_delete, archive")
        if retention_days <= 0:
            raise ValueError("retention_days must be > 0")

        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            existing = self._policies.get(resource_type)
            created_at = existing.created_at if existing else now
            policy = RetentionPolicyRecord(
                resource_type=resource_type,
                retention_days=retention_days,
                delete_action=delete_action,
                enabled=True,
                created_at=created_at,
                updated_at=now,
            )
            self._policies[resource_type] = policy
        return asdict(policy)

    def apply_policies(self) -> dict[str, int]:
        """Apply all enabled policies and return count of affected resources by type."""
        with self._lock:
            policies = list(self._policies.values())

        result: dict[str, int] = {}
        for policy in policies:
            if not policy.enabled:
                continue
            cutoff = datetime.now(timezone.utc) - timedelta(days=policy.retention_days)
            handler = self._handlers.get(policy.resource_type)
            if handler is None:
                result[policy.resource_type] = 0
                continue
            result[policy.resource_type] = int(handler(cutoff, policy.delete_action))
        return result
