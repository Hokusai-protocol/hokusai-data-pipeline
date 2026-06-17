"""Attribution for Model 30 using emitted k-NN neighbor provenance."""

from __future__ import annotations

import json
import logging
import math
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

OUTCOME_COLUMN = "completed_successfully"
ROW_ID_COLUMN = "row_id"
NEIGHBOR_PROVENANCE_COLUMN = "neighbor_provenance"


def attribute(
    baseline_per_row: pd.DataFrame,
    candidate_per_row: pd.DataFrame,
    *,
    model_id: str,
    baseline_run_id: str,
    candidate_run_id: str,
    created_at: str,
) -> dict[str, Any]:
    """Build a deterministic attribution report from improved eval rows."""
    _require_columns(baseline_per_row, "baseline", (ROW_ID_COLUMN, OUTCOME_COLUMN))
    _require_columns(
        candidate_per_row,
        "candidate",
        (ROW_ID_COLUMN, OUTCOME_COLUMN, NEIGHBOR_PROVENANCE_COLUMN),
    )

    joined = baseline_per_row[[ROW_ID_COLUMN, OUTCOME_COLUMN]].merge(
        candidate_per_row[[ROW_ID_COLUMN, OUTCOME_COLUMN, NEIGHBOR_PROVENANCE_COLUMN]],
        on=ROW_ID_COLUMN,
        how="outer",
        suffixes=("_baseline", "_candidate"),
        indicator=True,
    )
    candidate_only_count = int((joined["_merge"] == "right_only").sum())
    if candidate_only_count:
        logger.info("Excluding %d candidate-only row(s) from attribution", candidate_only_count)

    eligible = joined[
        (joined["_merge"] == "both")
        & (joined[f"{OUTCOME_COLUMN}_baseline"] == False)  # noqa: E712
        & (joined[f"{OUTCOME_COLUMN}_candidate"] == True)  # noqa: E712
    ]

    identity_totals: dict[str, dict[str, Any]] = {}
    skipped_no_identity_shares = 0.0

    for _, row in eligible.iterrows():
        per_identity, skipped_share = _row_identity_shares(
            row_id=str(row[ROW_ID_COLUMN]),
            encoded_neighbor_provenance=row[NEIGHBOR_PROVENANCE_COLUMN],
        )
        skipped_no_identity_shares += skipped_share
        for identity, identity_share in per_identity.items():
            aggregate = identity_totals.setdefault(
                identity,
                {
                    "account_id": identity_share["account_id"],
                    "wallet": identity_share["wallet"],
                    "submission_ids": set(),
                    "rows_credited": set(),
                    "raw_score": 0.0,
                },
            )
            # Backfill the other identity field if a later slot supplies one the first lacked.
            if aggregate["wallet"] is None and identity_share["wallet"] is not None:
                aggregate["wallet"] = identity_share["wallet"]
            if aggregate["account_id"] is None and identity_share["account_id"] is not None:
                aggregate["account_id"] = identity_share["account_id"]
            aggregate["submission_ids"].update(identity_share["submission_ids"])
            aggregate["rows_credited"].add(str(row[ROW_ID_COLUMN]))
            aggregate["raw_score"] += identity_share["share"]

    if skipped_no_identity_shares:
        logger.info(
            "Skipped %.6f attribution share(s) with no contributor identity",
            skipped_no_identity_shares,
        )

    contributors = _finalize_contributors(identity_totals)
    return {
        "schema_version": "attribution_report/v1",
        "model_id": model_id,
        "method": "neighbor_provenance",
        "baseline_run_id": baseline_run_id,
        "candidate_run_id": candidate_run_id,
        "created_at": created_at,
        "total_rows_evaluated": int(len(baseline_per_row)),
        "rows_improved": int(len(eligible)),
        "contributors": contributors,
        "weight_bps_total": int(sum(item["weight_bps"] for item in contributors)),
        "method_details": {"weight_kind": "knn_similarity"},
    }


