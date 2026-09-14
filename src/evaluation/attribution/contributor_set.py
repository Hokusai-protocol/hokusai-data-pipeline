"""Derive mint-ready contributor sets from attribution reports."""

from __future__ import annotations

import logging
import math
import re
from typing import Any

logger = logging.getLogger(__name__)

_ETH_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_SCHEMA_VERSION = "attribution_report/v1"


class ContributorDerivationError(ValueError):
    """Raised when a contributor set cannot be derived from an attribution report."""


def derive_contributor_set(
    report: dict[str, Any],
    *,
    candidate_run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return deterministic contributor allocations derived from positive attribution lift.

    Each contributor entry is identified by ``account_id`` (the Hokusai account / user_id)
    and/or ``wallet``. Account-centric reports may carry ``account_id`` with no wallet (the
    wallet is resolved at mint, HOK-2244/2245); legacy reports carry only ``wallet``. The
    output preserves whichever identity fields were present, so wallet-only reports are
    unchanged.
    """
    _validate_report_header(report, candidate_run_id=candidate_run_id)
    positive_contributors = _filter_positive_contributors(report)

    normalized: list[dict[str, Any]] = []
    raw_scores: dict[str, float] = {}
    for entry in positive_contributors:
        account_id, wallet = _contributor_identity(entry)
        identity = account_id if account_id is not None else wallet
        normalized_submission_ids = _normalize_submission_ids(
            identity=identity,
            submission_ids=entry.get("submission_ids"),
        )

        raw_score = max(0.0, float(entry["raw_score"]))
        raw_scores[identity] = raw_score
        normalized.append(
            {
                "identity": identity,
                "account_id": account_id,
                "wallet": wallet,
                "submission_ids": normalized_submission_ids,
            }
        )

    weight_bps_by_identity = _largest_remainder_bps(raw_scores)
    total_weight_bps = sum(weight_bps_by_identity.values())
    if total_weight_bps != 10000:
        raise ContributorDerivationError(
            f"derived contributor weights must sum to 10000; got {total_weight_bps}"
        )

    normalized.sort(key=lambda entry: entry["identity"])
    result: list[dict[str, Any]] = []
    for entry in normalized:
        item: dict[str, Any] = {
            "weight_bps": weight_bps_by_identity[entry["identity"]],
            "submission_ids": entry["submission_ids"],
        }
        # Preserve only the identity fields that were present (wallet-only output unchanged).
        if entry["wallet"] is not None:
            item["wallet"] = entry["wallet"]
        if entry["account_id"] is not None:
            item["account_id"] = entry["account_id"]
        result.append(item)
    return result


def _contributor_identity(entry: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (account_id, wallet) for a contributor entry; at least one must be present.

    Validates the wallet format when present and requires a non-empty account_id when
    present. Account-centric entries may omit the wallet (resolved at mint).
    """
    account_id = entry.get("account_id")
    if account_id is not None:
        if not isinstance(account_id, str) or not account_id.strip():
            raise ContributorDerivationError(f"invalid contributor account_id={account_id!r}")
        account_id = account_id.strip()

    wallet = entry.get("wallet")
    if wallet is not None:
        if not isinstance(wallet, str) or not _ETH_ADDRESS_RE.match(wallet):
            raise ContributorDerivationError(f"invalid contributor wallet={wallet!r}")
        wallet = wallet.lower()

    if account_id is None and wallet is None:
        raise ContributorDerivationError("contributor entry must have account_id or wallet")
    return account_id, wallet


def _validate_report_header(
    report: dict[str, Any],
    *,
    candidate_run_id: str | None,
) -> None:
    schema_version = report.get("schema_version")
    if schema_version != _SCHEMA_VERSION:
        raise ContributorDerivationError(
            f"unsupported attribution report schema_version={schema_version!r}"
        )

    report_candidate_run_id = report.get("candidate_run_id")
    if candidate_run_id is not None and report_candidate_run_id != candidate_run_id:
        raise ContributorDerivationError(
            "attribution report candidate_run_id mismatch: "
            f"expected {candidate_run_id!r}, got {report_candidate_run_id!r}"
        )


def _filter_positive_contributors(report: dict[str, Any]) -> list[dict[str, Any]]:
    raw_contributors = report.get("contributors")
    if not isinstance(raw_contributors, list):
        raise ContributorDerivationError("attribution report contributors must be a list")

    positive_contributors: list[dict[str, Any]] = []
    excluded_count = 0
    for entry in raw_contributors:
        raw_score = _coerce_raw_contributor_score(entry)
        if raw_score > 0:
            positive_contributors.append(entry)
        else:
            excluded_count += 1

    if excluded_count:
        logger.info(
            "event=attribution_contributors_filtered excluded=%d total=%d",
            excluded_count,
            len(raw_contributors),
        )

    if not positive_contributors:
        raise ContributorDerivationError("no positive-lift contributors")
    return positive_contributors


def _coerce_raw_contributor_score(entry: Any) -> float:
    if not isinstance(entry, dict):
        raise ContributorDerivationError("attribution report contributor entries must be objects")
    try:
        return float(entry.get("raw_score", 0.0))
    except (TypeError, ValueError) as exc:
        identity = entry.get("account_id") or entry.get("wallet")
        raise ContributorDerivationError(f"invalid raw_score for contributor={identity!r}") from exc


def _normalize_submission_ids(*, identity: str, submission_ids: Any) -> list[str]:
    if submission_ids is None:
        return []
    if isinstance(submission_ids, list) and all(isinstance(item, str) for item in submission_ids):
        return sorted(submission_ids)
    raise ContributorDerivationError(
        f"invalid submission_ids for contributor={identity!r}; expected list[str]"
    )


def _largest_remainder_bps(raw_scores: dict[str, float]) -> dict[str, int]:
    ordered = sorted(raw_scores)
    total_raw = sum(raw_scores.values())
    if total_raw <= 0:
        raise ContributorDerivationError("no positive-lift contributors")
    exact_bps = {key: (raw_scores[key] / total_raw) * 10000.0 for key in ordered}
    floor_bps = {key: math.floor(value) for key, value in exact_bps.items()}
    deficit = 10000 - sum(floor_bps.values())
    if deficit > 0:
        remainders = sorted(
            ordered,
            key=lambda key: (-(exact_bps[key] - floor_bps[key]), key),
        )
        for key in remainders[:deficit]:
            floor_bps[key] += 1
    return floor_bps
