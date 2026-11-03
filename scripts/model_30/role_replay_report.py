"""Role-level replay of Model 30 candidates on a holdout.

The v2 benchmark only counts a label when the predicted route equals the
historically executed route, which on real holdouts is ~5% of rows. This report
gives more statistical power, with two diagnostics:

* **Role agreement lift.** For each role, P(pick == executed | good outcome)
  minus P(pick == executed | bad outcome), with a bootstrap 90% CI. A useful
  router agrees with what worked more often than with what failed. "Good"
  means ``completed_successfully`` and no ``budget_violation``.
* **Calibration gap.** The mean ``estimated_success_under_budget`` of the
  recommended strategy against the observed good rate. This is not a proper
  per-route calibration (the estimate is for the recommended route), but a large
  gap means the model's success estimates don't match current conditions.

Auth: for a remote tracking URI (e.g. ``models:/...`` on registry.hokus.ai), the
MLflow SDK sends ``MLFLOW_TRACKING_TOKEN`` from the environment as a bearer
token. Local ``file://`` stores need no auth.

Example::

    python scripts/model_30/role_replay_report.py \
      --tracking-uri file://$PWD/data/model_30/retrain-2026-11/mlruns \
      --holdout data/model_30/retrain-2026-11/holdout-oct.csv \
      --candidate 'prod=models:/Technical Task Router/5' \
      --candidate B=runs:/<run_id>/model \
      --output data/model_30/retrain-2026-11/role-replay-oct.json
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.model_30 import evaluate_technical_task_router as ev  # noqa: E402

ROLES = ("planner", "coder", "reviewer")


def is_good_outcome(row: dict[str, str]) -> bool:
    """Return True when the row completed successfully within budget."""
    return ev._coerce_bool(row.get("completed_successfully")) and not ev._coerce_bool(
        row.get("budget_violation")
    )


def agreement_lift(
    agree: list[bool], good: list[bool], *, boot: int = 1000, seed: int = 0
) -> dict[str, Any]:
    """Return agreement on good/bad outcomes, the lift, and a bootstrap 90% CI."""

    def lift(idx: list[int]) -> float | None:
        g = [agree[i] for i in idx if good[i]]
        b = [agree[i] for i in idx if not good[i]]
        if not g or not b:
            return None
        return sum(g) / len(g) - sum(b) / len(b)

    idx = list(range(len(agree)))
    point = lift(idx)
    rng = random.Random(seed)
    samples = sorted(
        x for x in (lift([rng.choice(idx) for _ in idx]) for _ in range(boot)) if x is not None
    )
    g = [a for a, y in zip(agree, good) if y]
    b = [a for a, y in zip(agree, good) if not y]
    return {
        "agree_good": round(sum(g) / len(g), 3) if g else None,
        "agree_bad": round(sum(b) / len(b), 3) if b else None,
        "lift": None if point is None else round(point, 3),
        "lift_ci90": (
            [
                round(samples[int(0.05 * len(samples))], 3),
                round(samples[int(0.95 * len(samples)) - 1], 3),
            ]
            if samples
            else None
        ),
    }


def replay(model: Any, rows: list[dict[str, str]], *, objective: str) -> dict[str, Any]:
    """Replay one model over the holdout and summarize role agreement and calibration."""
    good = [is_good_outcome(r) for r in rows]
    agree: dict[str, list[bool]] = {role: [] for role in ROLES}
    estimates: list[float] = []
    for row in rows:
        features = ev._features_from_holdout_row(
            row, objective, ev._scenario_context(row, "production_pool")
        )
        prediction = ev._predict_one(model, features)
        strategy = prediction.get("recommended_strategy") or {}
        for role in ROLES:
            agree[role].append(str(strategy.get(f"{role}_model") or "") == row[f"{role}_model"])
        estimate = ev._optional_float(strategy.get("estimated_success_under_budget"))
        if estimate is not None:
            estimates.append(estimate)
    result: dict[str, Any] = {role: agreement_lift(agree[role], good) for role in ROLES}
    observed = sum(good) / len(good) if good else None
    mean_estimate = sum(estimates) / len(estimates) if estimates else None
    result["mean_estimated_success"] = None if mean_estimate is None else round(mean_estimate, 3)
    result["calibration_gap"] = (
        None if mean_estimate is None or observed is None else round(mean_estimate - observed, 3)
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tracking-uri", required=True)
    parser.add_argument("--holdout", required=True)
    parser.add_argument(
        "--candidate",
        action="append",
        required=True,
        help="name=model_uri; repeat for each candidate.",
    )
    parser.add_argument("--objective", default="highest_reliability")
    parser.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    import mlflow

    args = build_parser().parse_args(argv)
    mlflow.set_tracking_uri(args.tracking_uri)
    with open(args.holdout, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    good = [is_good_outcome(r) for r in rows]
    report: dict[str, Any] = {
        "holdout": args.holdout,
        "rows": len(rows),
        "observed_good_rate": round(sum(good) / len(good), 3) if rows else None,
        "objective": args.objective,
        "results": {},
    }
    for spec in args.candidate:
        name, _, uri = spec.partition("=")
        if not uri:
            raise SystemExit(f"--candidate must be name=model_uri, got {spec!r}")
        report["results"][name] = replay(
            mlflow.pyfunc.load_model(uri), rows, objective=args.objective
        )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n")
    print(text)  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
