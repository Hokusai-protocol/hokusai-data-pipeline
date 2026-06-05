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

    wallet_totals: dict[str, dict[str, Any]] = {}
    skipped_null_wallet_shares = 0.0

    for _, row in eligible.iterrows():
        per_wallet, skipped_share = _row_wallet_shares(
            row_id=str(row[ROW_ID_COLUMN]),
            encoded_neighbor_provenance=row[NEIGHBOR_PROVENANCE_COLUMN],
        )
        skipped_null_wallet_shares += skipped_share
        for wallet, wallet_share in per_wallet.items():
            aggregate = wallet_totals.setdefault(
                wallet,
                {
                    "wallet": wallet,
                    "submission_ids": set(),
                    "rows_credited": set(),
                    "raw_score": 0.0,
                },
            )
            aggregate["submission_ids"].update(wallet_share["submission_ids"])
            aggregate["rows_credited"].add(str(row[ROW_ID_COLUMN]))
            aggregate["raw_score"] += wallet_share["share"]

    if skipped_null_wallet_shares:
        logger.info("Skipped %.6f null-wallet attribution share(s)", skipped_null_wallet_shares)

    contributors = _finalize_contributors(wallet_totals)
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


def _row_wallet_shares(
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

    per_wallet: dict[str, dict[str, Any]] = {}
    skipped_null_wallet_shares = 0.0
    for neighbor, share in zip(neighbors, normalized, strict=True):
        wallet = neighbor.get("wallet")
        if wallet is None:
            skipped_null_wallet_shares += share
            continue
        wallet_key = str(wallet)
        aggregate = per_wallet.setdefault(
            wallet_key,
            {"submission_ids": set(), "share": 0.0},
        )
        aggregate["share"] += share
        submission_id = neighbor.get("submission_id")
        if submission_id:
            aggregate["submission_ids"].add(str(submission_id))
    return per_wallet, skipped_null_wallet_shares


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


def _finalize_contributors(wallet_totals: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not wallet_totals:
        return []

    ordered_wallets = sorted(wallet_totals)
    total_raw = sum(float(wallet_totals[wallet]["raw_score"]) for wallet in ordered_wallets)
    exact_bps = {
        wallet: (float(wallet_totals[wallet]["raw_score"]) / total_raw) * 10000.0
        for wallet in ordered_wallets
    }
    floor_bps = {wallet: math.floor(value) for wallet, value in exact_bps.items()}
    deficit = 10000 - sum(floor_bps.values())
    if deficit > 0:
        remainders = sorted(
            ordered_wallets,
            key=lambda wallet: (-(exact_bps[wallet] - floor_bps[wallet]), wallet),
        )
        for wallet in remainders[:deficit]:
            floor_bps[wallet] += 1

    contributors = [
        {
            "wallet": wallet,
            "submission_ids": sorted(wallet_totals[wallet]["submission_ids"]),
            "rows_credited": len(wallet_totals[wallet]["rows_credited"]),
            "raw_score": round(float(wallet_totals[wallet]["raw_score"]), 12),
            "weight_bps": int(floor_bps[wallet]),
        }
        for wallet in ordered_wallets
    ]
    contributors.sort(key=lambda item: (-item["weight_bps"], item["wallet"]))
    return contributors
