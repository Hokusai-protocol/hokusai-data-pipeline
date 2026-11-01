#!/usr/bin/env python3
"""Model 30 routing feedback report (HOK-3365).

Reads stored Model 30 contribution records and their intake routing joins
(``metadata.row_routing_joins``) and reports:

* **coverage**: the share of rows linked to the inference that recommended
  their route, and override counts by source. This is how much of the Hokusai
  feedback loop is measurable.
* **calibration**: recommendation success-under-budget by confidence band,
  from recommendation evidence only (linked, consistent, no override on any
  role). Answers e.g. "does confidence 0.33 predict failure?".
* **overrides**: outcomes per override source, and escalation outcomes vs
  followed recommendations in the same confidence band, which is the
  comparison that decides whether harness escalation should exist.

Rows whose records predate the routing join are counted, never guessed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.api.services.contribution_service import StoredContributionRecord  # noqa: E402
from src.api.services.routing_join import (  # noqa: E402
    ROUTE_OVERRIDE_SOURCES,
    EvidenceClass,
    summarize_routing_joins,
)

REPORT_SCHEMA_VERSION = "model_30_routing_feedback_report/v1"
# Lower bounds are inclusive; the last band includes 1.0.
CONFIDENCE_BANDS: tuple[tuple[str, float, float], ...] = (
    ("[0.0,0.4)", 0.0, 0.4),
    ("[0.4,0.6)", 0.4, 0.6),
    ("[0.6,0.8)", 0.6, 0.8),
    ("[0.8,1.0]", 0.8, 1.0000001),
)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return None if number != number else number


def row_outcome(row: dict[str, Any]) -> tuple[bool | None, float | None]:
    """Return ``(success under budget, actual cost)`` for a stored row, else ``None``s."""
    cost = _number(row.get("actual_cost_usd"))
    if isinstance(row.get("success_under_budget"), bool):
        return bool(row["success_under_budget"]), cost
    if isinstance(row.get("completed_successfully"), bool):
        if not row["completed_successfully"]:
            return False, cost
        budget = _number(row.get("max_cost_usd"))
        if budget is None:
            budget = _number(row.get("budget_usd"))
        if cost is None or budget is None:
            return None, cost
        return cost <= budget, cost
    if isinstance(row.get("completion_result"), str):
        return row["completion_result"] == "success", cost
    return None, cost


def confidence_band(confidence: float) -> str | None:
    """Return the band label for a confidence, or None when out of range."""
    for label, lower, upper in CONFIDENCE_BANDS:
        if lower <= confidence < upper:
            return label
    return None


def _empty_tally() -> dict[str, Any]:
    return {"rows": 0, "known_outcomes": 0, "successes": 0, "cost_usd": 0.0, "confidence_sum": 0.0}


def _add(
    tally: dict[str, Any], success: bool | None, cost: float | None, conf: float | None
) -> None:
    tally["rows"] += 1
    if conf is not None:
        tally["confidence_sum"] += conf
    if success is None:
        return
    tally["known_outcomes"] += 1
    tally["successes"] += int(success)
    tally["cost_usd"] += cost or 0.0


def _finish(tally: dict[str, Any]) -> dict[str, Any]:
    known = tally["known_outcomes"]
    successes = tally["successes"]
    return {
        "rows": tally["rows"],
        "known_outcomes": known,
        "successes": successes,
        "success_rate": successes / known if known else None,
        "mean_confidence": tally["confidence_sum"] / tally["rows"] if tally["rows"] else None,
        "cost_per_success_usd": tally["cost_usd"] / successes if successes else None,
    }


def build_routing_feedback_report(records: Iterable[StoredContributionRecord]) -> dict[str, Any]:
    """Build the coverage, calibration and override report from stored records."""
    joins: list[dict[str, Any]] = []
    rows_without_join = 0
    calibration = {label: _empty_tally() for label, _, _ in CONFIDENCE_BANDS}
    recommendation_without_confidence = 0
    by_source = {source: _empty_tally() for source in ROUTE_OVERRIDE_SOURCES}
    escalation_vs_followed = {
        label: {"followed": _empty_tally(), "escalation": _empty_tally()}
        for label, _, _ in CONFIDENCE_BANDS
    }

    for record in records:
        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        row_joins = metadata.get("row_routing_joins")
        for index, row in enumerate(record.rows):
            join = (
                row_joins[index] if isinstance(row_joins, list) and index < len(row_joins) else None
            )
            if not isinstance(join, dict):
                rows_without_join += 1
                continue
            joins.append(join)
            success, cost = row_outcome(row)
            confidence = _number(join.get("confidence"))
            band = confidence_band(confidence) if confidence is not None else None
            evidence = join.get("evidence")

            if evidence == EvidenceClass.RECOMMENDATION.value:
                if band is None:
                    recommendation_without_confidence += 1
                else:
                    _add(calibration[band], success, cost, confidence)
                    _add(escalation_vs_followed[band]["followed"], success, cost, confidence)
            elif evidence == EvidenceClass.OVERRIDE.value:
                sources = join.get("override_sources") or []
                for source in sources:
                    if source in by_source:
                        _add(by_source[source], success, cost, confidence)
                if band is not None and "escalation" in sources:
                    _add(escalation_vs_followed[band]["escalation"], success, cost, confidence)

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "coverage": {
            **summarize_routing_joins(joins),
            "rows_without_routing_join": rows_without_join,
        },
        "calibration": {
            "evidence": "recommendation evidence only: linked, consistent, no override on any role",
            "bands": {label: _finish(tally) for label, tally in calibration.items()},
            "recommendation_rows_without_confidence": recommendation_without_confidence,
        },
        "overrides": {
            "by_source": {source: _finish(tally) for source, tally in by_source.items()},
            "escalation_vs_followed_by_band": {
                label: {arm: _finish(tally) for arm, tally in arms.items()}
                for label, arms in escalation_vs_followed.items()
            },
        },
    }


def _load_s3_records(bucket: str, prefix: str, model_id: str) -> list[StoredContributionRecord]:
    import boto3

    from scripts.model_30.assemble_training_set import list_contribution_keys, read_record

    s3_client = boto3.client("s3")
    records: list[StoredContributionRecord] = []
    for key in list_contribution_keys(s3_client, bucket, prefix, model_id):
        record, _ = read_record(s3_client, bucket, key)
        if record is not None:
            records.append(record)
    return records


def _load_local_records(directory: Path) -> list[StoredContributionRecord]:
    records: list[StoredContributionRecord] = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        records.append(
            StoredContributionRecord(
                submission_id=payload["submission_id"],
                model_id=payload["model_id"],
                idempotency_key=payload.get("idempotency_key", ""),
                body_hash=payload.get("body_hash", ""),
                rows=payload["rows"],
                metadata=payload.get("metadata", {}),
                response_payload=payload.get("response_payload", {}),
                created_at=payload.get("created_at", ""),
            )
        )
    return records


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default="30")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--s3-bucket", default=os.getenv("HOKUSAI_CONTRIBUTIONS_BUCKET"))
    source.add_argument("--records-dir", help="Directory of stored contribution record JSON.")
    parser.add_argument("--s3-prefix", default=os.getenv("HOKUSAI_CONTRIBUTIONS_PREFIX", ""))
    parser.add_argument("--output", help="Write the report JSON here (default: stdout).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Build the report from S3 or a local directory and write it as JSON."""
    args = parse_args(argv)
    if args.records_dir:
        records = _load_local_records(Path(args.records_dir))
    elif args.s3_bucket:
        records = _load_s3_records(args.s3_bucket, args.s3_prefix, args.model_id)
    else:
        sys.stderr.write("Pass --s3-bucket (or HOKUSAI_CONTRIBUTIONS_BUCKET) or --records-dir\n")
        return 2
    report = build_routing_feedback_report(records)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
