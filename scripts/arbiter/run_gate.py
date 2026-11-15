# ruff: noqa: T201, D103, E501
r"""Run the HOK-3028 gate: preflight, rehearse on development repos, or score the slice once.

Modes:

``preflight``
    Reads the sealed slice, checks it against the pre-registered SHA-256, builds
    the gate rows and prints the power check (pass/fail) and training counts.
    Nothing is scored and no slice detail is printed.

``rehearse``
    Draws a stand-in slice from development repos (never the sealed ones) and
    runs the whole pipeline. ``--stand-ins`` maps arms 1–2 onto the arm 4 and
    arm 5 roles, so the pipeline can be exercised before those arms exist.

``score``
    Scores the sealed slice once with the named frozen arms. It writes the
    private record under ``--record-dir`` and a summary without per-repo numbers
    to ``--public-out``. A second run needs ``--rerun-reason`` (§8.1).

Example::

    export HOKUSAI_SCAN_CMD="node /path/to/hokusai-scan.mjs"
    python scripts/arbiter/run_gate.py preflight
    python scripts/arbiter/run_gate.py rehearse --until 2026-09-20 --stand-ins \\
        --resamples 1000 --public-out /tmp/rehearsal.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.arbiter.feature_audit import LeakageError, print_manifest  # noqa: E402
from src.arbiter.gate import (  # noqa: E402
    MIN_POSITIVES,
    MIN_REPOS,
    PRIMARY_HORIZON,
    RESAMPLES,
    ArmContext,
    build_gate_data,
    json_default,
    public_summary,
    read_sealed_slice,
    rehearsal_slice,
    score_once,
)
from src.arbiter.gate_arms import ARM_FACTORIES, RehearsalStandIns  # noqa: E402

CACHE = Path("~/hokusai-data/arbiter-corpus").expanduser()
SLICE = Path("~/.hokusai-private/hok-3028-slice.json").expanduser()
RECORDS = Path("~/.hokusai-private/hok-3028-gate").expanduser()


def _categories() -> dict[str, list[str]]:
    return {
        e["name"]: e["categories"]
        for e in print_manifest()["entries"]
        if e["kind"] == "category" and "categories" in e
    }


def _arms(names: list[str], *, stand_ins: bool) -> list:
    arms = [ARM_FACTORIES[n]() for n in names]
    if stand_ins:
        covered = {role for arm in arms for role in arm.variants().values()}
        missing = tuple(r for r in ("arm4", "arm5") if r not in covered)
        if missing:
            arms.append(RehearsalStandIns(missing))
    return arms


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("mode", choices=("preflight", "rehearse", "score"))
    p.add_argument("--features-root", default=CACHE)
    p.add_argument("--labels-root", default=CACHE)
    p.add_argument("--slice", default=SLICE, help="sealed HOK-3028 slice file (read, never echoed)")
    p.add_argument("--horizon", type=int, default=PRIMARY_HORIZON, choices=(14, 30, 60))
    p.add_argument("--arms", default="hok-3024-baselines", help="comma-separated registered arms")
    p.add_argument(
        "--stand-ins",
        action="store_true",
        help="rehearse: arms 1–2 stand in for arm 4 and/or 5 where no arm is registered",
    )
    p.add_argument("--until", type=date.fromisoformat, help="rehearse: window end (exclusive)")
    p.add_argument("--resamples", type=int, default=RESAMPLES)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--content-root", type=Path, help="private evidence cache for content arms")
    p.add_argument("--record-dir", default=RECORDS)
    p.add_argument("--public-out", type=Path)
    p.add_argument("--rerun-reason")
    args = p.parse_args(argv)

    arm_names = [a for a in args.arms.split(",") if a]
    unknown = [a for a in arm_names if a not in ARM_FACTORIES]
    if unknown:
        p.error(f"unregistered arms: {unknown}")

    try:
        if args.mode == "rehearse":
            if not args.until:
                p.error("rehearse needs --until")
            evaluation_slice = rehearsal_slice(
                args.features_root, args.slice, merged_until=args.until
            )
        else:
            if args.stand_ins:
                p.error("--stand-ins is for rehearse only")
            evaluation_slice = read_sealed_slice(args.slice)
        data = build_gate_data(
            features_root=args.features_root,
            labels_root=args.labels_root,
            sealed_slice_file=args.slice,
            evaluation_slice=evaluation_slice,
            horizon_days=args.horizon,
        )
    except (LeakageError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    primary = data.primary
    ev = data.evaluation
    repos = ev.loc[primary, "repo"].nunique()
    positives = int(ev.loc[primary, "label"].sum())
    powered = repos >= MIN_REPOS and positives >= MIN_POSITIVES
    counts = data.provenance["counts"]
    print(f"slice: {'rehearsal' if evaluation_slice.rehearsal else 'sealed, hash matches §4'}")
    if evaluation_slice.rehearsal:
        # On the sealed slice, training counts would date the window, so they stay unprinted.
        print(f"training rows: {counts['train_rows']} ({counts['train_positives']} positive)")
    print(
        f"power check (≥{MIN_REPOS} repos, ≥{MIN_POSITIVES} positives): {'pass' if powered else 'FAIL'}"
    )
    if args.mode == "preflight":
        return 0 if powered else 1

    context = ArmContext(
        feature_columns=data.feature_columns,
        categories=_categories(),
        content_columns=data.content_columns,
        content_root=args.content_root,
        seed=args.seed,
    )
    try:
        record = score_once(
            data,
            _arms(arm_names, stand_ins=args.stand_ins),
            context,
            record_dir=args.record_dir,
            rerun_reason=args.rerun_reason,
            resamples=args.resamples,
            seed=args.seed,
        )
    except LeakageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    summary = public_summary(record)
    if args.public_out:
        args.public_out.write_text(
            json.dumps(summary, indent=2, sort_keys=True, default=json_default) + "\n"
        )
    print(f"outcome: {record['outcome']}")
    print(f"private record: {record['record_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
