#!/usr/bin/env python3
"""Backfill auth direct-mint settlements from signed mint requests and tx receipts."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api.schemas.token_mint import TokenMintResult  # noqa: E402
from src.api.services.auth_service_notifier import AuthServiceNotifier  # noqa: E402
from src.events.schemas import MintRequest  # noqa: E402

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mint-request", required=True, help="Signed MintRequest JSON artifact.")
    parser.add_argument("--receipt", required=True, help="On-chain tx receipt/log JSON artifact.")
    parser.add_argument("--reward-tokens", required=True, help="Total reward amount for the mint.")
    parser.add_argument("--token-symbol", required=True, help="Historical token symbol.")
    parser.add_argument(
        "--token-address",
        default=None,
        help="Historical token address. If omitted, read from receipt metadata/logs.",
    )
    parser.add_argument(
        "--deployment",
        default=None,
        help="Optional deployment metadata JSON file with historical contract addresses.",
    )
    parser.add_argument(
        "--pending-reward-rows",
        default=None,
        help="Optional auth reward rows JSON to validate before settlement backfill.",
    )
    parser.add_argument(
        "--auth-service-url",
        default=os.getenv("HOKUSAI_AUTH_SERVICE_URL", "https://auth.hokus.ai"),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Post to auth. Without this flag the command logs a dry run.",
    )
    return parser.parse_args()


def load_json(path: str | Path) -> Any:
    """Load a JSON document from disk."""
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_mint_request(path: str | Path) -> MintRequest:
    """Load and validate a MintRequest from a signed artifact wrapper or raw payload."""
    payload = load_json(path)
    candidate = _find_mint_request_payload(payload)
    return MintRequest.model_validate(candidate)


def validate_no_ambiguous_pending_wallet_rows(rows_payload: Any) -> None:
    """Reject pending wallet rewards that lack settlement or release metadata."""
    rows = rows_payload.get("items") if isinstance(rows_payload, dict) else rows_payload
    if not isinstance(rows, list):
        raise ValueError("pending reward rows must be a JSON array or object with items[]")
    ambiguous: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        metadata = row.get("metadata") or row.get("reward_metadata") or {}
        settlement = metadata.get("settlement") if isinstance(metadata, dict) else None
        if (
            row.get("status") == "pending"
            and row.get("recipient_kind", "wallet") == "wallet"
            and not row.get("claim_url")
            and not row.get("claim_tx_hash")
            and not (
                isinstance(metadata, dict) and metadata.get("settlement_status") == "mint_pending"
            )
            and not (isinstance(settlement, dict) and settlement.get("type"))
        ):
            ambiguous.append(str(row.get("reward_id") or row.get("id") or "<unknown>"))
    if ambiguous:
        raise ValueError(
            "ambiguous pending wallet rewards without settlement metadata: " + ", ".join(ambiguous)
        )


def recipient_kinds_from_mint_request(mint_request: MintRequest) -> dict[str, str]:
    """Return mint-time routing by on-chain recipient address from a signed MintRequest."""
    return {
        contributor.wallet_address: contributor.recipient_kind
        for contributor in mint_request.contributors
    }


def build_mint_result_from_receipt(
    receipt: dict[str, Any],
    *,
    token_symbol: str,
    token_address: str | None,
    deployment: dict[str, Any] | None,
) -> TokenMintResult:
    """Convert a successful transaction receipt/log artifact into a mint result."""
    if not _receipt_succeeded(receipt):
        raise ValueError("receipt status is not successful")

    vesting = _extract_vesting(receipt)
    resolved_token_address = (
        token_address
        or _string(receipt.get("token_address"))
        or _string(receipt.get("tokenAddress"))
        or _string(vesting.get("token_address"))
        or _string(vesting.get("tokenAddress"))
        or _string((deployment or {}).get("token_address"))
        or _string((deployment or {}).get("tokenAddress"))
    )
    if not resolved_token_address:
        raise ValueError("token address missing from receipt; pass --token-address")

    payload: dict[str, Any] = {
        "status": "success",
        "audit_ref": _string(receipt.get("transactionHash"))
        or _string(receipt.get("transaction_hash"))
        or _string(receipt.get("tx_hash"))
        or "receipt-backfill",
        "timestamp": _receipt_timestamp(receipt),
        "tx_hash": _tx_hash(receipt),
        "token_address": resolved_token_address,
        "token_symbol": token_symbol,
        "recipient_address": _string(receipt.get("recipient_address"))
        or _string(receipt.get("recipientAddress")),
        "claimed_at": _receipt_timestamp(receipt),
        "deployment": deployment or receipt.get("deployment"),
    }
    if vesting:
        payload["vesting"] = _normalize_vesting_keys(vesting)
    return TokenMintResult.model_validate(payload)


def main() -> int:
    """Run the direct-mint settlement backfill command."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    args = parse_args()

    if args.pending_reward_rows:
        validate_no_ambiguous_pending_wallet_rows(load_json(args.pending_reward_rows))

    mint_request = load_mint_request(args.mint_request)
    receipt = load_json(args.receipt)
    if not isinstance(receipt, dict):
        raise ValueError("receipt must be a JSON object")
    deployment = load_json(args.deployment) if args.deployment else None
    if deployment is not None and not isinstance(deployment, dict):
        raise ValueError("deployment metadata must be a JSON object")

    mint_result = build_mint_result_from_receipt(
        receipt,
        token_symbol=args.token_symbol,
        token_address=args.token_address,
        deployment=deployment,
    )
    notifier = AuthServiceNotifier(
        auth_service_url=args.auth_service_url,
        internal_token=os.getenv("HOKUSAI_AUTH_INTERNAL_TOKEN", ""),
        dry_run=not args.execute,
    )
    delivered, error = notifier.notify_direct_mint_settlement(
        mint_request=mint_request,
        mint_result=mint_result,
        reward_tokens=float(args.reward_tokens),
        token_address=mint_result.token_address,
        token_symbol=args.token_symbol,
        deployment=deployment,
        recipient_kinds=recipient_kinds_from_mint_request(mint_request),
    )
    if not delivered:
        LOGGER.error("direct mint settlement backfill failed: %s", error)
        return 1
    LOGGER.info(
        "Direct mint settlement backfill %s: idempotency_key=%s tx_hash=%s",
        "executed" if args.execute else "dry-run",
        mint_request.idempotency_key,
        mint_result.tx_hash,
    )
    return 0


