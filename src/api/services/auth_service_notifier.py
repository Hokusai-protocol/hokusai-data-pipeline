"""Notify auth-service when a contribution submission is accepted."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any
from uuid import UUID

import httpx

from src.api.services.contribution_service import StoredContributionRecord

LOGGER = logging.getLogger(__name__)

_AUTH_ACCEPTED_PATH = "/internal/data-submissions/accepted"
_SUBMISSION_SOURCE = "hokusai_data_pipeline"
_ENDPOINT_TEMPLATE = "/api/v1/models/{model_id}/contributions"


class AuthServiceNotifier:
    """Small sync client for accepted-submission ledger events."""

    def __init__(
        self: AuthServiceNotifier,
        *,
        auth_service_url: str,
        internal_token: str | None,
        dry_run: bool,
        timeout: float = 5.0,
        retry_attempts: int = 2,
    ) -> None:
        self.auth_service_url = auth_service_url.rstrip("/")
        self.internal_token = (internal_token or "").strip()
        self.dry_run = dry_run
        self.timeout = timeout
        self.retry_attempts = max(1, retry_attempts)

    @classmethod
    def from_env(cls: type[AuthServiceNotifier]) -> AuthServiceNotifier:
        """Build an instance from environment-backed defaults."""
        auth_service_url = os.getenv("HOKUSAI_AUTH_SERVICE_URL", "https://auth.hokus.ai")
        internal_token = os.getenv("HOKUSAI_AUTH_INTERNAL_TOKEN", "")
        callback_enabled = (
            os.getenv("CONTRIBUTION_AUTH_CALLBACK_ENABLED", "false").strip().lower() == "true"
        )
        return cls(
            auth_service_url=auth_service_url,
            internal_token=internal_token,
            dry_run=not callback_enabled or not bool(internal_token.strip()),
        )

    def notify_accepted(
        self: AuthServiceNotifier,
        *,
        record: StoredContributionRecord,
        auth: dict[str, Any],
        storage_ref: str | None = None,
    ) -> None:
        """Post an accepted-submission event to auth service."""
        user_id = self._parse_uuid(value=auth.get("user_id"), field_name="user_id", record=record)
        api_key_id = self._parse_uuid(
            value=auth.get("api_key_id"),
            field_name="api_key_id",
            record=record,
        )
        if user_id is None or api_key_id is None:
            return

        payload = {
            "submissionId": record.submission_id,
            "jobId": record.submission_id,
            "modelId": record.model_id,
            "rowsAccepted": len(record.rows),
            "idempotencyKey": record.idempotency_key,
            "body_hash": record.body_hash,
            "storageRef": storage_ref,
            "timestamp": record.created_at,
            "source": _SUBMISSION_SOURCE,
            "endpoint": _ENDPOINT_TEMPLATE.format(model_id=record.model_id),
            "user_id": str(user_id),
            "api_key_id": str(api_key_id),
            "service_id": auth.get("service_id"),
        }

        if self.dry_run:
            LOGGER.info(
                json.dumps(
                    {
                        "event": "auth_submission_notification_dry_run",
                        "submission_id": record.submission_id,
                        "payload": payload,
                    },
                    default=str,
                    sort_keys=True,
                )
            )
            return

        headers = {
            "Authorization": f"Bearer {self.internal_token}",
            "Content-Type": "application/json",
            "Idempotency-Key": record.idempotency_key,
        }
        url = f"{self.auth_service_url}{_AUTH_ACCEPTED_PATH}"

        for attempt in range(1, self.retry_attempts + 1):
            if attempt > 1:
                time.sleep(2 ** (attempt - 2))
            try:
                response = httpx.post(url, json=payload, headers=headers, timeout=self.timeout)
            except httpx.HTTPError as exc:
                self._log_retryable_warning(
                    event="auth_submission_notification_request_error",
                    record=record,
                    attempt=attempt,
                    error=str(exc),
                )
                continue
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning(
                    json.dumps(
                        {
                            "event": "auth_submission_notification_unexpected_error",
                            "submission_id": record.submission_id,
                            "attempt": attempt,
                            "error": str(exc),
                        },
                        default=str,
                        sort_keys=True,
                    )
                )
                return

            if response.status_code in {200, 201}:
                LOGGER.info(
                    json.dumps(
                        {
                            "event": "auth_submission_notification_succeeded",
                            "submission_id": record.submission_id,
                            "status_code": response.status_code,
                        },
                        default=str,
                        sort_keys=True,
                    )
                )
                return

            if response.status_code == 409:
                LOGGER.warning(
                    json.dumps(
                        {
                            "event": "auth_submission_notification_conflict",
                            "submission_id": record.submission_id,
                            "status_code": response.status_code,
                            "response_body": response.text[:500],
                        },
                        default=str,
                        sort_keys=True,
                    )
                )
                return

            if response.status_code >= 500:
                self._log_retryable_warning(
                    event="auth_submission_notification_retryable_response",
                    record=record,
                    attempt=attempt,
                    status_code=response.status_code,
                    response_body=response.text[:500],
                )
                continue

            LOGGER.warning(
                json.dumps(
                    {
                        "event": "auth_submission_notification_failed",
                        "submission_id": record.submission_id,
                        "status_code": response.status_code,
                        "response_body": response.text[:500],
                    },
                    default=str,
                    sort_keys=True,
                )
            )
            return

        LOGGER.warning(
            json.dumps(
                {
                    "event": "auth_submission_notification_retry_exhausted",
                    "submission_id": record.submission_id,
                    "attempts": self.retry_attempts,
                },
                default=str,
                sort_keys=True,
            )
        )

    def _parse_uuid(
        self: AuthServiceNotifier,
        *,
        value: Any,
        field_name: str,
        record: StoredContributionRecord,
    ) -> UUID | None:
        if value is None:
            LOGGER.warning(
                json.dumps(
                    {
                        "event": "auth_submission_notification_skipped_invalid_auth_context",
                        "submission_id": record.submission_id,
                        "field": field_name,
                        "value": value,
                    },
                    default=str,
                    sort_keys=True,
                )
            )
            return None
        try:
            return UUID(str(value))
        except (TypeError, ValueError, AttributeError):
            LOGGER.warning(
                json.dumps(
                    {
                        "event": "auth_submission_notification_skipped_invalid_auth_context",
                        "submission_id": record.submission_id,
                        "field": field_name,
                        "value": value,
                    },
                    default=str,
                    sort_keys=True,
                )
            )
            return None

    def _log_retryable_warning(
        self: AuthServiceNotifier,
        *,
        event: str,
        record: StoredContributionRecord,
        attempt: int,
        error: str | None = None,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        LOGGER.warning(
            json.dumps(
                {
                    "event": event,
                    "submission_id": record.submission_id,
                    "attempt": attempt,
                    "max_attempts": self.retry_attempts,
                    "status_code": status_code,
                    "response_body": response_body,
                    "error": error,
                },
                default=str,
                sort_keys=True,
            )
        )
