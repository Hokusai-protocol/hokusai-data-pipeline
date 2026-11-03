"""Temporal train/holdout split for Model 30 router datasets.

``split_router_benchmark.py`` makes a random grouped split. When the task mix
drifts over time (as it did in Sep–Oct 2026), a random split hides that drift.
This tool trains on everything before ``--cutoff`` and holds out
``[--cutoff, --end)``. It reuses the splitter's benchmark-validity rules, so
holdout rows that the evaluator would reject are written to a quarantine file.

Challenge pairs (rows sharing ``challenge_pair_hash``) are kept on one side,
placed by the pair's earliest timestamp.

Example::

    python scripts/model_30/temporal_split_router_benchmark.py \
      --input data/model_30/retrain-2026-11/router-dataset.union.clean.csv \
      --cutoff 2026-10-01 --end 2026-11-01 \
      --train-output data/model_30/retrain-2026-11/train.csv \
      --holdout-output data/model_30/retrain-2026-11/holdout-oct.csv \
      --quarantine-output data/model_30/retrain-2026-11/holdout-oct.quarantine.csv \
      --report data/model_30/retrain-2026-11/split-report.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.model_30.split_router_benchmark import _quarantine_reason  # noqa: E402


def _group_id(row: dict[str, str]) -> str:
    return (row.get("challenge_pair_hash") or "").strip() or row.get("run_id_hash") or ""


def temporal_split(
    rows: list[dict[str, str]], *, cutoff: str, end: str | None = None
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    """Split rows into (train, holdout, quarantined_holdout, report)."""
    group_start: dict[str, str] = {}
    for row in rows:
        gid = _group_id(row)
        ts = row["timestamp"]
        if gid not in group_start or ts < group_start[gid]:
            group_start[gid] = ts

    train: list[dict[str, str]] = []
    holdout: list[dict[str, str]] = []
    quarantined: list[dict[str, str]] = []
    reasons: Counter[str] = Counter()
    excluded_after_end = 0
    for row in rows:
        start = group_start[_group_id(row)]
        if start < cutoff:
            train.append(row)
        elif end is None or start < end:
            reason = _quarantine_reason(dict(row))
            if reason is None:
                holdout.append(row)
            else:
                quarantined.append({**row, "quarantine_reason": reason})
                reasons[reason] += 1
        else:
            excluded_after_end += 1

    report = {
        "cutoff": cutoff,
        "end": end,
        "train_rows": len(train),
        "holdout_valid_rows": len(holdout),
        "holdout_quarantined_rows": len(quarantined),
        "quarantine_reasons": dict(reasons),
        "excluded_after_end": excluded_after_end,
    }
    return train, holdout, quarantined, report


def _write(path: str, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--input", required=True, help="Cleaned router dataset CSV.")
    parser.add_argument("--cutoff", required=True, help="Holdout starts here (ISO date/time).")
    parser.add_argument("--end", help="Exclusive holdout end; later rows are dropped.")
    parser.add_argument("--train-output", required=True)
    parser.add_argument("--holdout-output", required=True)
    parser.add_argument("--quarantine-output")
    parser.add_argument("--report")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    args = build_parser().parse_args(argv)
    with open(args.input, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    train, holdout, quarantined, report = temporal_split(rows, cutoff=args.cutoff, end=args.end)
    if not train or not holdout:
        raise SystemExit(f"Split produced an empty side: {report}")
    _write(args.train_output, train, fieldnames)
    _write(args.holdout_output, holdout, fieldnames)
    if args.quarantine_output:
        _write(args.quarantine_output, quarantined, [*fieldnames, "quarantine_reason"])
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
