"""Privacy control API routes."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from src.api.dependencies import get_audit_logger, get_pii_detector
from src.api.services.governance.audit_logger import AuditLogger
from src.api.services.privacy.pii_detector import PIIDetector
from src.middleware.auth import require_auth

router = APIRouter(prefix="/api/v1/privacy", tags=["privacy"])


def _is_admin(auth_payload: dict[str, Any]) -> bool:
    token = str(auth_payload.get("token", "")).lower()
    user_id = str(auth_payload.get("user_id", "")).lower()
    scopes = auth_payload.get("scopes", [])
    return "admin" in token or user_id in {"admin", "root"} or "admin" in scopes


@router.post("/scan")
async def scan_privacy_payload(
    text: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    detector: PIIDetector = Depends(get_pii_detector),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Scan uploaded text/file for PII and return structured findings."""
    if not text and not file:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either text or file payload",
        )

    if text:
        result = detector.scan_text_result(text).to_dict()
        audit_logger.log(
            action="privacy.scan.text",
            resource_type="privacy_scan",
            resource_id="inline",
            user_id=_auth.get("user_id", "unknown"),
            details={"findings": result["total_findings"]},
            outcome="success",
        )
        return result

    suffix = Path(file.filename or "input.txt").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        data = await file.read()
        handle.write(data)
        temp_path = handle.name

    try:
        result = detector.scan_file(temp_path).to_dict()
        audit_logger.log(
            action="privacy.scan.file",
            resource_type="privacy_scan",
            resource_id=file.filename or "uploaded",
            user_id=_auth.get("user_id", "unknown"),
            details={"findings": result["total_findings"]},
            outcome="success",
        )
        return result
    finally:
        Path(temp_path).unlink(missing_ok=True)


@router.post("/scan/dataset/{dataset_id}")
async def scan_dataset(
    dataset_id: str,
    detector: PIIDetector = Depends(get_pii_detector),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    _auth: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Scan a dataset by ID from local dataset storage path."""
    base_dir = Path(os.getenv("DATASET_STORAGE_DIR", "data/datasets"))
    candidates = [
        base_dir / f"{dataset_id}.csv",
        base_dir / f"{dataset_id}.json",
        base_dir / f"{dataset_id}.jsonl",
    ]

    dataset_file = next((path for path in candidates if path.exists()), None)
    if dataset_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    result = detector.scan_file(str(dataset_file)).to_dict()
    audit_logger.log(
        action="privacy.scan.dataset",
        resource_type="dataset",
        resource_id=dataset_id,
        user_id=_auth.get("user_id", "unknown"),
        details={"findings": result["total_findings"]},
        outcome="success",
    )

    if result["total_findings"] and not _is_admin(_auth):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "PII detected", "findings": result["findings"]},
        )
    return result
