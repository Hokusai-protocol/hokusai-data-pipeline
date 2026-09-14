"""Notify auth-service when contribution lifecycle and reward events change."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import quote
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.contribution import LifecycleReasonCode, LifecycleUpdatePayload
from src.api.schemas.token_mint import TokenMintResult
from src.api.services.contribution_service import StoredContributionRecord
from src.events.schemas import MintRequest

LOGGER = logging.getLogger(__name__)

# HOK-2256: the /api/v1 prefix is required — the deployed auth route is
# /api/v1/internal/data-submissions/accepted (bare /internal/... 404s).
_AUTH_ACCEPTED_PATH = "/api/v1/internal/data-submissions/accepted"
# HOK-2256: the lifecycle callback lands on auth's canonical processing endpoint
# (POST /api/v1/internal/data-submissions/processed). There is no separate
# /lifecycle-update route on the deployed service; the lifecycle payload is remapped
# to ProcessedDataSubmissionUpdateRequest in ``_build_processed_body``.
_AUTH_LIFECYCLE_PATH = "/api/v1/internal/data-submissions/processed"
_AUTH_REWARD_ENTITLEMENT_PATH = "/internal/reward-entitlements"
# Canonical account-centric reward ingest (HOK-2270): one idempotent row per contributor.
_AUTH_REWARD_INGEST_PATH = "/api/v1/internal/rewards/ingest"
_AUTH_DIRECT_MINT_SETTLEMENT_PATH = "/api/v1/internal/rewards/settlements/direct-mint"
# HOK-2243/2244: account -> verified-wallet resolver. user_id is a PATH param; the
# /api/v1 prefix is required (the bare /internal/... path 404s on the deployed service).
_AUTH_WALLET_RESOLUTION_PATH = "/api/v1/internal/users/{user_id}/wallet"
_SUBMISSION_SOURCE = "hokusai_data_pipeline"
_ENDPOINT_TEMPLATE = "/api/v1/models/{model_id}/contributions"


@dataclass(frozen=True)
class WalletResolution:
    """Outcome of an account -> payout-wallet lookup against auth-service (HOK-2243).

    - ``resolved=False``: auth gave no definitive answer (missing user_id, dry-run,
      auth/token error, unknown user, timeout). Callers must NOT treat this as
      "no wallet" — the contributor's disposition is unknown.
    - ``resolved=True, has_verified_wallet=False``: the definitive "this account has
      no verified wallet yet" signal -> route the reward to escrow (HOK-2246), never drop.
    - ``resolved=True, has_verified_wallet=True``: use ``wallet_address`` as the recipient.
    """

    resolved: bool
    has_verified_wallet: bool
    wallet_address: str | None


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


class RewardIngestRow(BaseModel):
    """One account-centric reward row for auth's POST /internal/rewards/ingest (HOK-2270).

    Mirrors auth's RewardIngestRequest: snake_case fields, ``reward_metadata`` serialized as
    ``metadata``. ``recipient_kind`` ("wallet" | "escrow") is the explicit routing flag so auth
    records escrow tranches as pending without matching the escrow address.
    """

    model_config = ConfigDict(populate_by_name=True)

    reward_id: str
    submission_id: str
    user_id: str
    model_id: str | None = None
    token_symbol: str | None = None
    token_address: str | None = None
    amount: Decimal
    status: Literal["pending", "claimable"]
    recipient_kind: str = "wallet"
    reward_metadata: dict[str, Any] | None = Field(default=None, serialization_alias="metadata")


class DirectMintSettlementPayload(BaseModel):
    """Auth-service direct-mint settlement callback payload."""

    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    reward_id: str
    submission_id: str
    user_id: str
    model_id: str | None = None
    token_symbol: str
    token_address: str
    amount: Decimal
    recipient_address: str
    claim_tx_hash: str
    claim_reference: str | None = None
    claimed_at: str | None = None
    immediate_amount: Decimal | None = None
    vested_amount: Decimal | None = None
    vesting_schedule: dict[str, Any] | None = None
    deployment: dict[str, Any] | None = None
    reward_metadata: dict[str, Any] | None = Field(default=None, serialization_alias="metadata")


def _metadata_string(metadata: dict[str, Any] | None, key: str) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _split_vesting_amounts(
    *,
    amount: Decimal,
    total_reward: Decimal,
    mint_result: TokenMintResult,
) -> tuple[Decimal | None, Decimal | None]:
    vesting = mint_result.vesting_payload() or {}
    liquid_total = vesting.get("liquid_amount")
    vested_total = vesting.get("vested_amount")
    if liquid_total is None and vested_total is None:
        return None, None

    immediate = (
        Decimal(str(liquid_total)) * amount / total_reward
        if liquid_total is not None and total_reward != 0
        else None
    )
    vested = (
        Decimal(str(vested_total)) * amount / total_reward
        if vested_total is not None and total_reward != 0
        else None
    )
    return immediate, vested


def _build_vesting_schedule(
    *,
    contributor_address: str,
    token_address: str,
    total_vested_amount: Decimal | None,
    mint_result: TokenMintResult,
) -> dict[str, Any] | None:
    vesting = mint_result.vesting_payload()
    if not vesting or total_vested_amount is None:
        return None
    schedule_id = vesting.get("schedule_id")
    vault_address = vesting.get("vault_address")
    if not schedule_id or not vault_address:
        return None

    schedule: dict[str, Any] = {
        "schedule_id": str(schedule_id),
        "vault_address": str(vault_address),
        "token_address": str(vesting.get("token_address") or token_address),
        "beneficiary_address": str(
            vesting.get("beneficiary_address")
            or mint_result.recipient_address
            or contributor_address
        ),
        "total_amount": total_vested_amount,
        "claimed_amount": vesting.get("claimed_amount") or "0",
    }
    optional_fields = (
        "claimable_amount",
        "start_at",
        "end_at",
        "duration_seconds",
        "cliff_seconds",
    )
    for field_name in optional_fields:
        value = vesting.get(field_name)
        if value is not None:
            schedule[field_name] = value
    return schedule


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
        self.reward_ingest_path = (
            os.getenv(
                "HOKUSAI_AUTH_REWARD_INGEST_PATH",
                _AUTH_REWARD_INGEST_PATH,
            ).strip()
            or _AUTH_REWARD_INGEST_PATH
        )
        self.direct_mint_settlement_path = (
            os.getenv(
                "HOKUSAI_AUTH_DIRECT_MINT_SETTLEMENT_PATH",
                _AUTH_DIRECT_MINT_SETTLEMENT_PATH,
            ).strip()
            or _AUTH_DIRECT_MINT_SETTLEMENT_PATH
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
        recipient_kinds: dict[str, str] | None = None,
        reward_tokens: float | None = None,
        token_address: str | None = None,
    ) -> tuple[bool, str | None]:
        """Ingest one account-centric reward row per contributor into auth (HOK-2270).

        Posts to ``/api/v1/internal/rewards/ingest`` (the canonical account-centric, idempotent
        seam) -- one ``RewardIngestRow`` per contributor keyed by ``user_id`` (the account /
        ``contributor_id``). ``recipient_kinds`` maps ``wallet_address`` -> "wallet"|"escrow"
        (the mint-time routing flag, default "wallet"); ``reward_tokens`` is the total minted,
        split per contributor by ``weight_bps`` for the row ``amount``.

        Contributors without an account (``contributor_id``) or ``submission_id`` are skipped
        with a warning -- the account-centric seam needs both -- rather than failing the batch.
        Returns (all_delivered, first_error); a 409 is treated as an idempotent success.
        """
        kinds = recipient_kinds or {}
        rows = self._build_reward_ingest_rows(
            mint_request=mint_request,
            status=status,
            kinds=kinds,
            reward_tokens=reward_tokens,
            mint_result=mint_result,
            token_address=token_address,
        )

        if self.dry_run:
            LOGGER.info(
                json.dumps(
                    {
                        "event": "auth_reward_ingest_dry_run",
                        "mint_idempotency_key": mint_request.idempotency_key,
                        "status": status,
                        "rows": [row.model_dump(mode="json", by_alias=True) for row in rows],
                    },
                    default=str,
                    sort_keys=True,
                )
            )
            return True, None

        all_delivered = True
        first_error: str | None = None
        for row in rows:
            delivered, error = self._post_reward_ingest(row=row, status=status)
            if not delivered:
                all_delivered = False
                first_error = first_error or error
        return all_delivered, first_error

    def notify_direct_mint_settlement(
        self: AuthServiceNotifier,
        *,
        mint_request: MintRequest,
        mint_result: TokenMintResult,
        reward_tokens: float,
        token_address: str | None = None,
        token_symbol: str | None = None,
        deployment: dict[str, Any] | None = None,
        recipient_kinds: dict[str, str] | None = None,
    ) -> tuple[bool, str | None]:
        """Record successful direct wallet mints in auth as claimed rewards.

        This callback is receipt-driven: callers must provide a successful mint result with a
        transaction hash plus token address/symbol. Rows routed to escrow are skipped because this
        endpoint describes direct-to-user-wallet settlement only.
        """
        rows = self._build_direct_mint_settlement_rows(
            mint_request=mint_request,
            mint_result=mint_result,
            reward_tokens=reward_tokens,
            token_address=token_address,
            token_symbol=token_symbol,
            deployment=deployment,
            recipient_kinds=recipient_kinds or {},
        )
        if self.dry_run:
            LOGGER.info(
                json.dumps(
                    {
                        "event": "auth_direct_mint_settlement_dry_run",
                        "mint_idempotency_key": mint_request.idempotency_key,
                        "rows": [row.model_dump(mode="json", by_alias=True) for row in rows],
                    },
                    default=str,
                    sort_keys=True,
                )
            )
            return True, None

        all_delivered = True
        first_error: str | None = None
        for row in rows:
            delivered, error = self._post_direct_mint_settlement(row=row)
            if not delivered:
                all_delivered = False
                first_error = first_error or error
        return all_delivered, first_error

    def _build_reward_ingest_rows(
        self: AuthServiceNotifier,
        *,
        mint_request: MintRequest,
        status: Literal["pending", "claimable"],
        kinds: dict[str, str],
        reward_tokens: float | None,
        mint_result: TokenMintResult | None = None,
        token_address: str | None = None,
    ) -> list[RewardIngestRow]:
        total = Decimal(str(reward_tokens)) if reward_tokens is not None else None
        vesting = mint_result.vesting_payload() if mint_result is not None else None
        rows: list[RewardIngestRow] = []
        for contributor in mint_request.contributors:
            user_id = contributor.contributor_id
            submission_id = contributor.submission_id
            if not user_id or not submission_id:
                LOGGER.warning(
                    json.dumps(
                        {
                            "event": "auth_reward_ingest_skipped_missing_identity",
                            "mint_idempotency_key": mint_request.idempotency_key,
                            "wallet_address": contributor.wallet_address,
                            "has_user_id": bool(user_id),
                            "has_submission_id": bool(submission_id),
                        },
                        default=str,
                        sort_keys=True,
                    )
                )
                continue
            recipient_kind = kinds.get(contributor.wallet_address, "wallet")
            amount = (total * contributor.weight_bps / 10000) if total is not None else Decimal(0)
            reward_metadata: dict[str, Any] = {
                "recipient_kind": recipient_kind,
                "payout_address": contributor.wallet_address,
                "weight_bps": contributor.weight_bps,
                "model_id_uint": mint_request.model_id_uint,
                "eval_id": mint_request.eval_id,
                "mint_request_id": mint_request.message_id,
                "attestation_hash": mint_request.attestation_hash,
                "mint_idempotency_key": mint_request.idempotency_key,
            }
            if status == "pending" and recipient_kind == "wallet":
                reward_metadata["settlement_status"] = "mint_pending"
            if recipient_kind == "escrow":
                # For escrow tranches the on-chain recipient IS the escrow; record it so the
                # releaser (HOK-2271) can release this account's tranche on wallet verification.
                reward_metadata["escrow_address"] = contributor.wallet_address
            if vesting is not None:
                reward_metadata["vesting"] = vesting
            rows.append(
                RewardIngestRow(
                    reward_id=f"{mint_request.idempotency_key}:{user_id}",
                    submission_id=str(submission_id),
                    user_id=str(user_id),
                    model_id=mint_request.model_id,
                    token_address=token_address,
                    amount=amount,
                    status=status,
                    recipient_kind=recipient_kind,
                    reward_metadata=reward_metadata,
                )
            )
        return rows

    def _post_reward_ingest(
        self: AuthServiceNotifier,
        *,
        row: RewardIngestRow,
        status: str,
    ) -> tuple[bool, str | None]:
        """POST a single reward ingest row with retries; 409 == idempotent success."""
        headers = {
            "Authorization": f"Bearer {self.internal_token}",
            "Content-Type": "application/json",
            "Idempotency-Key": row.reward_id,
        }
        url = f"{self.auth_service_url}{self.reward_ingest_path}"
        body = row.model_dump(mode="json", by_alias=True)
        error_message: str | None = None

        for attempt in range(1, self.retry_attempts + 1):
            if attempt > 1:
                time.sleep(2 ** (attempt - 2))
            try:
                response = httpx.post(url, json=body, headers=headers, timeout=self.timeout)
            except httpx.HTTPError as exc:
                error_message = str(exc)
                LOGGER.warning(
                    json.dumps(
                        {
                            "event": "auth_reward_ingest_request_error",
                            "reward_id": row.reward_id,
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
                            "event": "auth_reward_ingest_unexpected_error",
                            "reward_id": row.reward_id,
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
                            "event": "auth_reward_ingest_succeeded",
                            "reward_id": row.reward_id,
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
                            "event": "auth_reward_ingest_conflict",
                            "reward_id": row.reward_id,
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
                            "event": "auth_reward_ingest_retryable_response",
                            "reward_id": row.reward_id,
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
                        "event": "auth_reward_ingest_failed",
                        "reward_id": row.reward_id,
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
                    "event": "auth_reward_ingest_retry_exhausted",
                    "reward_id": row.reward_id,
                    "status": status,
                    "attempts": self.retry_attempts,
                    "error": error_message,
                },
                default=str,
                sort_keys=True,
            )
        )
        return False, error_message

    def _build_direct_mint_settlement_rows(
        self: AuthServiceNotifier,
        *,
        mint_request: MintRequest,
        mint_result: TokenMintResult,
        reward_tokens: float,
        token_address: str | None,
        token_symbol: str | None,
        deployment: dict[str, Any] | None,
        recipient_kinds: dict[str, str],
    ) -> list[DirectMintSettlementPayload]:
        if mint_result.status != "success":
            raise ValueError("direct mint settlement requires a successful mint result")
        tx_hash = (mint_result.tx_hash or "").strip()
        if not tx_hash:
            raise ValueError("direct mint settlement requires tx_hash from the mint receipt")
        resolved_token_address = (
            token_address or mint_result.token_address or ""
        ).strip() or _metadata_string(mint_result.deployment, "token_address")
        if not resolved_token_address:
            raise ValueError("direct mint settlement requires token_address")
        resolved_token_symbol = (token_symbol or mint_result.token_symbol or "").strip()
        if not resolved_token_symbol:
            raise ValueError("direct mint settlement requires token_symbol")

        total = Decimal(str(reward_tokens))
        rows: list[DirectMintSettlementPayload] = []
        for contributor in mint_request.contributors:
            if recipient_kinds.get(contributor.wallet_address, "wallet") != "wallet":
                continue
            user_id = contributor.contributor_id
            submission_id = contributor.submission_id
            if not user_id or not submission_id:
                LOGGER.warning(
                    json.dumps(
                        {
                            "event": "auth_direct_mint_settlement_skipped_missing_identity",
                            "mint_idempotency_key": mint_request.idempotency_key,
                            "wallet_address": contributor.wallet_address,
                            "has_user_id": bool(user_id),
                            "has_submission_id": bool(submission_id),
                        },
                        default=str,
                        sort_keys=True,
                    )
                )
                continue

            amount = total * contributor.weight_bps / 10000
            immediate_amount, vested_amount = _split_vesting_amounts(
                amount=amount,
                total_reward=total,
                mint_result=mint_result,
            )
            rows.append(
                DirectMintSettlementPayload(
                    reward_id=f"{mint_request.idempotency_key}:{user_id}",
                    submission_id=str(submission_id),
                    user_id=str(user_id),
                    model_id=mint_request.model_id,
                    token_symbol=resolved_token_symbol,
                    token_address=resolved_token_address,
                    amount=amount,
                    recipient_address=mint_result.recipient_address or contributor.wallet_address,
                    claim_tx_hash=tx_hash,
                    claim_reference=f"{tx_hash}:{mint_request.idempotency_key}:{user_id}",
                    claimed_at=(
                        mint_result.claimed_at.isoformat()
                        if mint_result.claimed_at is not None
                        else mint_result.timestamp.isoformat()
                    ),
                    immediate_amount=immediate_amount,
                    vested_amount=vested_amount,
                    vesting_schedule=_build_vesting_schedule(
                        contributor_address=contributor.wallet_address,
                        token_address=resolved_token_address,
                        total_vested_amount=vested_amount,
                        mint_result=mint_result,
                    ),
                    deployment=deployment or mint_result.deployment,
                    reward_metadata={
                        "source": "pipeline_direct_mint_settlement",
                        "mint_request_id": mint_request.message_id,
                        "mint_idempotency_key": mint_request.idempotency_key,
                        "external_submission_id": str(submission_id),
                        "model_id_uint": mint_request.model_id_uint,
                        "eval_id": mint_request.eval_id,
                        "attestation_hash": mint_request.attestation_hash,
                        "recipient_wallet": contributor.wallet_address,
                        "weight_bps": contributor.weight_bps,
                    },
                )
            )
        return rows

    def _post_direct_mint_settlement(
        self: AuthServiceNotifier,
        *,
        row: DirectMintSettlementPayload,
    ) -> tuple[bool, str | None]:
        headers = {
            "Authorization": f"Bearer {self.internal_token}",
            "Content-Type": "application/json",
            "Idempotency-Key": row.reward_id,
        }
        url = f"{self.auth_service_url}{self.direct_mint_settlement_path}"
        body = row.model_dump(mode="json", by_alias=True, exclude_none=True)
        error_message: str | None = None

        for attempt in range(1, self.retry_attempts + 1):
            if attempt > 1:
                time.sleep(2 ** (attempt - 2))
            try:
                response = httpx.post(url, json=body, headers=headers, timeout=self.timeout)
            except httpx.HTTPError as exc:
                error_message = str(exc)
                LOGGER.warning(
                    json.dumps(
                        {
                            "event": "auth_direct_mint_settlement_request_error",
                            "reward_id": row.reward_id,
                            "attempt": attempt,
                            "max_attempts": self.retry_attempts,
                            "error": error_message,
                        },
                        default=str,
                        sort_keys=True,
                    )
                )
                continue

            if response.status_code in {200, 201}:
                LOGGER.info(
                    json.dumps(
                        {
                            "event": "auth_direct_mint_settlement_succeeded",
                            "reward_id": row.reward_id,
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
                            "event": "auth_direct_mint_settlement_conflict",
                            "reward_id": row.reward_id,
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
                            "event": "auth_direct_mint_settlement_retryable_response",
                            "reward_id": row.reward_id,
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
                        "event": "auth_direct_mint_settlement_failed",
                        "reward_id": row.reward_id,
                        "status_code": response.status_code,
                        "response_body": response.text[:500],
                    },
                    default=str,
                    sort_keys=True,
                )
            )
            return False, error_message

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
        api_key_id: str | None = None,  # noqa: ARG002 - accepted for caller/cache compatibility
        service_id: str | None = None,  # noqa: ARG002 - resolver is keyed by user_id only
    ) -> WalletResolution:
        """Resolve an account's verified payout wallet via auth-service (HOK-2243/2244).

        Calls ``GET /api/v1/internal/users/{user_id}/wallet`` with the shared internal
        bearer token. ``api_key_id``/``service_id`` are accepted for caller compatibility
        but unused: the deployed resolver is keyed solely by ``user_id`` (auth handles the
        api_key->user_id seam internally). See ``WalletResolution`` for how callers branch.
        """
        unresolved = WalletResolution(
            resolved=False, has_verified_wallet=False, wallet_address=None
        )
        if not user_id:
            return unresolved
        if self.dry_run:
            LOGGER.info(
                json.dumps(
                    {"event": "auth_wallet_resolution_dry_run", "user_id": user_id},
                    default=str,
                    sort_keys=True,
                )
            )
            return unresolved

        headers = {"Authorization": f"Bearer {self.internal_token}"}
        path = self.wallet_resolution_path.format(user_id=quote(str(user_id), safe=""))
        url = f"{self.auth_service_url}{path}"
        for attempt in range(1, self.retry_attempts + 1):
            if attempt > 1:
                time.sleep(2 ** (attempt - 2))
            try:
                response = httpx.get(url, headers=headers, timeout=self.timeout)
            except httpx.HTTPError:
                continue
            except Exception:  # noqa: BLE001
                return unresolved

            if response.status_code == 200:
                try:
                    body = response.json()
                except Exception:  # noqa: BLE001
                    return unresolved
                wallet = body.get("wallet_address")
                if wallet is not None and not isinstance(wallet, str):
                    return unresolved
                return WalletResolution(
                    resolved=True,
                    has_verified_wallet=bool(body.get("has_verified_wallet")),
                    wallet_address=wallet,
                )

            if response.status_code >= 500:
                continue
            # 401/403 (auth/token), 404 (unknown user), 422 (bad id): no definitive answer.
            return unresolved
        return unresolved

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

    @staticmethod
    def _build_processed_body(payload: LifecycleUpdatePayload) -> dict[str, Any]:
        """Remap a lifecycle payload to auth's ProcessedDataSubmissionUpdateRequest (HOK-2256).

        Auth's processing endpoint uses camelCase aliases, forbids extra fields, and treats every
        present key as a field-to-write (``model_fields_set``). So we OMIT None-valued optionals
        rather than clobber stored ledger fields with null. ``submissionId`` carries the pipeline
        external submission id (auth joins on ``external_submission_id``); ``status`` values line
        up 1:1 with auth's ``SubmissionStatus``. ``evaluation_run_id`` (always) and, for
        rejected/excluded outcomes, the ``reason_code`` ride along in ``metadata`` since auth has
        no first-class field for either.
        """
        body: dict[str, Any] = {
            "submissionId": payload.submission_id,
            "status": payload.status,
        }
        if payload.row_counts is not None:
            body["acceptedRowCount"] = payload.row_counts.accepted
            body["rejectedRowCount"] = payload.row_counts.rejected
        if payload.dataset_version is not None:
            body["datasetVersion"] = payload.dataset_version
        if payload.training_run_id is not None:
            body["trainingRunId"] = payload.training_run_id
        if payload.estimated_reward_at is not None:
            body["expectedRewardAt"] = payload.estimated_reward_at.isoformat()

        metadata: dict[str, Any] = {}
        if payload.evaluation_run_id is not None:
            metadata["evaluation_run_id"] = payload.evaluation_run_id
        if payload.status in {"rejected", "excluded"} and payload.reason_code is not None:
            metadata["reason_code"] = payload.reason_code.value
        if metadata:
            body["metadata"] = metadata
        return body

    def notify_lifecycle_update(
        self: AuthServiceNotifier,
        payload: LifecycleUpdatePayload,
    ) -> tuple[bool, str | None]:
        """Post a contribution lifecycle update to auth-service."""
        body = self._build_processed_body(payload)
        if self.dry_run:
            LOGGER.info(
                json.dumps(
                    {
                        "event": "auth_lifecycle_notification_dry_run",
                        "submission_id": payload.submission_id,
                        "payload": body,
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
                    json=body,
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
