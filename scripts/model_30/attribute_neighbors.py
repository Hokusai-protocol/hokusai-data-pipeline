"""Attribute Model 30 improvements to emitted neighbor provenance."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.attribution.neighbor_provenance import attribute  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for neighbor provenance attribution."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--model-id", default="30")
    parser.add_argument("--baseline-run-id", required=True)
    parser.add_argument("--candidate-run-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--created-at")
    parser.add_argument(
        "--schema",
        default=str(REPO_ROOT / "schema" / "attribution_report.v1.json"),
    )
    return parser.parse_args()


def main() -> None:
    """Run the attribution CLI and write a validated JSON report."""
    args = parse_args()
    baseline = pd.read_parquet(Path(args.baseline).expanduser().resolve())
    candidate = pd.read_parquet(Path(args.candidate).expanduser().resolve())

    if (
        "neighbor_provenance" not in candidate.columns
        or candidate["neighbor_provenance"].isna().all()
    ):
        raise SystemExit(
            "neighbor_provenance column missing; run prerequisite provenance emission first"
        )

    created_at = args.created_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )
    report = attribute(
        baseline,
        candidate,
        model_id=args.model_id,
        baseline_run_id=args.baseline_run_id,
        candidate_run_id=args.candidate_run_id,
        created_at=created_at,
    )

    schema = json.loads(Path(args.schema).expanduser().resolve().read_text(encoding="utf-8"))
    jsonschema.validate(instance=report, schema=schema)

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
