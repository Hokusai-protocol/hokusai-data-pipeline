#!/usr/bin/env python3
# ruff: noqa: T201 - a CLI prints its result
r"""Assemble a Rework Risk training dataset from the development repos (HOK-2818).

For example:
  # time split: train on PRs merged before 2026-02-01, evaluate from then on
  python scripts/arbiter/assemble_rework_dataset.py --split time --train-until 2026-02-01 \\
    --out ~/hokusai-data/arbiter-datasets/rr-time-2026-02-01

  # leave-repo-out: one fold per development repo
  python scripts/arbiter/assemble_rework_dataset.py --split leave-repo-out \\
    --out ~/hokusai-data/arbiter-datasets/rr-lro

The roots hold ``<owner>__<name>/`` directories: ``features.jsonl.gz`` under
``--features-root`` (s3://hokusai-pipeline-data-development/arbiter-corpus/hok-3023/),
``corrective.jsonl.gz`` and ``s2.jsonl.gz`` under ``--labels-root``
(.../hok-3022/as-of=2026-10-20/). Both default to the local corpus cache.

The leakage validator runs from ``HOKUSAI_SCAN_CMD`` or ``hokusai-scan`` on PATH.
Write datasets outside git: they name development repos. Output on stdout is
pooled counts only.

Exit codes: 0 assembled, 1 leakage or contract break, 2 bad arguments or inputs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.arbiter.feature_audit import LeakageError  # noqa: E402
from src.arbiter.rework_dataset import (  # noqa: E402
    HORIZONS,
    LeaveRepoOut,
    TimeSplit,
    assemble,
)

CACHE = "~/hokusai-data/arbiter-corpus"
SLICE = "~/.hokusai-private/hok-3028-slice.json"


def _list(path: str | None) -> list[str] | None:
    if path is None:
        return None
    value = json.loads(Path(path).expanduser().read_text())
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{path} must hold a JSON array of strings")
    return value


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns the exit code."""
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--features-root", default=CACHE)
    p.add_argument("--labels-root", default=CACHE)
    p.add_argument("--slice", default=SLICE, help="HOK-3028 evaluation slice file (required)")
    p.add_argument("--split", choices=("time", "leave-repo-out"), required=True)
    p.add_argument("--train-until", help="time split: end of training (YYYY-MM-DD, exclusive)")
    p.add_argument("--eval-from", help="time split: start of evaluation (default --train-until)")
    p.add_argument("--eval-repos", help="leave-repo-out: JSON array file (default every repo)")
    p.add_argument("--horizon", type=int, default=30, choices=HORIZONS)
    p.add_argument("--columns", help="JSON array file of feature columns (default all inputs)")
    p.add_argument("--segment-columns", help="JSON array file of segment.* columns to carry")
    p.add_argument("--allow-segments", action="store_true", help="carry segment columns")
    p.add_argument("--repos", help="JSON array file of development repos (default all)")
    p.add_argument("--out", required=True, help="new directory, outside git")
    args = p.parse_args(argv)

    try:
        if args.split == "time":
            if not args.train_until:
                p.error("--split time needs --train-until")
            split = TimeSplit(train_until=args.train_until, eval_from=args.eval_from)
        else:
            if args.train_until or args.eval_from:
                p.error("--train-until and --eval-from are for --split time")
            eval_repos = _list(args.eval_repos)
            split = LeaveRepoOut(eval_repos=None if eval_repos is None else tuple(eval_repos))
        dataset = assemble(
            features_root=args.features_root,
            labels_root=args.labels_root,
            slice_file=args.slice,
            split=split,
            horizon_days=args.horizon,
            feature_columns=_list(args.columns),
            segment_columns=_list(args.segment_columns) or (),
            allow_segments=args.allow_segments,
            repos=_list(args.repos),
        )
        out = dataset.write(args.out)
    except LeakageError as error:
        print(f"leakage: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    prov = dataset.provenance
    summary = {
        "out": str(out),
        "split": prov["split"],
        "target": prov["target"],
        "development_repos": len(prov["inputs"]),
        "feature_columns": len(dataset.feature_columns),
        "counts": prov["counts"],
        "base_rates_pooled": dataset.base_rates["pooled"],
        "base_rates_by_role": dataset.base_rates.get("by_role"),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
