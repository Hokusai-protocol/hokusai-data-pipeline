#!/usr/bin/env python3
"""Activate the Model 30 v2 composite benchmark spec (HOK-2217).

Makes ``technical_task_router.benchmark_score/v2`` the single active benchmark spec for
the model, so ``BenchmarkSpecService.get_active_spec_for_model(model_id)`` returns it, and
deactivates any other currently-active specs for that model (e.g. the legacy v1 spec).

Benchmark specs are immutable; this only flips the ``is_active`` flag via the sanctioned
``update_spec_fields`` path. It does NOT create specs — register the v2 spec first (via the
governance registration flow) if none exists.

Dry-run by default: prints the plan and changes nothing. Pass ``--apply`` to write.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.api.services.governance.benchmark_specs import BenchmarkSpecService  # noqa: E402

DEFAULT_MODEL_ID = os.getenv("MODEL_30_MODEL_ID", "30")
DEFAULT_METRIC_NAME = "technical_task_router.benchmark_score/v2"


@dataclass
class ActivationPlan:
    """Planned is_active changes to make the v2 spec the single active spec."""

    target: dict[str, Any] | None
    to_activate: list[dict[str, Any]] = field(default_factory=list)
    to_deactivate: list[dict[str, Any]] = field(default_factory=list)


def plan_activation(
    service: BenchmarkSpecService,
    *,
    model_id: str,
    metric_name: str,
) -> ActivationPlan:
    """Compute the activation plan for ``model_id`` without mutating anything."""
    specs = service.list_specs(model_id=model_id)
    matching = [spec for spec in specs if spec.get("metric_name") == metric_name]
    if not matching:
        return ActivationPlan(target=None)

    # Most recently created matching spec becomes the single active one.
    target = sorted(matching, key=lambda spec: spec.get("created_at") or "", reverse=True)[0]

    to_activate = [] if target.get("is_active") else [target]
    to_deactivate = [
        spec
        for spec in specs
        if spec.get("is_active") and spec.get("spec_id") != target.get("spec_id")
    ]
    return ActivationPlan(target=target, to_activate=to_activate, to_deactivate=to_deactivate)


def apply_activation(service: BenchmarkSpecService, plan: ActivationPlan) -> None:
    """Apply the plan's is_active changes via the immutability-safe update path."""
    for spec in plan.to_deactivate:
        service.update_spec_fields(spec["spec_id"], {"is_active": False})
    for spec in plan.to_activate:
        service.update_spec_fields(spec["spec_id"], {"is_active": True})


def _describe(spec: dict[str, Any]) -> str:
    return (
        f"{spec.get('spec_id')} (metric={spec.get('metric_name')}, "
        f"dataset_version={spec.get('dataset_version')}, created_at={spec.get('created_at')})"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--metric-name", default=DEFAULT_METRIC_NAME)
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="Benchmark spec DB URL. Defaults to $DATABASE_URL.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the changes. Without this flag the script is a dry-run.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Plan (and optionally apply) v2 benchmark spec activation."""
    args = parse_args(argv)
    if not args.database_url:
        raise SystemExit(
            "set DATABASE_URL or pass --database-url (in-memory mode does not persist)"
        )

    service = BenchmarkSpecService(database_url=args.database_url)
    plan = plan_activation(service, model_id=args.model_id, metric_name=args.metric_name)

    if plan.target is None:
        raise SystemExit(
            f"no benchmark spec with metric_name={args.metric_name!r} exists for "
            f"model_id={args.model_id!r}; register the v2 spec first."
        )

    sys.stdout.write(f"target active spec: {_describe(plan.target)}\n")
    if not plan.to_activate and not plan.to_deactivate:
        sys.stdout.write("already the single active spec; nothing to do.\n")
        return 0

    for spec in plan.to_deactivate:
        sys.stdout.write(f"  - deactivate {_describe(spec)}\n")
    for spec in plan.to_activate:
        sys.stdout.write(f"  + activate   {_describe(spec)}\n")

    if not args.apply:
        sys.stdout.write("\ndry-run: re-run with --apply to write these changes.\n")
        return 0

    apply_activation(service, plan)
    active = service.get_active_spec_for_model(args.model_id)
    if not active or active.get("spec_id") != plan.target["spec_id"]:
        raise SystemExit(
            "activation applied but active spec verification failed; "
            f"get_active_spec_for_model({args.model_id!r}) returned {active}"
        )
    sys.stdout.write(
        f"\napplied. active spec for model {args.model_id} is now {_describe(active)}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
