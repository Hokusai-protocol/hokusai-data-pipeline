"""Unit tests for governance audit logger."""

from __future__ import annotations

from src.api.services.governance.audit_logger import AuditLogger


def test_audit_logger_writes_entries() -> None:
    logger = AuditLogger()

    logger.log(
        action="eval.create",
        resource_type="evaluation",
        resource_id="job-1",
        user_id="u-1",
        details={"private": True},
        outcome="success",
    )

    logger._executor.shutdown(wait=True)  # noqa: SLF001
    logs = logger.get_logs({"user_id": "u-1"})

    assert len(logs) == 1
    assert logs[0]["action"] == "eval.create"
    assert logs[0]["details"]["private"] is True
