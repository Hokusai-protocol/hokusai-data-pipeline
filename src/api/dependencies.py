"""Dependency providers for API routes."""

from __future__ import annotations

from functools import lru_cache

import redis
from fastapi import Depends
from redis import Redis

from src.api.services.contributor_logger import ContributorLogger
from src.api.services.evaluation_service import EvaluationService
from src.api.services.governance.audit_logger import AuditLogger
from src.api.services.governance.gdpr import GDPRService
from src.api.services.governance.licensing import LicenseValidator
from src.api.services.governance.retention import RetentionManager
from src.api.services.privacy.pii_detector import PIIDetector
from src.api.utils.config import get_settings


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    """Return a shared Redis client backed by a connection pool."""
    settings = get_settings()
    pool = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    return redis.Redis(connection_pool=pool)


@lru_cache(maxsize=1)
def get_pii_detector() -> PIIDetector:
    """Return shared PII detector singleton."""
    return PIIDetector()


@lru_cache(maxsize=1)
def get_audit_logger() -> AuditLogger:
    """Return shared audit logger instance."""
    return AuditLogger()


@lru_cache(maxsize=1)
def get_retention_manager() -> RetentionManager:
    """Return shared retention manager instance."""
    return RetentionManager()


@lru_cache(maxsize=1)
def get_license_validator() -> LicenseValidator:
    """Return shared dataset license validator."""
    return LicenseValidator()


@lru_cache(maxsize=1)
def get_gdpr_service() -> GDPRService:
    """Return shared GDPR service."""
    service = GDPRService()
    return service


def get_evaluation_service(
    redis_client: Redis = Depends(get_redis_client),
    pii_detector: PIIDetector = Depends(get_pii_detector),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    license_validator: LicenseValidator = Depends(get_license_validator),
) -> EvaluationService:
    """Return a service instance for evaluation operations."""
    return EvaluationService(
        redis_client=redis_client,
        pii_detector=pii_detector,
        audit_logger=audit_logger,
        license_validator=license_validator,
    )


@lru_cache(maxsize=1)
def get_contributor_logger() -> ContributorLogger:
    """Return shared contributor logger instance."""
    return ContributorLogger()
