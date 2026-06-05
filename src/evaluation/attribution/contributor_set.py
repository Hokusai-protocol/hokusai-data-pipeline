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
    """Return deterministic contributor allocations derived from positive attribution lift."""
    _validate_report_header(report, candidate_run_id=candidate_run_id)
    positive_contributors = _filter_positive_contributors(report)

    normalized: list[dict[str, Any]] = []
    raw_scores: dict[str, float] = {}
    for entry in positive_contributors:
        wallet = entry.get("wallet")
        if not isinstance(wallet, str) or not _ETH_ADDRESS_RE.match(wallet):
            raise ContributorDerivationError(f"invalid contributor wallet={wallet!r}")
        wallet = wallet.lower()
        normalized_submission_ids = _normalize_submission_ids(
            wallet=wallet,
            submission_ids=entry.get("submission_ids"),
        )

        raw_score = max(0.0, float(entry["raw_score"]))
        raw_scores[wallet] = raw_score
        normalized.append(
            {
                "wallet": wallet,
                "submission_ids": normalized_submission_ids,
            }
        )

    weight_bps_by_wallet = _largest_remainder_bps(raw_scores)
    total_weight_bps = sum(weight_bps_by_wallet.values())
    if total_weight_bps != 10000:
        raise ContributorDerivationError(
            f"derived contributor weights must sum to 10000; got {total_weight_bps}"
        )

    result = [
        {
            "wallet": entry["wallet"],
            "weight_bps": weight_bps_by_wallet[entry["wallet"]],
            "submission_ids": entry["submission_ids"],
        }
        for entry in normalized
    ]
    result.sort(key=lambda item: item["wallet"])
    return result


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
        raise ContributorDerivationError(
            f"invalid raw_score for wallet={entry.get('wallet')!r}"
        ) from exc


def _normalize_submission_ids(*, wallet: str, submission_ids: Any) -> list[str]:
    if submission_ids is None:
        return []
    if isinstance(submission_ids, list) and all(isinstance(item, str) for item in submission_ids):
        return sorted(submission_ids)
    raise ContributorDerivationError(
        f"invalid submission_ids for wallet={wallet!r}; expected list[str]"
    )


def _largest_remainder_bps(raw_scores: dict[str, float]) -> dict[str, int]:
    ordered_wallets = sorted(raw_scores)
    total_raw = sum(raw_scores.values())
    if total_raw <= 0:
        raise ContributorDerivationError("no positive-lift contributors")
    exact_bps = {wallet: (raw_scores[wallet] / total_raw) * 10000.0 for wallet in ordered_wallets}
    floor_bps = {wallet: math.floor(value) for wallet, value in exact_bps.items()}
    deficit = 10000 - sum(floor_bps.values())
    if deficit > 0:
        remainders = sorted(
            ordered_wallets,
            key=lambda wallet: (-(exact_bps[wallet] - floor_bps[wallet]), wallet),
        )
        for wallet in remainders[:deficit]:
            floor_bps[wallet] += 1
    return floor_bps