def _find_mint_request_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        if payload.get("message_type") == "mint_request":
            return payload
        for key in ("mint_request", "mintRequest", "payload", "message"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                try:
                    return _find_mint_request_payload(nested)
                except ValueError:
                    pass
    raise ValueError("could not locate MintRequest payload")


def _receipt_succeeded(receipt: dict[str, Any]) -> bool:
    status = receipt.get("status")
    if status in (1, "1", "0x1", True, "success", "successful"):
        return True
    return False


def _tx_hash(receipt: dict[str, Any]) -> str:
    value = (
        _string(receipt.get("transactionHash"))
        or _string(receipt.get("transaction_hash"))
        or _string(receipt.get("tx_hash"))
        or _string(receipt.get("hash"))
    )
    if not value:
        raise ValueError("receipt is missing transaction hash")
    return value


def _receipt_timestamp(receipt: dict[str, Any]) -> str:
    value = (
        _string(receipt.get("timestamp"))
        or _string(receipt.get("blockTimestamp"))
        or _string(receipt.get("claimed_at"))
    )
    if value:
        return value
    return datetime.now(timezone.utc).isoformat()


def _extract_vesting(receipt: dict[str, Any]) -> dict[str, Any]:
    direct = receipt.get("vesting") or receipt.get("vesting_schedule")
    if isinstance(direct, dict):
        return dict(direct)
    for log in receipt.get("logs") or []:
        if not isinstance(log, dict):
            continue
        args = log.get("args") if isinstance(log.get("args"), dict) else log
        event_name = _string(log.get("event")) or _string(log.get("name"))
        if event_name and "vesting" not in event_name.lower():
            continue
        if any(key in args for key in ("schedule_id", "scheduleId", "vault_address", "vault")):
            return dict(args)
    return {}


def _normalize_vesting_keys(value: dict[str, Any]) -> dict[str, Any]:
    key_map = {
        "liquidAmount": "liquid_amount",
        "immediate_amount": "liquid_amount",
        "immediateAmount": "liquid_amount",
        "vestedAmount": "vested_amount",
        "vault": "vault_address",
        "vaultAddress": "vault_address",
        "scheduleId": "schedule_id",
        "claimableAmount": "claimable_amount",
        "claimedAmount": "claimed_amount",
        "tokenAddress": "token_address",
        "beneficiary": "beneficiary_address",
        "beneficiaryAddress": "beneficiary_address",
        "startAt": "start_at",
        "endAt": "end_at",
        "durationSeconds": "duration_seconds",
        "cliffSeconds": "cliff_seconds",
    }
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        normalized[key_map.get(key, key)] = item
    return normalized


def _string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


if __name__ == "__main__":
    raise SystemExit(main())
