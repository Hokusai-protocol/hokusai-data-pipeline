"""Notify auth-service when contribution lifecycle and reward events change."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.contribution import LifecycleReasonCode, LifecycleUpdatePayload
from src.api.schemas.token_mint import TokenMintResult
from src.api.services.contribution_service import StoredContributionRecord
from src.events.schemas import MintRequest

LOGGER = logging.getLogger(__name__)

_AUTH_ACCEPTED_PATH = "/internal/data-submissions/accepted"
_AUTH_LIFECYCLE_PATH = "/internal/data-submissions/lifecycle-update"
_AUTH_REWARD_ENTITLEMENT_PATH = "/internal/reward-entitlements"
_AUTH_WALLET_RESOLUTION_PATH = "/internal/auth-context/wallet"
_SUBMISSION_SOURCE = "hokusai_data_pipeline"
_ENDPOINT_TEMPLATE = "/api/v1/models/{model_id}/contributions"


class RewardEntitlementContributor(BaseModel):
    """Contributor-level reward entitlement information."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    wallet_address: str = Field(..., alias="walletAddress")
    weight_bps: int = Field(..., alias="weightBps", ge=0, le=10000)
    submission_id: str | None = Field(default=None, alias="submissionId")
    contribution_batch_id: str | None = Field(default=None, alias="contributionBatchId")
    contributor_id: str | None = Field(default=None, alias="contributorId")


