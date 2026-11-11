#!/usr/bin/env python3
# ruff: noqa: T201 - a CLI prints its result
"""Run the trivial and classical JIT baselines on Rework Risk datasets (HOK-3024).

Usage:
  python scripts/arbiter/run_rework_baselines.py \
    --time-dataset ~/hokusai-data/arbiter-datasets/rr-time-2026-02-01-h30 \
    --lro-dataset ~/hokusai-data/arbiter-datasets/rr-lro-h30 \
    --private-out ~/.hokusai-private/hok-3024/results.json \
    --public-out docs/arbiter/hok-3024-baselines.json

``--private-out`` holds per-repo results and names development repos: keep it
outside git. ``--public-out`` holds pooled results and per-repo distributions
with no repo names.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.arbiter import baselines as bl  # noqa: E402
from src.arbiter.feature_audit import print_manifest  # noqa: E402
from src.arbiter.rework_dataset import (  # noqa: E402
    AssembledDataset,
    LeaveRepoOut,
    TimeSplit,
    load_dataset,
)

SLICE = "~/.hokusai-private/hok-3028-slice.json"
Categories = dict[str, list[str]]
RESAMPLES = 500


def _round(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round(v) for v in value]
    return value


def _quarter(ts: pd.Timestamp) -> str:
    return f"{ts.year}Q{(ts.month - 1) // 3 + 1}"


def _arm_metrics(y: np.ndarray, scores: list[bl.Scores], prior: float) -> dict[str, Any]:
    return {s.arm: bl.metrics(y, s, prior) for s in scores}


def run_time(dataset: AssembledDataset, categories: Categories) -> dict[str, Any]:
    """Fit on the training period; report pooled, per repo and per quarter."""
    (split,) = list(dataset.splits())
    y_train = split.y("train")
    prior = float(np.average(y_train, weights=split.weights("train")))
    scores = bl.fit_and_score(
        split.X("train"), y_train, split.X("eval"), categories, weights=split.weights("train")
    )
    y = split.y("eval").to_numpy()
    pooled = {}
    for s in scores:
        pooled[s.arm] = bl.metrics(y, s, prior)
        pooled[s.arm]["ci95"] = bl.bootstrap(y, s, prior, resamples=RESAMPLES)
    by_repo, by_quarter = {}, {}
    repos = split.evaluation["repo"].to_numpy()
    quarters = split.evaluation["as_of"].map(_quarter).to_numpy()
    for repo in sorted(set(repos)):
        m = repos == repo
        by_repo[repo] = _arm_metrics(
            y[m], [bl.Scores(s.arm, s.score[m], s.probability) for s in scores], prior
        )
    for q in sorted(set(quarters)):
        m = quarters == q
        by_quarter[q] = _arm_metrics(
            y[m], [bl.Scores(s.arm, s.score[m], s.probability) for s in scores], prior
        )
    return {
        "train_rows": int(len(y_train)),
        "train_positives": int(y_train.sum()),
        "train_rate": prior,
        "pooled": pooled,
        "by_repo": by_repo,
        "by_quarter": by_quarter,
    }


def run_lro(dataset: AssembledDataset, categories: Categories) -> dict[str, Any]:
    """Fit one model per held-out repo."""
    by_repo = {}
    oof_y, oof = [], {}
    for split in dataset.splits():
        y_train = split.y("train")
        prior = float(np.average(y_train, weights=split.weights("train")))
        scores = bl.fit_and_score(
            split.X("train"), y_train, split.X("eval"), categories, weights=split.weights("train")
        )
        y = split.y("eval").to_numpy()
        by_repo[split.name] = _arm_metrics(y, scores, prior)
        oof_y.append(y)
        for s in scores:
            oof.setdefault(s.arm, []).append(s)
        print(f"lro fold {len(by_repo)} done", file=sys.stderr)
    y = np.concatenate(oof_y)
    pooled = {}
    for arm, parts in oof.items():
        score = np.concatenate([p.score for p in parts])
        # Out-of-fold scores come from 12 different models; pooled AUC mixes repos.
        pooled[arm] = {
            "auc": bl.auc(y, score),
            "top_decile_capture": bl.top_capture(y, score),
        }
    return {"by_repo": by_repo, "pooled_out_of_fold": pooled}


def _distribution(by_repo: dict[str, Any], arm: str, key: str) -> dict[str, Any]:
    values = sorted(v[arm][key] for v in by_repo.values() if v[arm].get(key) is not None)
    if not values:
        return {"repos": 0}
    return {
        "repos": len(values),
        "min": values[0],
        "median": float(np.median(values)),
        "max": values[-1],
        "at_least_0.55": sum(v >= 0.55 for v in values) if key == "auc" else None,
    }


def public_view(result: dict[str, Any]) -> dict[str, Any]:
    """Pooled results and per-repo distributions, with no repo names."""
    arms = list(result["time_split"]["pooled"])
    keys = ("auc", "top_decile_capture", "brier_skill", "ece")
    return {
        "issue": "HOK-3024",
        "datasets": result["datasets"],
        "fixed_parameters": result["fixed_parameters"],
        "time_split": {
            k: result["time_split"][k] for k in ("train_rows", "train_positives", "train_rate")
        }
        | {
            "pooled": result["time_split"]["pooled"],
            "by_quarter": result["time_split"]["by_quarter"],
            "per_repo_distribution": {
                arm: {k: _distribution(result["time_split"]["by_repo"], arm, k) for k in keys}
                for arm in arms
            },
        },
        "leave_repo_out": {
            "pooled_out_of_fold": result["leave_repo_out"]["pooled_out_of_fold"],
            "per_repo_distribution": {
                arm: {k: _distribution(result["leave_repo_out"]["by_repo"], arm, k) for k in keys}
                for arm in arms
            },
        },
        "label_quality": result["label_quality"],
    }


def _dataset_ref(path: Path, dataset: AssembledDataset) -> dict[str, Any]:
    prov = dataset.provenance
    return {
        "provenance_sha256": hashlib.sha256((path / "provenance.json").read_bytes()).hexdigest(),
        "dataset_schema_version": prov["dataset_schema_version"],
        "feature_manifest_version": prov["feature_manifest_version"],
        "target": prov["target"],
        "split": prov["split"],
        "evaluation_slice_sha256": prov["evaluation_slice"]["sha256"],
        "development_repos": len(prov["inputs"]),
        "rows": prov["counts"]["accepted"],
        "positives": prov["counts"]["positives"],
    }


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns the exit code."""
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--time-dataset", required=True)
    p.add_argument("--lro-dataset", required=True)
    p.add_argument("--slice", default=SLICE)
    p.add_argument("--private-out", required=True)
    p.add_argument("--public-out", required=True)
    args = p.parse_args(argv)

    time_path = Path(args.time_dataset).expanduser()
    lro_path = Path(args.lro_dataset).expanduser()
    time_ds = load_dataset(time_path, slice_file=args.slice)
    lro_ds = load_dataset(lro_path, slice_file=args.slice)
    if not isinstance(time_ds.split, TimeSplit) or not isinstance(lro_ds.split, LeaveRepoOut):
        print("error: need a time-split dataset and a leave-repo-out dataset", file=sys.stderr)
        return 2
    categories = {
        e["name"]: e["categories"]
        for e in print_manifest()["entries"]
        if e["kind"] == "category" and "categories" in e
    }

    result: dict[str, Any] = {
        "issue": "HOK-3024",
        "datasets": {
            "time_split": _dataset_ref(time_path, time_ds),
            "leave_repo_out": _dataset_ref(lro_path, lro_ds),
        },
        "fixed_parameters": {
            "trivial_features": dict(bl.TRIVIAL_FEATURES),
            "logistic_regression": bl.LR_PARAMS,
            "gradient_boosting": bl.GBM_PARAMS,
            "top_fraction": bl.TOP_FRACTION,
            "ece_bins": bl.ECE_BINS,
            "bootstrap_resamples": RESAMPLES,
            "seed": bl.SEED,
        },
    }
    result["time_split"] = run_time(time_ds, categories)
    print("time split done", file=sys.stderr)
    result["leave_repo_out"] = run_lro(lro_ds, categories)
    result["label_quality"] = bl.label_quality(result["time_split"], result["leave_repo_out"])
    result = _round(result)

    for path, data in ((args.private_out, result), (args.public_out, _round(public_view(result)))):
        out = Path(path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["label_quality"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
