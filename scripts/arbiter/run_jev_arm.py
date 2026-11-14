#!/usr/bin/env python3
# ruff: noqa: T201 - a CLI prints its result
"""Score development PRs with the Jev question set, resumably (HOK-3026).

Usage:
  python scripts/arbiter/run_jev_arm.py --n 40000 --max-usd 12 \
    --cache ~/.hokusai-private/hok-3026/dev-scores.jsonl

Sends PR text to TypeSafe; needs TYPESAFE_API_KEY. Answers are appended to
``--cache`` as they arrive. If the run stops (balance, rate limit, crash), run
the same command again: rows already in the cache are skipped. The rows are a
seeded random sample taken in a fixed order, so a larger ``--n`` extends an
earlier run and any prefix is itself a random sample.

Only development rows are read: the dataset excludes the HOK-3028 evaluation
slice, and ``--slice`` is passed on as a path to check that. Output never names
a repo or a PR. ``--cache`` names both: keep it outside git.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.arbiter import jev_arm  # noqa: E402
from src.arbiter import jev_state as js  # noqa: E402
from src.arbiter.jev_client import JevClient  # noqa: E402
from src.arbiter.rework_dataset import load_dataset  # noqa: E402

SLICE = "~/.hokusai-private/hok-3028-slice.json"
DATASET = "~/hokusai-data/arbiter-datasets/rr-time-2026-02-01-h30-cr020"
CORPUS = "~/hokusai-data/arbiter-corpus"
SEED = 20261114


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns 0 when every sampled row is settled, 1 when the run stopped early."""
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--corpus-root", default=CORPUS)
    p.add_argument("--slice", default=SLICE)
    p.add_argument("--n", type=int, required=True, help="rows in the random sample")
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--cache", required=True, help="private JSONL of answers; names repos")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--max-usd", type=float, required=True, help="stop when this run spends this")
    args = p.parse_args(argv)

    dataset = load_dataset(Path(args.dataset).expanduser(), slice_file=args.slice)
    rows = dataset.rows
    # Dependency-bot PRs are a separate segment (pre-registration §2).
    rows = rows[rows["feature.author.is_bot"] != True]  # noqa: E712 - None means unknown
    # Shuffle everything, then take a prefix: a larger --n extends a smaller one.
    rows = rows.sample(frac=1.0, random_state=args.seed).head(args.n)
    corpus_root = Path(args.corpus_root).expanduser()

    bases: dict[tuple[str, int], str] = {}
    for repo, group in rows.groupby("repo"):
        numbers = {int(n) for n in group["pr_number"]}
        for number, sha in js.base_shas(corpus_root, repo, numbers).items():
            bases[(repo, number)] = sha
    columns = ["repo", "pr_number", "merge_sha", "as_of"]
    work = [
        (row, bases[(row["repo"], int(row["pr_number"]))])
        for row in rows[columns].to_dict("records")
        if (row["repo"], int(row["pr_number"])) in bases
    ]
    print(json.dumps({"sampled": len(rows), "with_base_sha": len(work)}), file=sys.stderr)

    local = threading.local()

    def score(row: dict[str, Any], base_sha: str) -> dict[str, Any]:
        if not hasattr(local, "client"):
            local.client = JevClient()
        return jev_arm.score_row(local.client, row, base_sha, corpus_root)

    started = time.monotonic()

    def progress(stats: dict[str, Any]) -> None:
        stats["minutes"] = round((time.monotonic() - started) / 60, 1)
        stats["usd"] = round(stats["usd"], 3)
        print(json.dumps(stats), file=sys.stderr, flush=True)

    stats = jev_arm.run(
        work,
        cache=Path(args.cache).expanduser(),
        score=score,
        workers=args.workers,
        max_usd=args.max_usd,
        progress=progress,
    )
    stats["minutes"] = round((time.monotonic() - started) / 60, 1)
    stats["usd"] = round(stats["usd"], 3)
    print(json.dumps(stats, indent=2))
    unsettled = stats["to_score"] - stats["scored"] - stats["unscorable"]
    return 1 if stats["stopped"] or unsettled else 0


if __name__ == "__main__":
    sys.exit(main())
