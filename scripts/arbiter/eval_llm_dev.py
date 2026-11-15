#!/usr/bin/env python3
# ruff: noqa: T201 - a CLI prints its result
"""Evaluate the frontier chat-model arm on its development sample (HOK-3027).

Usage:
  python scripts/arbiter/eval_llm_dev.py \
    --cache ~/.hokusai-private/hok-3027/dev-scores.jsonl \
    --jev-cache ~/.hokusai-private/hok-3026/dev-scores.jsonl \
    --public-out docs/arbiter/hok-3027-llm-dev-results.json

Development rows only. The sample over-represents positives (see
``run_llm_arm.py``), so every row is weighted back to the population: within a
repo, period and label, the weight is the number of eligible rows over the
number scored. Results are reported for PRs merged after the model's knowledge
cutoff and before it, separately. The after-cutoff numbers are the ones to
quote: before the cutoff the model may recall what happened to a PR.

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
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.arbiter.eval_jev_dev import load_scores as load_jev_scores  # noqa: E402
from scripts.arbiter.run_llm_arm import with_period  # noqa: E402
from src.arbiter import jev_questions as jq  # noqa: E402
from src.arbiter import jev_state as js  # noqa: E402
from src.arbiter import llm_arm as la  # noqa: E402
from src.arbiter.baselines import ECE_BINS, TOP_FRACTION  # noqa: E402
from src.arbiter.rework_dataset import load_dataset  # noqa: E402

SLICE = "~/.hokusai-private/hok-3028-slice.json"
DATASET = "~/hokusai-data/arbiter-datasets/rr-time-2026-02-01-h30-cr020"
# A repo needs this many scored positives in a period for its capture to mean anything.
MIN_REPO_POSITIVES = 10
RESAMPLES = 2000
SEED = 20261114


def capture(y: np.ndarray, score: np.ndarray, w: np.ndarray) -> float | None:
    """Weighted share of positives in the top decile of weighted rows; ties share the cut."""
    positives = float((w * y).sum())
    if positives == 0:
        return None
    room = TOP_FRACTION * w.sum()
    caught = 0.0
    for value in np.unique(score)[::-1]:
        tied = score == value
        mass = w[tied].sum()
        share = min(room / mass, 1.0)
        caught += share * (w[tied] * y[tied]).sum()
        room -= share * mass
        if room <= 0:
            break
    return caught / positives


def auc(y: np.ndarray, score: np.ndarray, w: np.ndarray) -> float | None:
    """Weighted ROC AUC, or None when only one class is present."""
    if len(set(y.tolist())) < 2:
        return None
    return float(roc_auc_score(y, score, sample_weight=w))


def brier(y: np.ndarray, p: np.ndarray, w: np.ndarray) -> float:
    """Weighted mean squared error of the stated probabilities."""
    return float(np.average((p - y) ** 2, weights=w))


def ece(y: np.ndarray, p: np.ndarray, w: np.ndarray, bins: int = ECE_BINS) -> float:
    """Weighted expected calibration error over equal-mass bins; equal predictions share a bin."""
    order = np.argsort(p, kind="stable")
    y, p, w = y[order], p[order], w[order]
    position = (np.cumsum(w) - w / 2) / w.sum()
    which = np.minimum((position * bins).astype(int), bins - 1)
    # Rows with the same prediction go to the bin of the first of them.
    first = np.searchsorted(p, p, side="left")
    which = which[first]
    total = 0.0
    for b in np.unique(which):
        m = which == b
        total += w[m].sum() * abs(np.average(p[m], weights=w[m]) - np.average(y[m], weights=w[m]))
    return float(total / w.sum())


def _groups(frame: pd.DataFrame) -> list[pd.DataFrame]:
    return [g for _, g in frame.groupby("repo") if g["label"].sum() >= MIN_REPO_POSITIVES]


def _macro(groups: list[pd.DataFrame], column: str, fn: Any = capture) -> list[float]:
    values = [
        fn(g["label"].to_numpy(float), g[column].to_numpy(float), g["weight"].to_numpy(float))
        for g in groups
    ]
    return [v for v in values if v is not None]


def summarize(frame: pd.DataFrame, column: str, probability: str | None) -> dict[str, Any]:
    """Return pooled and per-repo macro metrics for one score column."""
    y, w = frame["label"].to_numpy(float), frame["weight"].to_numpy(float)
    groups = _groups(frame)
    per_repo = _macro(groups, column)
    out: dict[str, Any] = {
        "pooled_auc": auc(y, frame[column].to_numpy(float), w),
        "pooled_top_decile_capture": capture(y, frame[column].to_numpy(float), w),
        "macro_top_decile_capture": float(np.mean(per_repo)) if per_repo else None,
        "macro_auc": float(np.mean(_macro(groups, column, auc))) if groups else None,
        "repos": len(per_repo),
    }
    if per_repo:
        out["per_repo_top_decile_capture"] = {
            "min": float(min(per_repo)),
            "median": float(np.median(per_repo)),
            "max": float(max(per_repo)),
        }
    if probability:
        p = frame[probability].to_numpy(float)
        out["pooled_brier"] = brier(y, p, w)
        out["pooled_ece"] = ece(y, p, w)
        out["macro_brier"] = float(np.mean(_macro(groups, probability, brier))) if groups else None
        out["macro_ece"] = float(np.mean(_macro(groups, probability, ece))) if groups else None
        out["mean_stated_probability"] = float(np.average(p, weights=w))
    return out


def paired(frame: pd.DataFrame, a: str, b: str, fn: Any = capture) -> dict[str, Any] | None:
    """Macro metric of ``a`` minus ``b``, with a bootstrap over repos and rows within them."""
    groups = _groups(frame)
    if not groups:
        return None
    rng = np.random.default_rng(SEED)
    point = float(np.mean(_macro(groups, a, fn)) - np.mean(_macro(groups, b, fn)))
    draws = []
    for _ in range(RESAMPLES):
        diffs = []
        for i in rng.integers(0, len(groups), len(groups)):
            g = groups[i].iloc[rng.integers(0, len(groups[i]), len(groups[i]))]
            y, w = g["label"].to_numpy(float), g["weight"].to_numpy(float)
            va, vb = fn(y, g[a].to_numpy(float), w), fn(y, g[b].to_numpy(float), w)
            if va is not None and vb is not None:
                diffs.append(va - vb)
        if diffs:
            draws.append(float(np.mean(diffs)))
    return {
        "difference": point,
        "ci95": [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))],
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
    p.add_argument("--jev-cache", help="arm 4 answers, for a comparison on the same rows")
    p.add_argument("--public-out")
    args = p.parse_args(argv)

    dataset = load_dataset(Path(args.dataset).expanduser(), slice_file=args.slice)
    eligible = with_period(dataset.rows)
    scored = la.load_scores(Path(args.cache).expanduser())
    frame = scored.merge(eligible, on=["repo", "pr_number"], how="inner", validate="1:1")
    cell = ["repo", "period", "label"]
    population = eligible.groupby(cell).size().rename("population")
    frame = frame.join(population, on=cell)
    frame["weight"] = frame["population"] / frame.groupby(cell)["repo"].transform("size")
    frame["code_risk"] = [jq.code_risk(r) for r in frame[list(jq.CODE_TERMS)].to_dict("records")]

    columns = {"frontier_llm": "score", "frontier_llm.questions": "composite", "code_risk": None}
    frame = frame.rename(columns={"composite": "frontier_llm.questions", "score": "frontier_llm"})
    if args.jev_cache:
        jev = load_jev_scores(Path(args.jev_cache).expanduser())[["repo", "pr_number", "composite"]]
        frame = frame.merge(jev.rename(columns={"composite": "jev.questions"}), how="left")
        frame["jev.steelman"] = (1 - jq.CODE_WEIGHT) * frame["jev.questions"] + (
            jq.CODE_WEIGHT * frame["code_risk"]
        )
        columns |= {"jev.questions": None, "jev.steelman": None}

    periods: dict[str, Any] = {}
    for period, part in frame.groupby("period"):
        if args.jev_cache:
            part = part[part["jev.questions"].notna()]
        usage = [c for c in part.columns if c.startswith("usage.")]
        periods[period] = {
            "rows_scored": int(len(part)),
            "positives_scored": int(part["label"].sum()),
            "population_rows": int(part["weight"].sum()),
            "population_base_rate": float(np.average(part["label"], weights=part["weight"])),
            "arms": {
                name: summarize(part, name, "probability" if name == "frontier_llm" else None)
                for name in columns
            },
            "mean_tokens_per_pr": {c.removeprefix("usage."): float(part[c].mean()) for c in usage},
            "mean_usd_per_pr": float(part["usd"].mean()),
        }
        if args.jev_cache:
            periods[period]["differences_in_macro_top_decile_capture"] = {
                "frontier_llm_minus_jev.steelman": paired(part, "frontier_llm", "jev.steelman"),
                "frontier_llm.questions_minus_jev.questions": paired(
                    part, "frontier_llm.questions", "jev.questions"
                ),
                "frontier_llm_minus_code_risk": paired(part, "frontier_llm", "code_risk"),
            }
    result = {
        "issue": "HOK-3027",
        "arm_version": la.ARM_VERSION,
        "frozen_sha256": la.frozen_sha256(),
        "model": la.MODEL,
        "effort": la.EFFORT,
        "knowledge_cutoff": la.KNOWLEDGE_CUTOFF,
        "state_version": js.STATE_VERSION,
        "question_set_version": jq.QUESTION_SET_VERSION,
        "min_repo_positives": MIN_REPO_POSITIVES,
        "chance_top_decile_capture": TOP_FRACTION,
        "total_usd": float(scored["usd"].sum()),
        "periods": periods,
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
