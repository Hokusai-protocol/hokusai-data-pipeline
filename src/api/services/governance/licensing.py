"""Dataset license registration and validation service."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any


@dataclass
class LicenseValidationResult:
    """Result of evaluating intended dataset usage against a license."""

    allowed: bool
    reason: str
    required_actions: list[str]


@dataclass
class DatasetLicenseRecord:
    """License metadata for one dataset."""

    dataset_id: str
    license_type: str
    allows_commercial: bool
    allows_derivative: bool
    requires_attribution: bool
    restrictions: dict[str, Any]
    verified_by: str | None
    verified_at: str | None
    created_at: str
    updated_at: str


KNOWN_LICENSES: dict[str, dict[str, Any]] = {
    "MIT": {
        "allows_commercial": True,
        "allows_derivative": True,
        "requires_attribution": True,
    },
    "Apache-2.0": {
        "allows_commercial": True,
        "allows_derivative": True,
        "requires_attribution": True,
    },
    "CC-BY-4.0": {
        "allows_commercial": True,
        "allows_derivative": True,
        "requires_attribution": True,
    },
    "CC-BY-NC-4.0": {
        "allows_commercial": False,
        "allows_derivative": True,
        "requires_attribution": True,
    },
    "proprietary": {
        "allows_commercial": False,
        "allows_derivative": False,
        "requires_attribution": False,
    },
    "internal": {
        "allows_commercial": True,
        "allows_derivative": True,
        "requires_attribution": False,
    },
}


class LicenseValidator:
    """In-memory licensing registry with policy checks for evaluation usage."""

    def __init__(self) -> None:
        self._licenses: dict[str, DatasetLicenseRecord] = {}
        self._lock = Lock()

    def register_license(
        self,
        dataset_id: str,
        license_type: str,
        restrictions: dict[str, Any] | None = None,
        verified_by: str | None = None,
    ) -> dict[str, Any]:
        """Register or update a dataset license."""
        if license_type not in KNOWN_LICENSES:
            raise ValueError(f"Unsupported license type: {license_type}")

        now = datetime.now(timezone.utc).isoformat()
        baseline = KNOWN_LICENSES[license_type]
        record = DatasetLicenseRecord(
            dataset_id=dataset_id,
            license_type=license_type,
            allows_commercial=baseline["allows_commercial"],
            allows_derivative=baseline["allows_derivative"],
            requires_attribution=baseline["requires_attribution"],
            restrictions=restrictions or {},
            verified_by=verified_by,
            verified_at=now if verified_by else None,
            created_at=now,
            updated_at=now,
        )

        with self._lock:
            previous = self._licenses.get(dataset_id)
            if previous:
                record.created_at = previous.created_at
            self._licenses[dataset_id] = record

        return asdict(record)

    def get_license(self, dataset_id: str) -> dict[str, Any] | None:
        """Get registered license metadata for a dataset."""
        with self._lock:
            record = self._licenses.get(dataset_id)
        return asdict(record) if record else None

    def validate_license(
        self, dataset_id: str, intended_use: dict[str, bool]
    ) -> LicenseValidationResult:
        """Validate intended usage flags against license allowances."""
        with self._lock:
            record = self._licenses.get(dataset_id)

        if record is None:
            return LicenseValidationResult(
                allowed=False,
                reason="No license registered for dataset",
                required_actions=["register_license"],
            )

        required_actions: list[str] = []
        if intended_use.get("commercial") and not record.allows_commercial:
            return LicenseValidationResult(
                allowed=False,
                reason="License does not permit commercial use",
                required_actions=["use_non_commercial_mode"],
            )

        if intended_use.get("derivative") and not record.allows_derivative:
            return LicenseValidationResult(
                allowed=False,
                reason="License does not permit derivative work",
                required_actions=["disable_derivative_use"],
            )

        if record.requires_attribution:
            required_actions.append("attribution_required")

        return LicenseValidationResult(
            allowed=True, reason="allowed", required_actions=required_actions
        )
