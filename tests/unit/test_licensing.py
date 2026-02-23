"""Unit tests for dataset license validation."""

from __future__ import annotations

from src.api.services.governance.licensing import LicenseValidator


def test_non_commercial_license_blocks_commercial_use() -> None:
    validator = LicenseValidator()
    validator.register_license("dataset-1", "CC-BY-NC-4.0")

    result = validator.validate_license("dataset-1", {"commercial": True, "derivative": False})

    assert result.allowed is False
    assert "commercial" in result.reason.lower()


def test_mit_license_allows_standard_use() -> None:
    validator = LicenseValidator()
    validator.register_license("dataset-2", "MIT")

    result = validator.validate_license("dataset-2", {"commercial": True, "derivative": True})

    assert result.allowed is True
