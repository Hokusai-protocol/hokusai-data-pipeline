"""Unit tests for PII detector service."""

from __future__ import annotations

import json

from src.api.services.privacy.pii_detector import PIIDetector


def test_scan_text_detects_common_pii() -> None:
    detector = PIIDetector()
    text = "Contact john@example.com or 555-123-4567. SSN 123-45-6789"

    findings = detector.scan_text(text)
    entity_types = {item.entity_type for item in findings}

    assert "EMAIL" in entity_types
    assert "PHONE" in entity_types
    assert "SSN" in entity_types


def test_scan_file_jsonl(tmp_path) -> None:
    detector = PIIDetector()
    file_path = tmp_path / "dataset.jsonl"
    rows = [
        {"text": "Alice lives at 123 Main St"},
        {"text": "Email me at test@example.org"},
    ]
    file_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    result = detector.scan_file(str(file_path))

    assert result.total_findings >= 1
    assert result.scanned_records == 2
