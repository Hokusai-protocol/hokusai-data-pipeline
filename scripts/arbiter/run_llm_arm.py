#!/usr/bin/env python3
# ruff: noqa: T201 - a CLI prints its result
"""Score a development sample with the frontier chat-model arm, resumably (HOK-3027).

Usage:
  python scripts/arbiter/run_llm_arm.py --positives 150 --negatives 600 --max-usd 100 \
    --cache ~/.hokusai-private/hok-3027/dev-scores.jsonl

Sends PR text to Anthropic; needs ANTHROPIC_API_KEY. Answers are appended to
``--cache`` as they arrive. If the run stops (spend cap, rate limit, crash), run
the same command again: rows already in the cache are skipped.

The sample is drawn by the evaluator, not by the arm, so it may use labels. It
has two periods: merged after the model's knowledge cutoff, and in the year up
to it. Each period gets ``--positives`` positive rows and ``--negatives``
negative rows, taken in a fixed hash order, so larger numbers extend an earlier
run. ``eval_llm_dev.py`` weights the rows back to the population.

``--jev-cache`` also scores the same rows with arm 4 (needs TYPESAFE_API_KEY),
so the two snap-judgment arms can be compared on identical rows.

Only development rows are read: the dataset excludes the HOK-3028 evaluation
slice, and ``--slice`` is passed on as a path to check that. Output never names
a repo or a PR. The caches name both: keep them outside git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.arbiter import jev_arm  # noqa: E402
from src.arbiter import llm_arm as la  # noqa: E402
from src.arbiter.jev_client import JevClient  # noqa: E402
from src.arbiter.rework_dataset import load_dataset  # noqa: E402

SLICE = "~/.hokusai-private/hok-3028-slice.json"
DATASET = "~/hokusai-data/arbiter-datasets/rr-time-2026-02-01-h30-cr020"
CORPUS = "~/hokusai-data/arbiter-corpus"
BEFORE_DAYS = 365


def with_period(rows: pd.DataFrame) -> pd.DataFrame:
    """Keep non-bot rows in the two periods and name each row's period."""
    rows = rows[rows[la.BOT_COLUMN] != True]  # noqa: E712 - None means unknown
    cutoff = pd.Timestamp(la.KNOWLEDGE_CUTOFF, tz="UTC") + pd.Timedelta(days=1)
    start = cutoff - pd.Timedelta(days=BEFORE_DAYS)
    rows = rows[rows["as_of"] >= start]
    return rows.assign(period=["after" if at >= cutoff else "before" for at in rows["as_of"]])


def draw(rows: pd.DataFrame, positives: int, negatives: int, seed: int) -> pd.DataFrame:
    """Return the first rows of each (period, label) cell in hash order."""
    order = [
        hashlib.sha256(f"{seed}\x00{repo}\x00{int(number)}".encode()).hexdigest()
        for repo, number in zip(rows["repo"], rows["pr_number"], strict=True)
    ]
    rows = rows.assign(_order=order).sort_values("_order")
    parts = []
    for (_, label), cell in rows.groupby(["period", "label"]):
        parts.append(cell.head(positives if label else negatives))
    return pd.concat(parts).drop(columns="_order")


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns 0 when every sampled row is settled, 1 when the run stopped early."""
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--corpus-root", default=CORPUS)
    p.add_argument("--slice", default=SLICE)
    p.add_argument("--positives", type=int, required=True, help="positive rows per period")
    p.add_argument("--negatives", type=int, required=True, help="negative rows per period")
    p.add_argument("--seed", type=int, default=la.SAMPLE_SEED)
    p.add_argument("--cache", required=True, help="private JSONL of answers; names repos")
    p.add_argument("--jev-cache", help="also score the sample with arm 4 into this cache")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--max-usd", type=float, required=True, help="stop when this run spends this")
    args = p.parse_args(argv)

    dataset = load_dataset(Path(args.dataset).expanduser(), slice_file=args.slice)
    sample = draw(with_period(dataset.rows), args.positives, args.negatives, args.seed)
    corpus_root = Path(args.corpus_root).expanduser()
    cells = sample.groupby(["period", "label"]).size()
    print(json.dumps({"sample": {f"{k[0]}.{int(k[1])}": int(v) for k, v in cells.items()}}))

    started = time.monotonic()

    def progress(stats: dict[str, Any]) -> None:
        stats["minutes"] = round((time.monotonic() - started) / 60, 1)
        stats["usd"] = round(stats["usd"], 3)
        print(json.dumps(stats), file=sys.stderr, flush=True)

    if args.jev_cache:
        local = threading.local()

        def jev_score(row: dict[str, Any], base_sha: str) -> dict[str, Any]:
            if not hasattr(local, "client"):
                local.client = JevClient()
            return jev_arm.score_row(local.client, row, base_sha, corpus_root)

        jev = jev_arm.run(
            la.work_items(sample, corpus_root),
            cache=Path(args.jev_cache).expanduser(),
            score=jev_score,
            workers=args.workers,
            max_usd=2.0,
        )
        print(json.dumps({"arm4": {**jev, "usd": round(jev["usd"], 3)}}))
        if jev["stopped"]:
            return 1

    stats = la.run(
        sample,
        corpus_root=corpus_root,
        cache=Path(args.cache).expanduser(),
        max_usd=args.max_usd,
        workers=args.workers,
        progress=progress,
    )
    stats["minutes"] = round((time.monotonic() - started) / 60, 1)
    stats["usd"] = round(stats["usd"], 3)
    print(json.dumps(stats, indent=2))
    unsettled = stats["to_score"] - stats["scored"] - stats["unscorable"]
    return 1 if stats["stopped"] or unsettled else 0


if __name__ == "__main__":
    sys.exit(main())
