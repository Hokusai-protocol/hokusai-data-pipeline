"""Build an account-centric attribution report from eval per-row frames + the training manifest.

The router emits neighbor provenance as ``training_row_index`` only (no identity coupling at
serving time). This module resolves each neighbor's contributing identity by mapping that index
to the training manifest block that produced it (HOK-2245), then runs the account-aware
attribution (:func:`neighbor_provenance.attribute`). It is the pure producer logic; the I/O
wiring (read per-row parquet, load the manifest artifact, upload report.json, set the
``hokusai.attribution_report_artifact_uri`` tag) layers on top.
"""

from __future__ import annotations

import bisect
import json
import math
from typing import Any

import pandas as pd

from src.evaluation.attribution.neighbor_provenance import NEIGHBOR_PROVENANCE_COLUMN, attribute

# Identity fields copied from a manifest block onto each neighbor it produced.
_BLOCK_IDENTITY_FIELDS = ("account_id", "wallet", "submission_id")


def build_report(
    baseline_per_row: pd.DataFrame,
    candidate_per_row: pd.DataFrame,
    *,
    manifest_blocks: list[dict[str, Any]],
    model_id: str,
    baseline_run_id: str,
    candidate_run_id: str,
    created_at: str,
) -> dict[str, Any]:
    """Enrich the candidate's neighbor provenance with manifest identity, then attribute."""
    enriched_candidate = enrich_neighbor_provenance(candidate_per_row, manifest_blocks)
    return attribute(
        baseline_per_row,
        enriched_candidate,
        model_id=model_id,
        baseline_run_id=baseline_run_id,
        candidate_run_id=candidate_run_id,
        created_at=created_at,
    )


def enrich_neighbor_provenance(
    candidate_per_row: pd.DataFrame,
    manifest_blocks: list[dict[str, Any]],
) -> pd.DataFrame:
    """Return a copy of the candidate frame with each neighbor tagged from its manifest block.

    A neighbor's ``training_row_index`` is mapped to the manifest block whose
    ``[row_start, row_end]`` range contains it; that block's account_id / wallet / submission_id
    (whichever are present) are copied onto the neighbor. Neighbors whose index matches no block
    are left unchanged (and get dropped downstream as having no identity).
    """
    if NEIGHBOR_PROVENANCE_COLUMN not in candidate_per_row.columns:
        return candidate_per_row
    starts, blocks = _index_blocks(manifest_blocks)

    def _enrich_cell(encoded: Any) -> Any:
        neighbors = _decode(encoded)
        if neighbors is None:
            return encoded
        enriched: list[dict[str, Any]] = []
        for neighbor in neighbors:
            item = dict(neighbor)
            raw_index = item.get("training_row_index")
            block = _block_for_row(starts, blocks, raw_index)
            if block is not None:
                for field in _BLOCK_IDENTITY_FIELDS:
                    value = block.get(field)
                    if value is not None:
                        item[field] = value
            enriched.append(item)
        return json.dumps(enriched, sort_keys=True, separators=(",", ":"))

    out = candidate_per_row.copy()
    out[NEIGHBOR_PROVENANCE_COLUMN] = out[NEIGHBOR_PROVENANCE_COLUMN].map(_enrich_cell)
    return out


def _index_blocks(
    manifest_blocks: list[dict[str, Any]],
) -> tuple[list[int], list[dict[str, Any]]]:
    blocks = sorted(manifest_blocks, key=lambda block: int(block["row_start"]))
    starts = [int(block["row_start"]) for block in blocks]
    return starts, blocks


def _block_for_row(
    starts: list[int],
    blocks: list[dict[str, Any]],
    raw_index: Any,
) -> dict[str, Any] | None:
    if raw_index is None:
        return None
    try:
        row_index = int(raw_index)
    except (TypeError, ValueError):
        return None
    # Rightmost block whose row_start <= row_index, then confirm it contains the index.
    pos = bisect.bisect_right(starts, row_index) - 1
    if pos < 0:
        return None
    block = blocks[pos]
    if int(block["row_start"]) <= row_index <= int(block["row_end"]):
        return block
    return None


def _decode(encoded: Any) -> list[dict[str, Any]] | None:
    if encoded is None or (isinstance(encoded, float) and math.isnan(encoded)):
        return None
    decoded = json.loads(encoded) if isinstance(encoded, str) else encoded
    if not isinstance(decoded, list):
        return None
    return [dict(item) for item in decoded]
