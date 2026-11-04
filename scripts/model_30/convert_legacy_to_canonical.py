r"""Freeze Wavemill history into canonical Model 30 rows (HOK-3414, one-off backfill).

This is the only reader of Wavemill eval records. It runs once per freeze, not
per retrain. Training then reads the frozen canonical rows
(``build_router_corpus.py``), so history survives after Claude Code transcripts
(~30 days) and local eval files age out.

Inputs:

* ``--search-root``: an eval snapshot (``<repo>/.wavemill/evals/evals.jsonl`` and
  ``challenge-records.jsonl``), e.g. ``data/model_30/retrain-2026-11/snapshot-v10``;
* ``--recovered-usage``: ``recover_session_usage.py`` output (real tokens for the
  2026-06-24 -> 10-26 contaminated window);
* ``--legacy-csv``: the frozen Feb-May router export, the only copy of pre-May
  history. Its placeholder success labels are re-derived from ``score``, and its
  OpenAI costs (cached input double-counted, no tokens to reprice) become unknown.

Output (``--output-dir``): ``rows.jsonl`` (canonical rows) and ``manifest.json``
(freeze id, input hashes, counts, git commit). Upload the directory as
``model_30/canonical/v1/legacy/<freeze-id>/``::

    W=data/model_30/retrain-2026-11
    python scripts/model_30/convert_legacy_to_canonical.py \\
      --search-root $W/snapshot-v10 \\
      --recovered-usage $W/v10-final/recovered-usage.json \\
      --legacy-csv $W/snapshot/wavemill/.wavemill/evals/hokusai-router-dataset.csv \\
      --freeze-id wavemill-2026-11-04 --output-dir /tmp/freeze
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.model_30.collect_wavemill_router_corpus import derive_router_rows  # noqa: E402
from src.model_30.model_identity import (  # noqa: E402
    is_supported_model_id,
    model_family,
    normalize_model_id,
)
from src.model_30.router_corpus import (  # noqa: E402
    FIELDNAMES,
    parse_freeze_id,
    router_row_to_canonical,
)

FREEZE_SCHEMA_VERSION = "model_30_canonical_freeze/v1"
# Mirrors wavemill shared/lib/eval-success-policy.ts DEFAULT_SUCCESS_THRESHOLD.
DEFAULT_SUCCESS_THRESHOLD = 0.8
ROLE_COLUMNS = ("planner_model", "coder_model", "reviewer_model")
AVAILABLE_COLUMNS = (
    "available_planner_models",
    "available_coder_models",
    "available_reviewer_models",
)
LEGACY_OPENAI_COST_STATUS = "untrusted:openai_cached_input_double_counted"
_COST_LABEL_COLUMNS = ("actual_cost_usd", "under_budget", "budget_violation")
# Where each origin's costs came from, stamped as the row's price_table_version.
DERIVED_PRICE_SOURCE = "wavemill_record_pricing_snapshot"
LEGACY_PRICE_SOURCE = "wavemill_recorded_total"


def relabel_success_from_score(
    frame: pd.DataFrame, *, threshold: float = DEFAULT_SUCCESS_THRESHOLD
) -> tuple[pd.DataFrame, int]:
    """Return a copy with ``completed_successfully`` re-derived from ``score``.

    The May export predates wavemill ``3bbc1f5c`` ("finalize eval success from
    scores") and carries placeholder labels. A missing or non-numeric score
    becomes ``false``, matching the Wavemill policy.
    """
    out = frame.copy()
    score = pd.to_numeric(out["score"], errors="coerce")
    fixed = (score >= threshold).map({True: "true", False: "false"})
    original = out["completed_successfully"].astype(str).str.strip().str.lower()
    changed = int((fixed != original).sum())
    out["completed_successfully"] = fixed
    return out, changed


def _normalize_model_list(value: str) -> str:
    try:
        models = json.loads(value) if value else []
    except json.JSONDecodeError:
        return value
    if not isinstance(models, list):
        return value
    normalized = sorted({normalize_model_id(m) or m for m in models if is_supported_model_id(m)})
    return json.dumps(normalized, separators=(",", ":"))


def _normalize_model_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Rewrite role and available-model IDs to the serving catalog's public spelling."""
    out = frame.copy()
    for column in ROLE_COLUMNS:
        out[column] = out[column].map(lambda value: normalize_model_id(value) or value)
    for column in AVAILABLE_COLUMNS:
        if column in out.columns:
            out[column] = out[column].map(_normalize_model_list)
    return out


def quarantine_openai_legacy_costs(legacy: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Blank cost labels on legacy rows whose route includes an OpenAI model.

    Wavemill priced OpenAI usage with cached input counted twice (~5x real cost
    for Codex). Legacy rows carry only the recorded total, not tokens, so they
    cannot be repriced: their cost becomes unknown. Success labels are kept.
    """
    affected = pd.Series(False, index=legacy.index)
    for column in ROLE_COLUMNS:
        affected |= legacy[column].map(lambda m: model_family(m) == "openai")
    out = legacy.copy()
    for column in _COST_LABEL_COLUMNS:
        if column in out.columns:
            out.loc[affected, column] = ""
    if "cost_status" in out.columns:
        out.loc[affected, "cost_status"] = LEGACY_OPENAI_COST_STATUS
    return out, int(affected.sum())


def _dedupe_key(frame: pd.DataFrame) -> pd.Series:
    key = frame["timestamp"].astype(str).str[:19]
    for column in ROLE_COLUMNS:
        key = key + "|" + frame[column].astype(str)
    return key


def merge_router_exports(
    legacy: pd.DataFrame,
    derived: pd.DataFrame,
    *,
    threshold: float = DEFAULT_SUCCESS_THRESHOLD,
    legacy_source: str = "legacy_router_csv",
    derived_source: str = "derived_evals_jsonl",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Merge legacy and derived router rows, sorted by timestamp.

    Legacy rows duplicating a derived row (same second, same three models) are
    dropped so the derived row wins. The frame has a ``provenance_source`` column.
    """
    legacy_only = sorted(set(legacy.columns) - set(derived.columns))
    if legacy_only:
        raise ValueError(f"legacy and derived exports have different columns: {legacy_only}")
    # Derived rows carry newer columns (executed-route provenance, per-role
    # token economics). Legacy rows predate them, so leave them blank.
    legacy = legacy.copy()
    for column in derived.columns:
        if column not in legacy.columns:
            legacy[column] = ""
    legacy = _normalize_model_columns(legacy[list(derived.columns)])

    legacy, relabelled = relabel_success_from_score(legacy, threshold=threshold)
    legacy, openai_cost_quarantined = quarantine_openai_legacy_costs(legacy)
    duplicate = _dedupe_key(legacy).isin(set(_dedupe_key(derived)))
    legacy = legacy[~duplicate].assign(provenance_source=legacy_source)
    derived = derived.assign(provenance_source=derived_source)

    merged = pd.concat([legacy, derived], ignore_index=True)
    merged = merged.sort_values("timestamp", kind="stable").reset_index(drop=True)
    report = {
        "legacy_rows_in": int(len(legacy) + duplicate.sum()),
        "derived_rows_in": int(len(derived)),
        "legacy_success_relabelled": relabelled,
        "legacy_openai_costs_quarantined": openai_cost_quarantined,
        "legacy_duplicates_dropped": int(duplicate.sum()),
        "success_threshold": threshold,
        "merged_rows": int(len(merged)),
        "by_month": merged["timestamp"].astype(str).str[:7].value_counts().sort_index().to_dict(),
        "by_source": merged["provenance_source"].value_counts().to_dict(),
    }
    return merged, report


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_digest(roots: list[Path]) -> str:
    """One digest over every file under the eval snapshot roots (path + content)."""
    digest = hashlib.sha256()
    for root in roots:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            digest.update(str(path.relative_to(root)).encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _git_commit() -> str | None:
    try:
        return subprocess.run(  # noqa: S603  (fixed argv)
            ["git", "rev-parse", "HEAD"],  # noqa: S603, S607
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def convert(
    *,
    search_roots: list[Path],
    legacy_csv: Path,
    recovered_usage: Path | None,
    freeze_id: str,
    threshold: float = DEFAULT_SUCCESS_THRESHOLD,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return ``(canonical rows, manifest)`` for one freeze."""
    parse_freeze_id(freeze_id)
    usage = (
        json.loads(recovered_usage.read_text(encoding="utf-8")).get("records") or {}
        if recovered_usage
        else {}
    )
    derived_rows, derive_report, _ = derive_router_rows(search_roots, recovered_usage=usage)
    derived = pd.DataFrame(derived_rows, columns=FIELDNAMES).fillna("").astype(str)
    legacy = pd.read_csv(legacy_csv, dtype=str, keep_default_na=False)
    derived_origin = "derived:evals.jsonl"
    legacy_origin = f"legacy:{legacy_csv.name}"
    merged, merge_report = merge_router_exports(
        legacy,
        derived,
        threshold=threshold,
        legacy_source=legacy_origin,
        derived_source=derived_origin,
    )
    rows = [
        router_row_to_canonical(
            row,
            freeze_id=freeze_id,
            row_index=index,
            origin=row["provenance_source"],
            price_source=(
                DERIVED_PRICE_SOURCE
                if row["provenance_source"] == derived_origin
                else LEGACY_PRICE_SOURCE
            ),
        )
        for index, row in enumerate(merged.to_dict(orient="records"))
    ]
    manifest = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "freeze_id": freeze_id,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "rows": len(rows),
        "by_origin": dict(Counter(row["source"]["origin"] for row in rows)),
        "by_cost_status": dict(Counter(row["cost_status"] for row in rows)),
        "inputs": {
            "eval_snapshot_sha256": _snapshot_digest(search_roots),
            "recovered_usage_sha256": _sha256(recovered_usage) if recovered_usage else None,
            "recovered_usage_records": len(usage),
            "legacy_csv": legacy_csv.name,
            "legacy_csv_sha256": _sha256(legacy_csv),
        },
        "derive_report": {k: v for k, v in derive_report.items() if k != "source_files"},
        "merge_report": merge_report,
    }
    return rows, manifest


def write_freeze(output_dir: Path, rows: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    """Write ``rows.jsonl`` and ``manifest.json`` (with the rows file's digest)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = output_dir / "rows.jsonl"
    rows_path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest = {**manifest, "rows_sha256": _sha256(rows_path)}
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--search-root", action="append", required=True)
    parser.add_argument("--legacy-csv", required=True)
    parser.add_argument("--recovered-usage")
    parser.add_argument("--freeze-id", required=True, help="e.g. wavemill-2026-11-04")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--success-threshold", type=float, default=DEFAULT_SUCCESS_THRESHOLD)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    args = build_parser().parse_args(argv)
    rows, manifest = convert(
        search_roots=[Path(p).expanduser().resolve() for p in args.search_root],
        legacy_csv=Path(args.legacy_csv).expanduser().resolve(),
        recovered_usage=(
            Path(args.recovered_usage).expanduser().resolve() if args.recovered_usage else None
        ),
        freeze_id=args.freeze_id,
        threshold=args.success_threshold,
    )
    write_freeze(Path(args.output_dir).expanduser().resolve(), rows, manifest)
    summary = {k: manifest[k] for k in ("freeze_id", "rows", "by_origin", "by_cost_status")}
    print(json.dumps(summary))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
