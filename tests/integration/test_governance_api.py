"""Integration tests for governance/privacy API routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_audit_logger,
    get_gdpr_service,
    get_license_validator,
    get_retention_manager,
)
from src.api.routes.governance import router as governance_router
from src.api.routes.privacy import router as privacy_router
from src.middleware.auth import require_auth

AUTH_HEADER = {"Authorization": "Bearer admin-token"}


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(governance_router)
    app.include_router(privacy_router)
    app.dependency_overrides[require_auth] = lambda: {
        "user_id": "admin",
        "token": "admin-token",
        "scopes": ["admin"],
    }

    # Reset singleton state between tests
    get_audit_logger.cache_clear()
    get_license_validator.cache_clear()
    get_retention_manager.cache_clear()
    get_gdpr_service.cache_clear()

    return TestClient(app)


def test_license_register_and_validate_flow() -> None:
    client = build_client()

    register_resp = client.post(
        "/api/v1/governance/licenses",
        headers=AUTH_HEADER,
        json={"dataset_id": "dataset-a", "license_type": "CC-BY-NC-4.0", "restrictions": {}},
    )
    assert register_resp.status_code == 200

    validate_resp = client.post(
        "/api/v1/governance/licenses/dataset-a/validate",
        headers=AUTH_HEADER,
        json={"commercial": True, "derivative": False},
    )
    assert validate_resp.status_code == 200
    assert validate_resp.json()["allowed"] is False


def test_retention_policy_endpoints() -> None:
    client = build_client()

    put_resp = client.put(
        "/api/v1/governance/retention-policies/audit_log",
        headers=AUTH_HEADER,
        json={"retention_days": 30, "delete_action": "archive"},
    )
    assert put_resp.status_code == 200

    list_resp = client.get("/api/v1/governance/retention-policies", headers=AUTH_HEADER)
    assert list_resp.status_code == 200
    assert len(list_resp.json()["policies"]) == 1


def test_gdpr_consent_endpoints() -> None:
    client = build_client()

    consent_resp = client.post(
        "/api/v1/governance/gdpr/consent",
        headers=AUTH_HEADER,
        json={
            "user_id": "test-user",
            "consent_type": "data_processing",
            "granted": True,
            "metadata": {},
        },
    )
    assert consent_resp.status_code == 200

    get_resp = client.get(
        "/api/v1/governance/gdpr/consent/test-user?consent_type=data_processing",
        headers=AUTH_HEADER,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["granted"] is True


def test_privacy_scan_text() -> None:
    client = build_client()

    scan_resp = client.post(
        "/api/v1/privacy/scan",
        headers=AUTH_HEADER,
        data={"text": "Email me at jane@example.com"},
    )
    assert scan_resp.status_code == 200
    assert scan_resp.json()["total_findings"] >= 1
