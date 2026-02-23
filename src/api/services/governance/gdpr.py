"""GDPR helper service for export, deletion, and consent lifecycle."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable


@dataclass
class ConsentRecordData:
    """In-memory consent record."""

    user_id: str
    consent_type: str
    granted: bool
    granted_at: str
    revoked_at: str | None
    metadata: dict[str, Any]


@dataclass
class DeletionReport:
    """Structured report for user-data deletion operations."""

    user_id: str
    deleted: dict[str, int]
    anonymized: dict[str, int]


class GDPRService:
    """Collects and deletes user-linked data via registered provider callbacks."""

    def __init__(self) -> None:
        self._consents: list[ConsentRecordData] = []
        self._exporters: dict[str, Callable[[str], Any]] = {}
        self._deleters: dict[str, Callable[[str], int]] = {}
        self._lock = Lock()

    def register_exporter(self, name: str, exporter: Callable[[str], Any]) -> None:
        """Register a named exporter callback for GDPR exports."""
        self._exporters[name] = exporter

    def register_deleter(self, name: str, deleter: Callable[[str], int]) -> None:
        """Register a named deletion callback for GDPR deletes."""
        self._deleters[name] = deleter

    def export_user_data(self, user_id: str) -> dict[str, Any]:
        """Collect all data associated with a user from registered providers."""
        payload = {"user_id": user_id, "exports": {}}
        for name, exporter in self._exporters.items():
            payload["exports"][name] = exporter(user_id)
        payload["exports"]["consent_records"] = self.get_consent_history(user_id)
        return payload

    def delete_user_data(self, user_id: str) -> DeletionReport:
        """Delete or anonymize all user data via registered callbacks."""
        deleted: dict[str, int] = {}
        for name, deleter in self._deleters.items():
            deleted[name] = int(deleter(user_id))

        anonymized = {"consent_records": self._delete_consents(user_id)}
        return DeletionReport(user_id=user_id, deleted=deleted, anonymized=anonymized)

    def record_consent(
        self,
        user_id: str,
        consent_type: str,
        granted: bool,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new consent state transition record."""
        now = datetime.now(timezone.utc).isoformat()
        record = ConsentRecordData(
            user_id=user_id,
            consent_type=consent_type,
            granted=granted,
            granted_at=now,
            revoked_at=None if granted else now,
            metadata=metadata or {},
        )
        with self._lock:
            self._consents.append(record)
        return asdict(record)

    def check_consent(self, user_id: str, consent_type: str) -> bool:
        """Check latest active consent for a user/consent type."""
        history = self.get_consent_history(user_id)
        matching = [item for item in history if item["consent_type"] == consent_type]
        if not matching:
            return False
        latest = matching[-1]
        return bool(latest["granted"] and latest["revoked_at"] is None)

    def get_consent_history(self, user_id: str) -> list[dict[str, Any]]:
        """Get consent history records for a user."""
        with self._lock:
            items = [item for item in self._consents if item.user_id == user_id]
        return [asdict(item) for item in items]

    def _delete_consents(self, user_id: str) -> int:
        with self._lock:
            before = len(self._consents)
            self._consents = [item for item in self._consents if item.user_id != user_id]
            after = len(self._consents)
        return before - after