class RewardEntitlementPayload(BaseModel):
    """Auth-service reward entitlement event payload."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    event_version: str = Field(default="reward_entitlement.v1", alias="eventVersion")
    status: Literal["pending", "claimable"]
    model_id: str = Field(..., alias="modelId")
    model_id_uint: str = Field(..., alias="modelIdUint")
    eval_id: str = Field(..., alias="evalId")
    mint_request_id: str = Field(..., alias="mintRequestId")
    mint_timestamp: str = Field(..., alias="mintTimestamp")
    attestation_hash: str = Field(..., alias="attestationHash")
    mint_idempotency_key: str = Field(..., alias="mintIdempotencyKey")
    contributors: list[RewardEntitlementContributor]
    vesting: dict[str, Any] | None = None


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
        self.lifecycle_callback_path = (
            os.getenv("HOKUSAI_AUTH_LIFECYCLE_CALLBACK_PATH", _AUTH_LIFECYCLE_PATH).strip()
            or _AUTH_LIFECYCLE_PATH
        )
        self.reward_entitlement_path = (
            os.getenv(
                "HOKUSAI_AUTH_REWARD_ENTITLEMENT_PATH",
                _AUTH_REWARD_ENTITLEMENT_PATH,
            ).strip()
            or _AUTH_REWARD_ENTITLEMENT_PATH
        )
        self.wallet_resolution_path = (
            os.getenv(
                "HOKUSAI_AUTH_WALLET_RESOLUTION_PATH",
                _AUTH_WALLET_RESOLUTION_PATH,
            ).strip()
            or _AUTH_WALLET_RESOLUTION_PATH
        )

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

    def notify_reward_entitlement(
        self: AuthServiceNotifier,
        *,
        mint_request: MintRequest,
        status: Literal["pending", "claimable"],
        mint_result: TokenMintResult | None = None,
    ) -> tuple[bool, str | None]:
        """Post a reward entitlement event to auth-service."""
        vesting_payload = mint_result.vesting_payload() if mint_result is not None else None
        payload = RewardEntitlementPayload(
            status=status,
            model_id=mint_request.model_id,
            model_id_uint=mint_request.model_id_uint,
            eval_id=mint_request.eval_id,
            mint_request_id=mint_request.message_id,
            mint_timestamp=mint_request.timestamp,
            attestation_hash=mint_request.attestation_hash,
            mint_idempotency_key=mint_request.idempotency_key,
            contributors=[
                RewardEntitlementContributor(
                    wallet_address=contributor.wallet_address,
                    weight_bps=contributor.weight_bps,
                    submission_id=contributor.submission_id,
                    contribution_batch_id=contributor.contribution_batch_id,
                    contributor_id=contributor.contributor_id,
                )
                for contributor in mint_request.contributors
            ],
            vesting=vesting_payload,
        )

        if self.dry_run:
            LOGGER.info(
                json.dumps(
                    {
                        "event": "auth_reward_entitlement_dry_run",
                        "mint_idempotency_key": mint_request.idempotency_key,
                        "status": status,
                        "payload": payload.model_dump(mode="json", by_alias=True),
                    },
                    default=str,
                    sort_keys=True,
                )
            )
            return True, None

        headers = {
            "Authorization": f"Bearer {self.internal_token}",
            "Content-Type": "application/json",
            "Idempotency-Key": (f"{mint_request.idempotency_key}:reward_entitlement:{status}"),
        }
        url = f"{self.auth_service_url}{self.reward_entitlement_path}"
        error_message: str | None = None

        for attempt in range(1, self.retry_attempts + 1):
            if attempt > 1:
                time.sleep(2 ** (attempt - 2))
            try:
                response = httpx.post(
                    url,
                    json=payload.model_dump(mode="json", by_alias=True),
                    headers=headers,
                    timeout=self.timeout,
                )
            except httpx.HTTPError as exc:
                error_message = str(exc)
                LOGGER.warning(
                    json.dumps(
                        {
                            "event": "auth_reward_entitlement_request_error",
                            "mint_idempotency_key": mint_request.idempotency_key,
                            "status": status,
                            "attempt": attempt,
                            "max_attempts": self.retry_attempts,
                            "error": error_message,
                        },
                        default=str,
                        sort_keys=True,
                    )
                )
                continue
            except Exception as exc:  # noqa: BLE001
                error_message = str(exc)
                LOGGER.warning(
                    json.dumps(
                        {
                            "event": "auth_reward_entitlement_unexpected_error",
                            "mint_idempotency_key": mint_request.idempotency_key,
                            "status": status,
                            "attempt": attempt,
                            "error": error_message,
                        },
                        default=str,
                        sort_keys=True,
                    )
                )
                return False, error_message

            if response.status_code in {200, 201}:
                LOGGER.info(
                    json.dumps(
                        {
                            "event": "auth_reward_entitlement_succeeded",
                            "mint_idempotency_key": mint_request.idempotency_key,
                            "status": status,
                            "status_code": response.status_code,
                        },
                        default=str,
                        sort_keys=True,
                    )
                )
                return True, None

            error_message = f"{response.status_code}: {response.text[:500]}"
            if response.status_code == 409:
                LOGGER.warning(
                    json.dumps(
                        {
                            "event": "auth_reward_entitlement_conflict",
                            "mint_idempotency_key": mint_request.idempotency_key,
                            "status": status,
                            "status_code": response.status_code,
                            "response_body": response.text[:500],
                        },
                        default=str,
                        sort_keys=True,
                    )
                )
                return True, None

            if response.status_code >= 500:
                LOGGER.warning(
                    json.dumps(
                        {
                            "event": "auth_reward_entitlement_retryable_response",
                            "mint_idempotency_key": mint_request.idempotency_key,
                            "status": status,
                            "attempt": attempt,
                            "max_attempts": self.retry_attempts,
                            "status_code": response.status_code,
                            "response_body": response.text[:500],
                        },
                        default=str,
                        sort_keys=True,
                    )
                )
                continue

            LOGGER.warning(
                json.dumps(
                    {
                        "event": "auth_reward_entitlement_failed",
                        "mint_idempotency_key": mint_request.idempotency_key,
                        "status": status,
                        "status_code": response.status_code,
                        "response_body": response.text[:500],
                    },
                    default=str,
                    sort_keys=True,
                )
            )
            return False, error_message

        LOGGER.warning(
            json.dumps(
                {
                    "event": "auth_reward_entitlement_retry_exhausted",
                    "mint_idempotency_key": mint_request.idempotency_key,
                    "status": status,
                    "attempts": self.retry_attempts,
                    "error": error_message,
                },
                default=str,
                sort_keys=True,
            )
        )
        return False, error_message

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

    def resolve_wallet(  # noqa: C901
        self: AuthServiceNotifier,
        *,
        user_id: str | None,
        api_key_id: str | None = None,
        service_id: str | None = None,
    ) -> str | None:
        """Resolve a wallet address from the auth-service auth-context lookup."""
        if self.dry_run:
            LOGGER.info(
                json.dumps(
                    {
                        "event": "auth_wallet_resolution_dry_run",
                        "user_id": user_id,
                        "api_key_id": api_key_id,
                        "service_id": service_id,
                    },
                    default=str,
                    sort_keys=True,
                )
            )
            return None

        params = {
            key: value
            for key, value in {
                "user_id": user_id,
                "api_key_id": api_key_id,
                "service_id": service_id,
            }.items()
            if value
        }
        if not params:
            return None

        headers = {"Authorization": f"Bearer {self.internal_token}"}
        url = f"{self.auth_service_url}{self.wallet_resolution_path}"
        for attempt in range(1, self.retry_attempts + 1):
            if attempt > 1:
                time.sleep(2 ** (attempt - 2))
            try:
                response = httpx.get(url, params=params, headers=headers, timeout=self.timeout)
            except httpx.HTTPError:
                continue
            except Exception:  # noqa: BLE001
                return None

            if response.status_code == 200:
                try:
                    wallet = response.json().get("wallet_address")
                except Exception:  # noqa: BLE001
                    return None
                if not isinstance(wallet, str):
                    return None
                return wallet

            if response.status_code in {404, 422}:
                return None
            if response.status_code >= 500:
                continue
            return None
        return None

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

    @staticmethod
    def _map_reason_code(cause: str | None) -> LifecycleReasonCode:
        normalized = (cause or "").strip().lower()
        mapping = {
            "schema_validation_failed": LifecycleReasonCode.SCHEMA_VALIDATION_FAILED,
            "duplicate_submission": LifecycleReasonCode.DUPLICATE_SUBMISSION,
            "insufficient_quality": LifecycleReasonCode.INSUFFICIENT_QUALITY,
            "excluded_from_training": LifecycleReasonCode.EXCLUDED_FROM_TRAINING,
        }
        return mapping.get(normalized, LifecycleReasonCode.PROCESSING_ERROR)

    def notify_lifecycle_update(
        self: AuthServiceNotifier,
        payload: LifecycleUpdatePayload,
    ) -> tuple[bool, str | None]:
        """Post a contribution lifecycle update to auth-service."""
        if self.dry_run:
            LOGGER.info(
                json.dumps(
                    {
                        "event": "auth_lifecycle_notification_dry_run",
                        "submission_id": payload.submission_id,
                        "payload": payload.model_dump(mode="json"),
                    },
                    default=str,
                    sort_keys=True,
                )
            )
            return True, None

        headers = {
            "Authorization": f"Bearer {self.internal_token}",
            "Content-Type": "application/json",
            "Idempotency-Key": (
                f"{payload.submission_id}:{payload.status}:{payload.event_version}"
            ),
        }
        url = f"{self.auth_service_url}{self.lifecycle_callback_path}"
        error_message: str | None = None

        for attempt in range(1, self.retry_attempts + 1):
            if attempt > 1:
                time.sleep(2 ** (attempt - 2))
            try:
                response = httpx.post(
                    url,
                    json=payload.model_dump(mode="json"),
                    headers=headers,
                    timeout=self.timeout,
                )
            except httpx.HTTPError as exc:
                error_message = str(exc)
                LOGGER.warning(
                    json.dumps(
                        {
                            "event": "auth_lifecycle_notification_request_error",
                            "submission_id": payload.submission_id,
                            "attempt": attempt,
                            "max_attempts": self.retry_attempts,
                            "error": error_message,
                        },
                        default=str,
                        sort_keys=True,
                    )
                )
                continue
            except Exception as exc:  # noqa: BLE001
                error_message = str(exc)
                LOGGER.warning(
                    json.dumps(
                        {
                            "event": "auth_lifecycle_notification_unexpected_error",
                            "submission_id": payload.submission_id,
                            "attempt": attempt,
                            "error": error_message,
                        },
                        default=str,
                        sort_keys=True,
                    )
                )
                return False, error_message

            if response.status_code in {200, 201}:
                LOGGER.info(
                    json.dumps(
                        {
                            "event": "auth_lifecycle_notification_succeeded",
                            "submission_id": payload.submission_id,
                            "status_code": response.status_code,
                        },
                        default=str,
                        sort_keys=True,
                    )
                )
                return True, None

            error_message = f"{response.status_code}: {response.text[:500]}"
            if response.status_code >= 500:
                LOGGER.warning(
                    json.dumps(
                        {
                            "event": "auth_lifecycle_notification_retryable_response",
                            "submission_id": payload.submission_id,
                            "attempt": attempt,
                            "max_attempts": self.retry_attempts,
                            "status_code": response.status_code,
                            "response_body": response.text[:500],
                        },
                        default=str,
                        sort_keys=True,
                    )
                )
                continue

            LOGGER.warning(
                json.dumps(
                    {
                        "event": "auth_lifecycle_notification_failed",
                        "submission_id": payload.submission_id,
                        "status_code": response.status_code,
                        "response_body": response.text[:500],
                    },
                    default=str,
                    sort_keys=True,
                )
            )
            return False, error_message

        LOGGER.warning(
            json.dumps(
                {
                    "event": "auth_lifecycle_notification_retry_exhausted",
                    "submission_id": payload.submission_id,
                    "attempts": self.retry_attempts,
                    "error": error_message,
                },
                default=str,
                sort_keys=True,
            )
        )
        return False, error_message
