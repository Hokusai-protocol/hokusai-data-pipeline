"""Governance and compliance API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.api.dependencies import (
    get_audit_logger,
    get_gdpr_service,
    get_license_validator,
    get_retention_manager,
)
from src.api.services.governance.audit_logger import AuditLogger
from src.api.services.governance.gdpr import GDPRService
from src.api.services.governance.licensing import LicenseValidator
from src.api.services.governance.retention import RetentionManager
from src.middleware.auth import require_auth

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])


class RetentionPolicyRequest(BaseModel):
    """Payload for creating/updating retention policy."""

    retention_days: int = Field(..., gt=0)
    delete_action: str = Field(..., pattern="^(hard_delete|soft_delete|archive)$")


class LicenseRegistrationRequest(BaseModel):
    """Payload for dataset license registration."""

    dataset_id: str
    license_type: str
    restrictions: dict[str, Any] = Field(default_factory=dict)


class LicenseValidationRequest(BaseModel):
    """Payload for intended-use license checks."""

    commercial: bool = False
    derivative: bool = False


class ConsentRequest(BaseModel):
    """Payload for GDPR consent tracking."""

    user_id: str
    consent_type: str
    granted: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


def _is_admin(auth_payload: dict[str, Any]) -> bool:
    token = str(auth_payload.get("token", "")).lower()
    user_id = str(auth_payload.get("user_id", "")).lower()
    scopes = auth_payload.get("scopes", [])
    return "admin" in token or user_id in {"admin", "root"} or "admin" in scopes


def _assert_admin(auth_payload: dict[str, Any]) -> None:
    if not _is_admin(auth_payload):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")


@router.get("/audit-logs")
async def get_audit_logs(
    user_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Query audit logs with common governance filters."""
    _assert_admin(_auth)
    logs = audit_logger.get_logs(
        {
            "user_id": user_id,
            "action": action,
            "resource_type": resource_type,
            "start": start,
            "end": end,
        }
    )
    return {"logs": logs, "count": len(logs)}


@router.get("/retention-policies")
async def list_retention_policies(
    retention: RetentionManager = Depends(get_retention_manager),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """List configured retention policies."""
    _assert_admin(_auth)
    policies = retention.list_policies()
    return {"policies": policies}


@router.put("/retention-policies/{resource_type}")
async def put_retention_policy(
    resource_type: str,
    request: RetentionPolicyRequest,
    retention: RetentionManager = Depends(get_retention_manager),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Create or update a retention policy."""
    _assert_admin(_auth)
    policy = retention.set_policy(resource_type, request.retention_days, request.delete_action)
    audit_logger.log(
        action="governance.retention.set",
        resource_type="retention_policy",
        resource_id=resource_type,
        user_id=_auth.get("user_id", "unknown"),
        details={"retention_days": request.retention_days, "delete_action": request.delete_action},
        outcome="success",
    )
    return policy


@router.post("/retention/apply")
async def apply_retention(
    retention: RetentionManager = Depends(get_retention_manager),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Apply enabled retention policies."""
    _assert_admin(_auth)
    report = retention.apply_policies()
    audit_logger.log(
        action="governance.retention.apply",
        resource_type="retention_policy",
        resource_id="all",
        user_id=_auth.get("user_id", "unknown"),
        details=report,
        outcome="success",
    )
    return {"applied": report}


@router.get("/licenses/{dataset_id}")
async def get_dataset_license(
    dataset_id: str,
    validator: LicenseValidator = Depends(get_license_validator),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Return license metadata for a dataset."""
    _assert_admin(_auth)
    record = validator.get_license(dataset_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    return record


@router.post("/licenses")
async def register_license(
    request: LicenseRegistrationRequest,
    validator: LicenseValidator = Depends(get_license_validator),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Register dataset license metadata."""
    _assert_admin(_auth)
    record = validator.register_license(
        dataset_id=request.dataset_id,
        license_type=request.license_type,
        restrictions=request.restrictions,
        verified_by=_auth.get("user_id"),
    )
    audit_logger.log(
        action="governance.license.register",
        resource_type="dataset_license",
        resource_id=request.dataset_id,
        user_id=_auth.get("user_id", "unknown"),
        details={"license_type": request.license_type},
        outcome="success",
    )
    return record


@router.post("/licenses/{dataset_id}/validate")
async def validate_license(
    dataset_id: str,
    request: LicenseValidationRequest,
    validator: LicenseValidator = Depends(get_license_validator),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Validate intended dataset use against registered license."""
    result = validator.validate_license(dataset_id, request.model_dump())
    audit_logger.log(
        action="governance.license.validate",
        resource_type="dataset_license",
        resource_id=dataset_id,
        user_id=_auth.get("user_id", "unknown"),
        details=request.model_dump(),
        outcome="success" if result.allowed else "denied",
    )
    return {
        "allowed": result.allowed,
        "reason": result.reason,
        "required_actions": result.required_actions,
    }


@router.post("/gdpr/export/{user_id}")
async def export_user_data(
    user_id: str,
    gdpr: GDPRService = Depends(get_gdpr_service),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Export all known user data for GDPR portability requests."""
    if _auth.get("user_id") != user_id and not _is_admin(_auth):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    payload = gdpr.export_user_data(user_id)
    audit_logger.log(
        action="governance.gdpr.export",
        resource_type="user_data",
        resource_id=user_id,
        user_id=_auth.get("user_id", "unknown"),
        outcome="success",
    )
    return payload


@router.post("/gdpr/delete/{user_id}")
async def delete_user_data(
    user_id: str,
    gdpr: GDPRService = Depends(get_gdpr_service),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Delete/anonymize all user-linked data for GDPR erasure requests."""
    _assert_admin(_auth)
    report = gdpr.delete_user_data(user_id)
    audit_logger.log(
        action="governance.gdpr.delete",
        resource_type="user_data",
        resource_id=user_id,
        user_id=_auth.get("user_id", "unknown"),
        details=report.deleted,
        outcome="success",
    )
    return {"user_id": report.user_id, "deleted": report.deleted, "anonymized": report.anonymized}


@router.post("/gdpr/consent")
async def record_consent(
    request: ConsentRequest,
    gdpr: GDPRService = Depends(get_gdpr_service),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Create a consent grant/revoke record."""
    if _auth.get("user_id") != request.user_id and not _is_admin(_auth):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    row = gdpr.record_consent(
        user_id=request.user_id,
        consent_type=request.consent_type,
        granted=request.granted,
        metadata=request.metadata,
    )
    audit_logger.log(
        action="governance.gdpr.consent.record",
        resource_type="consent",
        resource_id=request.user_id,
        user_id=_auth.get("user_id", "unknown"),
        details={"consent_type": request.consent_type, "granted": request.granted},
        outcome="success",
    )
    return row


@router.get("/gdpr/consent/{user_id}")
async def get_consent_status(
    user_id: str,
    consent_type: str | None = Query(default=None),
    gdpr: GDPRService = Depends(get_gdpr_service),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Get consent status and history for a user."""
    if _auth.get("user_id") != user_id and not _is_admin(_auth):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    history = gdpr.get_consent_history(user_id)
    if consent_type:
        return {
            "user_id": user_id,
            "consent_type": consent_type,
            "granted": gdpr.check_consent(user_id, consent_type),
            "history": [item for item in history if item["consent_type"] == consent_type],
        }
    return {"user_id": user_id, "history": history}
