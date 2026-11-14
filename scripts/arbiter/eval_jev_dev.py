#!/usr/bin/env python3
# ruff: noqa: T201 - a CLI prints its result
"""Evaluate the Jev composites on development rows already scored (HOK-3026).

Usage:
  python scripts/arbiter/eval_jev_dev.py \
    --cache ~/.hokusai-private/hok-3026/dev-scores.jsonl \
    --public-out docs/arbiter/hok-3026-jev-dev-results.json

Development rows only. This serves two decisions and no others: which of the
two hand-set composites is arm 4's gate score, and whether a question's wording
needs fixing. Weights are not fitted here. Scores are raw rankings; calibration
is fitted by the shared evaluator on training folds (HOK-3028).

Output holds pooled numbers and per-repo distributions, never repo names.
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

from src.arbiter import baselines as bl  # noqa: E402
from src.arbiter import jev_questions as jq  # noqa: E402
from src.arbiter import jev_state as js  # noqa: E402
from src.arbiter.jev_arm import is_current  # noqa: E402
from src.arbiter.rework_dataset import load_dataset  # noqa: E402

SLICE = "~/.hokusai-private/hok-3028-slice.json"
DATASET = "~/hokusai-data/arbiter-datasets/rr-time-2026-02-01-h30-cr020"
# A repo needs this many positives in the sample for its capture to mean anything.
MIN_REPO_POSITIVES = 10
RESAMPLES = 2000
SEED = 20261114


def load_scores(cache: Path) -> pd.DataFrame:
    """Return one row per answered PR under the current versions: composites and risk terms."""
    records = []
    with open(cache) as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not is_current(r) or "answers" not in r:
                continue
            terms = jq.risk_terms(r["answers"])
            records.append(
                {
                    "repo": r["repo"],
                    "pr_number": int(r["pr_number"]),
                    "composite": jq.composite(r["answers"]),
                    "truncated": bool(r["state"]["diff_truncated"]),
                    **{f"term.{k}": v for k, v in terms.items()},
                }
            )
    return pd.DataFrame.from_records(records).drop_duplicates(["repo", "pr_number"])


def macro_capture(frame: pd.DataFrame, column: str) -> tuple[float, list[float]]:
    """Top-decile capture per repo, and its mean over repos with enough positives."""
    per_repo = []
    for _, group in frame.groupby("repo"):
        if group["label"].sum() >= MIN_REPO_POSITIVES:
            per_repo.append(bl.top_capture(group["label"].to_numpy(), group[column].to_numpy()))
    return float(np.mean(per_repo)), per_repo


def paired_difference(frame: pd.DataFrame, a: str, b: str) -> dict[str, Any]:
    """Macro capture of ``a`` minus ``b``, with a bootstrap over repos and rows within them."""
    rng = np.random.default_rng(SEED)
    groups = [g for _, g in frame.groupby("repo") if g["label"].sum() >= MIN_REPO_POSITIVES]
    point = macro_capture(frame, a)[0] - macro_capture(frame, b)[0]
    draws = []
    for _ in range(RESAMPLES):
        diffs = []
        for i in rng.integers(0, len(groups), len(groups)):
            g = groups[i]
            idx = rng.integers(0, len(g), len(g))
            y = g["label"].to_numpy()[idx]
            ca = bl.top_capture(y, g[a].to_numpy()[idx])
            cb = bl.top_capture(y, g[b].to_numpy()[idx])
            if ca is not None and cb is not None:
                diffs.append(ca - cb)
        if diffs:
            draws.append(float(np.mean(diffs)))
    return {
        "difference": point,
        "ci95": [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))],
    }


def _dist(values: list[float]) -> dict[str, float]:
    return {
        "repos": len(values),
        "min": float(min(values)),
        "median": float(np.median(values)),
        "max": float(max(values)),
    }


def _round(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round(v) for v in value]
    return value


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns the exit code."""
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--slice", default=SLICE)
    p.add_argument("--cache", required=True)
    p.add_argument("--public-out")
    args = p.parse_args(argv)

    dataset = load_dataset(Path(args.dataset).expanduser(), slice_file=args.slice)
    scores = load_scores(Path(args.cache).expanduser())
    frame = scores.merge(dataset.rows, on=["repo", "pr_number"], how="inner", validate="1:1")
    code_columns = list(jq.CODE_TERMS)
    frame["code_risk"] = [jq.code_risk(r) for r in frame[code_columns].to_dict("records")]
    frame["steelman_composite"] = (1 - jq.CODE_WEIGHT) * frame["composite"] + (
        jq.CODE_WEIGHT * frame["code_risk"]
    )
    y = frame["label"].to_numpy()

    arms: dict[str, Any] = {}
    kept = {k: w for k, w in jq.WEIGHTS.items() if k not in jq.SENSITIVITY_DROPPED}
    frame["sensitivity_composite"] = (1 - jq.CODE_WEIGHT) * sum(
        w * frame[f"term.{k}"] for k, w in kept.items()
    ) / sum(kept.values()) + jq.CODE_WEIGHT * frame["code_risk"]
    for column in ("composite", "steelman_composite", "sensitivity_composite", "code_risk"):
        macro, per_repo = macro_capture(frame, column)
        arms[column] = {
            "pooled_auc": bl.auc(y, frame[column].to_numpy()),
            "pooled_top_decile_capture": bl.top_capture(y, frame[column].to_numpy()),
            "macro_top_decile_capture": macro,
            "per_repo_top_decile_capture": _dist(per_repo),
        }
    terms = {
        name: {
            "weight": jq.WEIGHTS[name],
            "pooled_auc": bl.auc(y, frame[f"term.{name}"].to_numpy()),
            "mean": float(frame[f"term.{name}"].mean()),
        }
        for name in jq.WEIGHTS
    }
    result = {
        "issue": "HOK-3026",
        "question_set_version": jq.QUESTION_SET_VERSION,
        "state_version": js.STATE_VERSION,
        "model": jq.MODEL,
        "rows": int(len(frame)),
        "positives": int(y.sum()),
        "base_rate": float(y.mean()),
        "diff_truncated_share": float(frame["truncated"].mean()),
        "repos_with_enough_positives": arms["composite"]["per_repo_top_decile_capture"]["repos"],
        "min_repo_positives": MIN_REPO_POSITIVES,
        "chance_top_decile_capture": bl.TOP_FRACTION,
        "arms": arms,
        "steelman_minus_composite": paired_difference(frame, "steelman_composite", "composite"),
        "sensitivity_minus_steelman": paired_difference(
            frame, "sensitivity_composite", "steelman_composite"
        ),
        "frozen_sha256": jq.frozen_sha256(),
        "steelman_minus_code_risk": paired_difference(frame, "steelman_composite", "code_risk"),
        "risk_terms": terms,
    }
    result = _round(result)
    if args.public_out:
        out = Path(args.public_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
