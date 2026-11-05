r"""Build the Model 30 router training CSV from canonical rows only (HOK-3414).

The one corpus builder. Every source arrives as ``model_30_canonical_row/v1``:
frozen Wavemill history under ``model_30/canonical/v1/legacy/<freeze-id>/`` and
v4 contributions under ``model_30/canonical/v1/<submission-id>.jsonl``. No
``.wavemill`` access is needed.

Steps: read rows (local paths or ``s3://`` prefixes) -> keep the newest
freeze of each history line (``--freeze-id`` pins one) -> filter (observed-at
range, source kind, contributor) -> map each to a router row
(``src.model_30.router_corpus``) -> clean and validate
(``clean_router_dataset``) -> write the CSV, plus the price table shipped with
the router artifact (Hokusai's own rates, ``model_30_token_prices``).

Cost trust: rows whose ``cost_status`` is not in ``--trusted-cost-status``
(default: ``priced`` and ``recorded_total``, which reproduces v10) keep their
success label but no cost labels.

Example::

    python scripts/model_30/build_router_corpus.py \\
      --canonical s3://<bucket>/contributions/model_30/canonical/v1/ \\
      --output union.clean.csv --prices-output model-prices.json --report corpus-report.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.model_30.clean_router_dataset import clean_router_datasets  # noqa: E402
from src.model_30.canonical_row import CANONICAL_ROW_SCHEMA_VERSION  # noqa: E402
from src.model_30.model_identity import (  # noqa: E402
    build_price_table,
    hokusai_price_snapshot,
    price_table_version,
)
from src.model_30.router_corpus import (  # noqa: E402
    DEFAULT_TRUSTED_COST_STATUSES,
    FIELDNAMES,
    LEGACY_SOURCE_KIND,
    canonical_to_router_row,
    parse_freeze_id,
    source_kind,
)

CORPUS_REPORT_SCHEMA_VERSION = "model_30_router_corpus/v2"
PRICES_SCHEMA_VERSION = "model_30_router_model_prices/v1"


def _jsonl_lines(text: str, origin: str) -> Iterator[dict[str, Any]]:
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{origin}:{line_number}: malformed JSON") from exc
        if record.get("schema_version") != CANONICAL_ROW_SCHEMA_VERSION:
            raise ValueError(f"{origin}:{line_number}: not a {CANONICAL_ROW_SCHEMA_VERSION} row")
        yield record


def _local_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"canonical row source not found: {path}")
    return sorted(path.rglob("*.jsonl"))


def _s3_records(uri: str) -> Iterator[dict[str, Any]]:
    import boto3

    bucket, _, prefix = uri.removeprefix("s3://").partition("/")
    client = boto3.client("s3")
    keys: list[str] = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        keys.extend(o["Key"] for o in page.get("Contents", []) if o["Key"].endswith(".jsonl"))
    for key in sorted(keys):
        body = client.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
        yield from _jsonl_lines(body, f"s3://{bucket}/{key}")


def read_canonical_rows(sources: Iterable[str]) -> list[dict[str, Any]]:
    """Read every canonical row under *sources* (files, directories, ``s3://`` prefixes)."""
    records: list[dict[str, Any]] = []
    for source in sources:
        if source.startswith("s3://"):
            records.extend(_s3_records(source))
            continue
        for path in _local_files(Path(source).expanduser()):
            records.extend(_jsonl_lines(path.read_text(encoding="utf-8"), str(path)))
    return records


def _freeze_id(record: dict[str, Any]) -> str:
    source = record.get("source") if isinstance(record.get("source"), dict) else {}
    return str(source.get("freeze_id") or "")


def choose_freezes(
    records: Iterable[dict[str, Any]], *, pinned: set[str] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Keep one frozen history per line; contributions pass through.

    Each freeze holds a line's whole history up to its date, so reading two
    freezes of ``wavemill`` would count the same tasks twice. By default the
    newest freeze of each line is used; *pinned* selects freezes explicitly.
    """
    records = list(records)
    found: dict[str, set[str]] = {}
    for record in records:
        if source_kind(record) == LEGACY_SOURCE_KIND:
            freeze_id = _freeze_id(record)
            line, _ = parse_freeze_id(freeze_id)
            found.setdefault(line, set()).add(freeze_id)
    if pinned:
        missing = sorted(pinned - {f for ids in found.values() for f in ids})
        if missing:
            raise ValueError(f"pinned freeze(s) not found: {missing}")
        for line, ids in found.items():
            if len(ids & pinned) > 1:
                raise ValueError(f"pin one freeze per line; {line!r} has {sorted(ids & pinned)}")
        used = set(pinned)
    else:
        used = {max(ids, key=lambda f: parse_freeze_id(f)[1]) for ids in found.values()}
    kept = [r for r in records if source_kind(r) != LEGACY_SOURCE_KIND or _freeze_id(r) in used]
    ignored = sorted({f for ids in found.values() for f in ids} - used)
    return kept, {"used": sorted(used), "ignored": ignored, "pinned": bool(pinned)}


def select_rows(
    records: Iterable[dict[str, Any]],
    *,
    start: str | None = None,
    end: str | None = None,
    sources: set[str] | None = None,
    contributors: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Filter by observed-at range ``[start, end)``, source kind and contributor."""
    selected = []
    for record in records:
        observed = str(record.get("observed_at") or "")
        if start and observed < start:
            continue
        if end and observed >= end:
            continue
        if sources and source_kind(record) not in sources:
            continue
        if contributors and record.get("contributor_id") not in contributors:
            continue
        selected.append(record)
    # Stable: rows with the same timestamp keep their store order.
    return sorted(selected, key=lambda r: str(r.get("observed_at") or ""))


def build_corpus(
    records: list[dict[str, Any]],
    *,
    output: Path,
    raw_output: Path,
    clean_report: Path | None = None,
    prices_output: Path | None = None,
    trusted_cost_statuses: frozenset[str] = DEFAULT_TRUSTED_COST_STATUSES,
) -> dict[str, Any]:
    """Write the raw and cleaned router CSVs (and price table) for *records*."""
    rows = [
        canonical_to_router_row(record, trusted_cost_statuses=trusted_cost_statuses)
        for record in records
    ]
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    with raw_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    cleaned = clean_router_datasets([raw_output], output, clean_report)
    report: dict[str, Any] = {
        "schema_version": CORPUS_REPORT_SCHEMA_VERSION,
        "canonical_rows": len(records),
        "by_source": dict(Counter(source_kind(r) for r in records)),
        "by_cost_status": dict(Counter(str(r.get("cost_status")) for r in records)),
        "cost_labelled_rows": sum(1 for r in rows if r["actual_cost_usd"]),
        "trusted_cost_statuses": sorted(trusted_cost_statuses),
        "output": str(output),
        "output_rows": cleaned["output_rows"],
        "clean_report": cleaned,
    }
    if prices_output is not None:
        route_models = sorted(
            {row[f"{role}_model"] for row in rows for role in ("planner", "coder", "reviewer")}
            - {""}
        )
        prices_output.write_text(
            json.dumps(
                {
                    "schema_version": PRICES_SCHEMA_VERSION,
                    "price_table_version": price_table_version(),
                    "prices": build_price_table([("", hokusai_price_snapshot())], route_models),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        report["model_prices"] = str(prices_output)
    return report


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--canonical",
        action="append",
        required=True,
        help="Canonical rows: a .jsonl file, a directory, or an s3:// prefix. Repeatable.",
    )
    parser.add_argument("--output", required=True, help="Cleaned router CSV for the trainer.")
    parser.add_argument("--raw-output", help="Uncleaned CSV (default: <output>.raw.csv).")
    parser.add_argument("--clean-report", help="Cleaner report JSON.")
    parser.add_argument("--prices-output", help="Price table JSON for --router-prices.")
    parser.add_argument("--report", help="Corpus report JSON.")
    parser.add_argument("--start", help="Inclusive observed_at lower bound (ISO).")
    parser.add_argument("--end", help="Exclusive observed_at upper bound (ISO).")
    parser.add_argument(
        "--source",
        action="append",
        choices=("legacy_freeze", "contribution"),
        help="Keep only these source kinds. Repeatable; default all.",
    )
    parser.add_argument("--contributor", action="append", help="Keep only these contributor ids.")
    parser.add_argument(
        "--freeze-id",
        action="append",
        help=(
            "Frozen history to use, one per line (e.g. wavemill-2026-11-04). Repeatable; "
            "default: the newest freeze of each line."
        ),
    )
    parser.add_argument(
        "--trusted-cost-status",
        action="append",
        help=(
            "cost_status values whose cost labels are trained on. Repeatable; default "
            f"{sorted(DEFAULT_TRUSTED_COST_STATUSES)}."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    args = build_parser().parse_args(argv)
    output = Path(args.output).expanduser().resolve()
    stored, freezes = choose_freezes(
        read_canonical_rows(args.canonical),
        pinned=set(args.freeze_id) if args.freeze_id else None,
    )
    records = select_rows(
        stored,
        start=args.start,
        end=args.end,
        sources=set(args.source) if args.source else None,
        contributors=set(args.contributor) if args.contributor else None,
    )
    report = build_corpus(
        records,
        output=output,
        raw_output=(
            Path(args.raw_output).expanduser().resolve()
            if args.raw_output
            else output.with_name(f"{output.stem}.raw.csv")
        ),
        clean_report=Path(args.clean_report).expanduser().resolve() if args.clean_report else None,
        prices_output=(
            Path(args.prices_output).expanduser().resolve() if args.prices_output else None
        ),
        trusted_cost_statuses=(
            frozenset(args.trusted_cost_status)
            if args.trusted_cost_status
            else DEFAULT_TRUSTED_COST_STATUSES
        ),
    )
    report["legacy_freezes"] = freezes
    report["filters"] = {
        "start": args.start,
        "end": args.end,
        "source": args.source,
        "contributor": args.contributor,
    }
    if args.report:
        Path(args.report).expanduser().write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    summary = {
        k: report[k] for k in ("canonical_rows", "output_rows", "by_source", "legacy_freezes")
    }
    print(json.dumps(summary))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
