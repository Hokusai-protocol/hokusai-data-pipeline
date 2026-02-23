"""Unit tests for retention manager."""

from __future__ import annotations

from src.api.services.governance.retention import RetentionManager


def test_retention_policy_lifecycle() -> None:
    manager = RetentionManager()
    manager.set_policy("audit_log", retention_days=30, delete_action="archive")

    called = {"count": 0}

    def fake_handler(cutoff, delete_action):
        assert delete_action == "archive"
        assert cutoff is not None
        called["count"] += 1
        return 7

    manager.register_handler("audit_log", fake_handler)
    report = manager.apply_policies()

    assert called["count"] == 1
    assert report["audit_log"] == 7