def _require_columns(
    frame: pd.DataFrame,
    frame_name: str,
    required: tuple[str, ...],
) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"{frame_name} per-row frame missing required columns: {missing}")


def _row_identity_shares(
    *,
    row_id: str,
    encoded_neighbor_provenance: Any,
) -> tuple[dict[str, dict[str, Any]], float]:
    neighbors = _decode_neighbor_provenance(encoded_neighbor_provenance, row_id=row_id)
    if not neighbors:
        return {}, 0.0

    weights = [max(float(neighbor.get("weight", 0.0)), 0.0) for neighbor in neighbors]
    total_weight = sum(weights)
    if total_weight <= 0:
        normalized = [1.0 / len(neighbors)] * len(neighbors)
    else:
        normalized = [weight / total_weight for weight in weights]

    per_identity: dict[str, dict[str, Any]] = {}
    skipped_no_identity_shares = 0.0
    for neighbor, share in zip(neighbors, normalized, strict=True):
        if share <= 0:
            continue
        account_id = neighbor.get("account_id")
        wallet = neighbor.get("wallet")
        # Identity is the account (preferred) or the wallet; account-centric provenance may
        # omit the wallet (resolved at mint). Skip only when neither is present.
        identity = account_id if account_id is not None else wallet
        if identity is None:
            skipped_no_identity_shares += share
            continue
        identity_key = str(identity)
        aggregate = per_identity.setdefault(
            identity_key,
            {"account_id": account_id, "wallet": wallet, "submission_ids": set(), "share": 0.0},
        )
        aggregate["share"] += share
        submission_id = neighbor.get("submission_id")
        if submission_id:
            aggregate["submission_ids"].add(str(submission_id))
    return per_identity, skipped_no_identity_shares


def _decode_neighbor_provenance(
    encoded_neighbor_provenance: Any,
    *,
    row_id: str,
) -> list[dict[str, Any]]:
    if encoded_neighbor_provenance is None or (
        isinstance(encoded_neighbor_provenance, float) and math.isnan(encoded_neighbor_provenance)
    ):
        logger.info("neighbor_provenance missing for row_id=%s; treating as empty", row_id)
        return []
    if isinstance(encoded_neighbor_provenance, str):
        decoded = json.loads(encoded_neighbor_provenance)
    else:
        decoded = encoded_neighbor_provenance
    if not isinstance(decoded, list):
        raise ValueError(f"neighbor_provenance must be a list for row_id={row_id}")
    return [dict(item) for item in decoded]


def _finalize_contributors(identity_totals: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not identity_totals:
        return []

    ordered = sorted(identity_totals)
    total_raw = sum(float(identity_totals[i]["raw_score"]) for i in ordered)
    if total_raw <= 0:
        return []
    exact_bps = {i: (float(identity_totals[i]["raw_score"]) / total_raw) * 10000.0 for i in ordered}
    floor_bps = {i: math.floor(value) for i, value in exact_bps.items()}
    deficit = 10000 - sum(floor_bps.values())
    if deficit > 0:
        remainders = sorted(
            ordered,
            key=lambda i: (-(exact_bps[i] - floor_bps[i]), i),
        )
        for i in remainders[:deficit]:
            floor_bps[i] += 1

    contributors: list[tuple[str, dict[str, Any]]] = []
    for i in ordered:
        totals = identity_totals[i]
        item: dict[str, Any] = {
            "submission_ids": sorted(totals["submission_ids"]),
            "rows_credited": len(totals["rows_credited"]),
            "raw_score": round(float(totals["raw_score"]), 12),
            "weight_bps": int(floor_bps[i]),
        }
        # Preserve only the identity fields present (wallet-only output unchanged).
        if totals["wallet"] is not None:
            item["wallet"] = totals["wallet"]
        if totals["account_id"] is not None:
            item["account_id"] = totals["account_id"]
        contributors.append((i, item))

    contributors.sort(key=lambda pair: (-pair[1]["weight_bps"], pair[0]))
    return [item for _, item in contributors]
