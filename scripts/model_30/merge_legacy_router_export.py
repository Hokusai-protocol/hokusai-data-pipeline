"""Merge a legacy Wavemill router CSV export with freshly derived router rows.

Raw Wavemill evals before 2026-05-11 no longer exist in any repo's
``evals.jsonl``. The only copy of that history is the May 18 router export,
which predates wavemill ``3bbc1f5c`` ("finalize eval success from scores"). That
export carries placeholder ``completed_successfully`` values, so this tool
re-derives them with the Wavemill success policy (``score >= threshold``).

Legacy rows that duplicate a derived row (same second and same planner, coder
and reviewer models) are dropped, so the derived row wins. Rows at or after
``--before`` are excluded.

Example (2026-11 retrain)::

    python scripts/model_30/merge_legacy_router_export.py \
      --legacy .../wavemill/.wavemill/evals/hokusai-router-dataset.csv \
      --derived data/model_30/retrain-2026-11/router-dataset.all.clean.csv \
      --before 2026-11-01 \
      --output data/model_30/retrain-2026-11/router-dataset.union.raw.csv \
      --provenance-output data/model_30/retrain-2026-11/router-dataset.union.provenance.csv \
      --report data/model_30/retrain-2026-11/union-report.json

Run ``clean_router_dataset.py`` on the output before training.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

# Mirrors wavemill shared/lib/eval-success-policy.ts DEFAULT_SUCCESS_THRESHOLD.
DEFAULT_SUCCESS_THRESHOLD = 0.8
ROLE_COLUMNS = ("planner_model", "coder_model", "reviewer_model")


def relabel_success_from_score(
    frame: pd.DataFrame, *, threshold: float = DEFAULT_SUCCESS_THRESHOLD
) -> tuple[pd.DataFrame, int]:
    """Return a copy with ``completed_successfully`` re-derived from ``score``.

    Returns the relabelled frame and the number of rows whose label changed.
    Rows with a missing or non-numeric score become ``false``, matching the
    Wavemill policy for records without a usable signal.
    """
    out = frame.copy()
    score = pd.to_numeric(out["score"], errors="coerce")
    fixed = (score >= threshold).map({True: "true", False: "false"})
    original = out["completed_successfully"].astype(str).str.strip().str.lower()
    changed = int((fixed != original).sum())
    out["completed_successfully"] = fixed
    return out, changed


def _dedupe_key(frame: pd.DataFrame) -> pd.Series:
    key = frame["timestamp"].astype(str).str[:19]
    for column in ROLE_COLUMNS:
        key = key + "|" + frame[column].astype(str)
    return key


def merge_router_exports(
    legacy: pd.DataFrame,
    derived: pd.DataFrame,
    *,
    before: str | None = None,
    threshold: float = DEFAULT_SUCCESS_THRESHOLD,
    legacy_source: str = "legacy_router_csv",
    derived_source: str = "derived_evals_jsonl",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Merge legacy and derived router rows, sorted by timestamp.

    The returned frame has a ``provenance_source`` column; drop it before
    writing a training CSV.
    """
    if list(legacy.columns) != list(derived.columns):
        missing = sorted(set(legacy.columns) ^ set(derived.columns))
        raise ValueError(f"legacy and derived exports have different columns: {missing}")

    legacy, relabelled = relabel_success_from_score(legacy, threshold=threshold)
    duplicate = _dedupe_key(legacy).isin(set(_dedupe_key(derived)))
    legacy = legacy[~duplicate].assign(provenance_source=legacy_source)
    derived = derived.assign(provenance_source=derived_source)

    merged = pd.concat([legacy, derived], ignore_index=True)
    merged = merged.sort_values("timestamp", kind="stable").reset_index(drop=True)
    if before:
        merged = merged[merged["timestamp"].astype(str) < before].reset_index(drop=True)

    report = {
        "legacy_rows_in": int(len(legacy) + duplicate.sum()),
        "derived_rows_in": int(len(derived)),
        "legacy_success_relabelled": relabelled,
        "legacy_duplicates_dropped": int(duplicate.sum()),
        "success_threshold": threshold,
        "before": before,
        "merged_rows": int(len(merged)),
        "by_month": merged["timestamp"].astype(str).str[:7].value_counts().sort_index().to_dict(),
        "by_source": merged["provenance_source"].value_counts().to_dict(),
    }
    return merged, report


def _read(path: str) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--legacy", required=True, help="Legacy router CSV export.")
    parser.add_argument("--derived", required=True, help="Clean CSV from the corpus collector.")
    parser.add_argument("--output", required=True, help="Merged router CSV (uncleaned).")
    parser.add_argument("--provenance-output", help="Optional run_id_hash/timestamp/source CSV.")
    parser.add_argument("--report", help="Optional JSON report path.")
    parser.add_argument("--before", help="Exclusive ISO timestamp cutoff, e.g. 2026-11-01.")
    parser.add_argument("--success-threshold", type=float, default=DEFAULT_SUCCESS_THRESHOLD)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    args = build_parser().parse_args(argv)
    merged, report = merge_router_exports(
        _read(args.legacy),
        _read(args.derived),
        before=args.before,
        threshold=args.success_threshold,
        legacy_source=f"legacy:{Path(args.legacy).name}",
        derived_source=f"derived:{Path(args.derived).name}",
    )
    merged.drop(columns=["provenance_source"]).to_csv(args.output, index=False)
    if args.provenance_output:
        merged[["run_id_hash", "timestamp", "provenance_source"]].to_csv(
            args.provenance_output, index=False
        )
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
