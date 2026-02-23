"""Unit tests for GDPR helpers."""

from __future__ import annotations

from src.api.services.governance.gdpr import GDPRService


def test_consent_record_and_check() -> None:
    service = GDPRService()
    service.record_consent("user-1", "data_processing", True)

    assert service.check_consent("user-1", "data_processing") is True

    service.record_consent("user-1", "data_processing", False)
    assert service.check_consent("user-1", "data_processing") is False


def test_export_and_delete_user_data() -> None:
    service = GDPRService()
    service.record_consent("user-2", "evaluation_storage", True)
    service.register_exporter("audit_logs", lambda user_id: [{"user_id": user_id}])
    service.register_deleter("audit_logs", lambda user_id: 2)

    exported = service.export_user_data("user-2")
    report = service.delete_user_data("user-2")

    assert exported["user_id"] == "user-2"
    assert report.deleted["audit_logs"] == 2
    assert report.anonymized["consent_records"] == 1
