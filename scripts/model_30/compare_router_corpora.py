"""Compare two router training CSVs row for row (HOK-3414 parity check).

Used to show a corpus built from canonical rows matches a reference build (e.g.
``v10-final/union.clean.csv``). Rows are compared in order, column by column.
Numbers are equal when they agree after ``--round-to`` significant figures
(default 6: the pre-HOK-3414 collector wrote numbers with ``%g``); model lists
are compared as JSON. Exit 1 when any row or value differs.

    python scripts/model_30/compare_router_corpora.py reference.csv candidate.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _equal(left: str, right: str, digits: int) -> tuple[bool, float]:
    """Return ``(equal, relative difference)`` for two cells."""
    if left == right:
        return True, 0.0
    try:
        a, b = float(left), float(right)
    except ValueError:
        try:
            return json.loads(left) == json.loads(right), math.nan
        except (json.JSONDecodeError, TypeError):
            return False, math.nan
    rel = abs(a - b) / max(abs(a), abs(b), 1e-300)
    return f"{a:.{digits}g}" == f"{b:.{digits}g}" or rel <= 1e-12, rel


def compare(reference: Path, candidate: Path, *, digits: int = 6) -> dict[str, Any]:
    """Return a report of every difference between two router CSVs."""
    ref_columns, ref_rows = _read(reference)
    cand_columns, cand_rows = _read(candidate)
    differences: Counter[str] = Counter()
    examples: dict[str, list[Any]] = {}
    text_only: Counter[str] = Counter()
    max_rel: dict[str, float] = {}
    for index, (ref, cand) in enumerate(zip(ref_rows, cand_rows, strict=False)):
        for column in ref_columns:
            left, right = ref.get(column, ""), cand.get(column, "")
            equal, rel = _equal(left, right, digits)
            if not equal:
                differences[column] += 1
                examples.setdefault(column, [index, left, right])
            elif left != right:
                text_only[column] += 1
                if not math.isnan(rel):
                    max_rel[column] = max(max_rel.get(column, 0.0), rel)
    return {
        "identical": (
            ref_columns == cand_columns and len(ref_rows) == len(cand_rows) and not differences
        ),
        "rows": [len(ref_rows), len(cand_rows)],
        "columns_identical": ref_columns == cand_columns,
        "value_differences": dict(differences),
        "first_difference": examples,
        "formatting_only_cells": sum(text_only.values()),
        "max_relative_difference": {c: max_rel[c] for c in sorted(max_rel)},
    }


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("reference")
    parser.add_argument("candidate")
    parser.add_argument("--round-to", type=int, default=6, help="Significant figures.")
    args = parser.parse_args(argv)
    report = compare(Path(args.reference), Path(args.candidate), digits=args.round_to)
    print(json.dumps(report, indent=2))  # noqa: T201
    return 0 if report["identical"] else 1


if __name__ == "__main__":
    sys.exit(main())
