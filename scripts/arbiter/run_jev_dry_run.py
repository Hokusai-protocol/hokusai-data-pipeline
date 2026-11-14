#!/usr/bin/env python3
# ruff: noqa: T201 - a CLI prints its result
"""Dry-run the Jev question set on a sample of development PRs (HOK-3026).

Usage:
  # State sizes and truncation only; nothing leaves the machine
  python scripts/arbiter/run_jev_dry_run.py --offline --n 300

  # Score a handful with Jev (sends PR text to TypeSafe; needs TYPESAFE_API_KEY)
  python scripts/arbiter/run_jev_dry_run.py --n 12 \
    --private-out ~/.hokusai-private/hok-3026/dry-run.jsonl

Only development rows are read: the dataset excludes the HOK-3028 evaluation
slice, and ``--slice`` is passed on as a path to check that. Stdout never names
a repo or a PR, because a list of development repos reveals the slice.
``--private-out`` names both: keep it outside git.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.arbiter import jev_questions as jq  # noqa: E402
from src.arbiter import jev_state as js  # noqa: E402
from src.arbiter.jev_client import ContextExceededError, JevClient, cost_usd  # noqa: E402
from src.arbiter.rework_dataset import load_dataset  # noqa: E402

SLICE = "~/.hokusai-private/hok-3028-slice.json"
DATASET = "~/hokusai-data/arbiter-datasets/rr-time-2026-02-01-h30-cr020"
CORPUS = "~/hokusai-data/arbiter-corpus"
SEED = 20261114
# On a context error the diff budget is halved, at most this many times.
MAX_HALVINGS = 2


def sample_rows(rows: pd.DataFrame, n: int, *, balanced: bool, seed: int) -> pd.DataFrame:
    """Pick ``n`` non-bot rows: half positives when ``balanced``, else uniformly at random."""
    rows = rows[rows["feature.author.is_bot"] != True]  # noqa: E712 - None means unknown
    if not balanced:
        return rows.sample(n=min(n, len(rows)), random_state=seed)
    half = n // 2
    positives = rows[rows["label"] == 1].sample(n=half, random_state=seed)
    negatives = rows[rows["label"] == 0].sample(n=n - half, random_state=seed)
    return pd.concat([positives, negatives]).sample(frac=1.0, random_state=seed)


def score_row(
    client: JevClient | None, row: pd.Series, base_sha: str, corpus_root: Path
) -> dict[str, Any]:
    """Build one row's state and, with a client, ask the question set."""
    record: dict[str, Any] = {
        "repo": row["repo"],
        "pr_number": int(row["pr_number"]),
        "merge_sha": row["merge_sha"],
        "label": int(row["label"]),
        "question_set_version": jq.QUESTION_SET_VERSION,
    }
    budget = js.DIFF_BUDGET_CHARS
    for halvings in range(MAX_HALVINGS + 1):
        built = js.state_for_row(
            corpus_root=corpus_root,
            repo=row["repo"],
            pr_number=int(row["pr_number"]),
            base_sha=base_sha,
            merge_sha=row["merge_sha"],
            as_of=row["as_of"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            diff_budget=budget,
        )
        record["state"] = built.meta | {"budget_halvings": halvings}
        if client is None:
            return record
        try:
            response = client.ask(model=jq.MODEL, state=built.state, questions=jq.QUESTIONS)
        except ContextExceededError:
            budget //= 2
            continue
        features = row.to_dict()
        record.update(
            model=response["model"],
            usage=response["usage"],
            answers=response["answers"],
            composite=jq.composite(response["answers"]),
            steelman_composite=jq.steelman_composite(response["answers"], features),
            code_risk=jq.code_risk(features),
            hybrid_features=jq.hybrid_features(response["answers"]),
        )
        return record
    record["error"] = "context_exceeded"
    return record


def _quantiles(values: list[float]) -> dict[str, float]:
    q = np.percentile(values, [50, 90, 99])
    return {
        "median": float(q[0]),
        "p90": float(q[1]),
        "p99": float(q[2]),
        "max": float(max(values)),
        "mean": float(np.mean(values)),
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate facts with no repo names or PR numbers."""
    built = [r for r in records if "state" in r]
    out: dict[str, Any] = {
        "question_set_version": jq.QUESTION_SET_VERSION,
        "state_version": js.STATE_VERSION,
        "rows": len(records),
        "state_unavailable": sum("state_error" in r for r in records),
        "state_chars": _quantiles([r["state"]["state_chars"] for r in built]) if built else None,
        "diff_truncated_share": float(np.mean([r["state"]["diff_truncated"] for r in built]))
        if built
        else None,
        "title_unknown": sum(not r["state"]["title_known"] for r in built),
        "body_unknown": sum(not r["state"]["body_known"] for r in built),
    }
    scored = [r for r in records if "usage" in r]
    if scored:
        tokens = [r["usage"]["input_tokens"] for r in scored]
        chars = [r["state"]["state_chars"] for r in scored]
        out["scored"] = {
            "rows": len(scored),
            "models": sorted({r["model"] for r in scored}),
            "context_exceeded": sum(r.get("error") == "context_exceeded" for r in records),
            "budget_halved": sum(r["state"]["budget_halvings"] > 0 for r in scored),
            "input_tokens": _quantiles(tokens),
            "chars_per_token": float(sum(chars) / sum(tokens)),
            "usd_per_1000_prs": cost_usd(int(np.mean(tokens) * 1000)),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns the exit code."""
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--corpus-root", default=CORPUS)
    p.add_argument("--slice", default=SLICE)
    p.add_argument("--n", type=int, default=12)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--offline", action="store_true", help="build states only; send nothing")
    p.add_argument("--private-out", help="per-row JSONL; names repos, holds no raw text")
    args = p.parse_args(argv)

    dataset = load_dataset(Path(args.dataset).expanduser(), slice_file=args.slice)
    rows = sample_rows(dataset.rows, args.n, balanced=not args.offline, seed=args.seed)
    corpus_root = Path(args.corpus_root).expanduser()
    client = None if args.offline else JevClient()

    bases: dict[tuple[str, int], str] = {}
    for repo, group in rows.groupby("repo"):
        numbers = {int(n) for n in group["pr_number"]}
        for number, sha in js.base_shas(corpus_root, repo, numbers).items():
            bases[(repo, number)] = sha

    records: list[dict[str, Any]] = []
    for position, (_, row) in enumerate(rows.iterrows(), start=1):
        key = (row["repo"], int(row["pr_number"]))
        try:
            record = score_row(client, row, bases[key], corpus_root)
        except (js.StateUnavailableError, KeyError) as error:
            record = {
                "repo": key[0],
                "pr_number": key[1],
                "state_error": type(error).__name__,
            }
        records.append(record)
        if not args.offline:
            line = {
                "row": position,
                "label": record.get("label"),
                "files": record.get("state", {}).get("files_total"),
                "truncated": record.get("state", {}).get("diff_truncated"),
                "input_tokens": record.get("usage", {}).get("input_tokens"),
                "composite": record.get("composite"),
                "steelman": record.get("steelman_composite"),
                "error": record.get("error") or record.get("state_error"),
            }
            print(json.dumps(line))

    if args.private_out:
        out = Path(args.private_out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(out, "w") as f:
            for record in records:
                f.write(json.dumps(record, sort_keys=True) + "\n")
        out.chmod(0o600)
    print(json.dumps(summarize(records), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
