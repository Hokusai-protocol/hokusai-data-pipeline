"""Create canonical train/holdout splits for Model 30 router benchmarks."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.model_30.evaluate_technical_task_router import _quarantine_reason  # noqa: E402
from scripts.model_30.register_technical_task_router import _parse_model_values  # noqa: E402

DEFAULT_HOLDOUT_FRACTION = 0.30
DEFAULT_SEED = "model-30-v2-canonical-benchmark-2026-06"
LEGACY_DEFAULT_MAX_COST_USD = 25.0
GROUP_COLUMNS = ("source_repo_hash", "task_id_hash", "run_id_hash")
STRATIFY_COLUMNS = ("task_type", "domain", "complexity")
REPAIR_COLUMNS = (
    "max_cost_usd_source",
    "available_models_repair",
    "repair_reasons",
    "initial_quarantine_reason",
)
ROLE_MODEL_COLUMNS = {
    "planner": ("planner_model", "available_planner_models"),
    "coder": ("coder_model", "available_coder_models"),
    "reviewer": ("reviewer_model", "available_reviewer_models"),
}


@dataclass(frozen=True)
class _Group:
    key: str
    stratum: tuple[str, ...]
    rows: list[dict[str, str]]

    @property
    def size(self: _Group) -> int:
        return len(self.rows)


def split_router_benchmark(
    input_path: Path,
    train_path: Path,
    holdout_path: Path,
    *,
    quarantine_path: Path | None = None,
    report_path: Path | None = None,
    holdout_fraction: float = DEFAULT_HOLDOUT_FRACTION,
    seed: str = DEFAULT_SEED,
    repair_mode: str = "none",
) -> dict[str, Any]:
    """Write deterministic grouped train/holdout CSVs from valid benchmark rows."""
    if not 0 < holdout_fraction < 1:
        raise ValueError("--holdout-fraction must be greater than 0 and less than 1")
    if repair_mode not in {"none", "conservative"}:
        raise ValueError("--repair-mode must be one of: none, conservative")

    rows, fieldnames = _read_rows(input_path)
    output_fieldnames = _output_fieldnames(fieldnames, repair_mode=repair_mode)
    valid_rows: list[dict[str, str]] = []
    quarantined_rows: list[dict[str, str]] = []
    initial_quarantine_reasons: Counter[str] = Counter()
    quarantine_reasons: Counter[str] = Counter()
    repair_reasons: Counter[str] = Counter()
    for row in rows:
        row_copy = dict(row)
        initial_reason = _quarantine_reason(row_copy)
        if initial_reason is not None:
            initial_quarantine_reasons[initial_reason] += 1
        if repair_mode == "conservative":
            row_copy, row_repair_reasons = _repair_row(row_copy, initial_reason=initial_reason)
            repair_reasons.update(row_repair_reasons)
        reason = _quarantine_reason(row_copy)
        if reason is None:
            valid_rows.append(row_copy)
        else:
            quarantine_reasons[reason] += 1
            quarantined_rows.append({**row_copy, "quarantine_reason": reason})

    if not valid_rows:
        raise ValueError(f"No valid benchmark rows found in {input_path}")

    train_rows, holdout_rows, groups = _split_valid_rows(
        valid_rows,
        holdout_fraction=holdout_fraction,
        seed=seed,
    )
    _write_rows(train_path, output_fieldnames, train_rows)
    _write_rows(holdout_path, output_fieldnames, holdout_rows)
    if quarantine_path is not None:
        _write_rows(quarantine_path, [*output_fieldnames, "quarantine_reason"], quarantined_rows)

    report = _build_report(
        input_path=input_path,
        train_path=train_path,
        holdout_path=holdout_path,
        quarantine_path=quarantine_path,
        total_rows=len(rows),
        valid_rows=valid_rows,
        quarantined_rows=quarantined_rows,
        train_rows=train_rows,
        holdout_rows=holdout_rows,
        groups=groups,
        holdout_fraction=holdout_fraction,
        seed=seed,
        repair_mode=repair_mode,
        initial_quarantine_reasons=initial_quarantine_reasons,
        quarantine_reasons=quarantine_reasons,
        repair_reasons=repair_reasons,
    )
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return report


def _read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Router dataset has no CSV header: {path}")
        return list(reader), list(reader.fieldnames)


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _output_fieldnames(fieldnames: list[str], *, repair_mode: str) -> list[str]:
    if repair_mode == "none":
        return fieldnames
    return [*fieldnames, *[column for column in REPAIR_COLUMNS if column not in fieldnames]]


def _repair_row(
    row: dict[str, str],
    *,
    initial_reason: str | None,
) -> tuple[dict[str, str], list[str]]:
    repaired = dict(row)
    repair_reasons: list[str] = []
    repaired["initial_quarantine_reason"] = initial_reason or ""
    repaired["max_cost_usd_source"] = "observed" if _positive_float(row.get("max_cost_usd")) else ""
    repaired["available_models_repair"] = "none"

    if _can_infer_legacy_default_budget(repaired):
        repaired["max_cost_usd"] = _format_float(LEGACY_DEFAULT_MAX_COST_USD)
        repaired["max_cost_usd_source"] = "inferred_legacy_default"
        repair_reasons.append("max_cost_usd:inferred_legacy_default")
    elif not _positive_float(repaired.get("max_cost_usd")):
        repaired["max_cost_usd_source"] = "missing"

    added_roles: list[str] = []
    for role, (selected_column, available_column) in ROLE_MODEL_COLUMNS.items():
        selected_model = str(repaired.get(selected_column) or "").strip()
        if not selected_model:
            continue
        available_models = _safe_parse_model_values(repaired.get(available_column, ""))
        if selected_model not in available_models:
            available_models.append(selected_model)
            repaired[available_column] = json.dumps(
                sorted(set(available_models)),
                separators=(",", ":"),
            )
            added_roles.append(role)

    if added_roles:
        repaired["available_models_repair"] = "added_selected_model"
        for role in added_roles:
            repair_reasons.append(f"available_{role}_models:added_selected_model")

    repaired["repair_reasons"] = json.dumps(repair_reasons, separators=(",", ":"))
    return repaired, repair_reasons


def _can_infer_legacy_default_budget(row: dict[str, str]) -> bool:
    if _positive_float(row.get("max_cost_usd")) is not None:
        return False
    actual_cost = _positive_float(row.get("actual_cost_usd"))
    if actual_cost is None or actual_cost > LEGACY_DEFAULT_MAX_COST_USD:
        return False
    return str(row.get("budget_violation") or "").strip().lower() == "false"


def _positive_float(value: str | None) -> float | None:
    try:
        parsed = float(str(value or "").strip())
    except ValueError:
        return None
    if parsed <= 0:
        return None
    return parsed


def _format_float(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)


def _safe_parse_model_values(value: str) -> list[str]:
    try:
        return _parse_model_values(value)
    except (json.JSONDecodeError, ValueError):
        return []


def _split_valid_rows(
    rows: list[dict[str, str]],
    *,
    holdout_fraction: float,
    seed: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[_Group]]:
    groups_by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups_by_key[_group_key(row, index)].append(row)

    groups = [
        _Group(key=key, stratum=_stratum(group_rows[0]), rows=group_rows)
        for key, group_rows in groups_by_key.items()
    ]
    groups_by_stratum: dict[tuple[str, ...], list[_Group]] = defaultdict(list)
    for group in groups:
        groups_by_stratum[group.stratum].append(group)

    holdout_group_keys: set[str] = set()
    for stratum, stratum_groups in groups_by_stratum.items():
        stratum_total = sum(group.size for group in stratum_groups)
        target = _target_holdout_rows(stratum_total, holdout_fraction)
        selected = 0
        for group in sorted(
            stratum_groups,
            key=lambda item: _stable_digest(f"{seed}|{stratum}|{item.key}"),
        ):
            if selected >= target:
                break
            holdout_group_keys.add(group.key)
            selected += group.size

    train_rows: list[dict[str, str]] = []
    holdout_rows: list[dict[str, str]] = []
    for group in sorted(groups, key=lambda item: _stable_digest(f"{seed}|output|{item.key}")):
        if group.key in holdout_group_keys:
            holdout_rows.extend(group.rows)
        else:
            train_rows.extend(group.rows)

    if not train_rows or not holdout_rows:
        raise ValueError("Split produced an empty train or holdout set")
    return train_rows, holdout_rows, groups


def _target_holdout_rows(total_rows: int, holdout_fraction: float) -> int:
    if total_rows <= 1:
        return 0
    return max(1, round(total_rows * holdout_fraction))


def _group_key(row: dict[str, str], index: int) -> str:
    source_repo_hash = str(row.get("source_repo_hash") or "").strip()
    task_id_hash = str(row.get("task_id_hash") or "").strip()
    run_id_hash = str(row.get("run_id_hash") or "").strip()
    if source_repo_hash and task_id_hash:
        return f"{source_repo_hash}|{task_id_hash}"
    if task_id_hash:
        return f"task|{task_id_hash}"
    if run_id_hash:
        return f"run|{run_id_hash}"
    return f"row:{index}"


def _stratum(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(_normalized_cell(row.get(column)) for column in STRATIFY_COLUMNS)


def _normalized_cell(value: str | None) -> str:
    stripped = (value or "").strip().lower()
    return stripped or "unknown"


def _stable_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _build_report(
    *,
    input_path: Path,
    train_path: Path,
    holdout_path: Path,
    quarantine_path: Path | None,
    total_rows: int,
    valid_rows: list[dict[str, str]],
    quarantined_rows: list[dict[str, str]],
    train_rows: list[dict[str, str]],
    holdout_rows: list[dict[str, str]],
    groups: list[_Group],
    holdout_fraction: float,
    seed: str,
    repair_mode: str,
    initial_quarantine_reasons: Counter[str],
    quarantine_reasons: Counter[str],
    repair_reasons: Counter[str],
) -> dict[str, Any]:
    return {
        "input_dataset": str(input_path),
        "input_dataset_sha256": _file_sha256(input_path),
        "train_dataset": str(train_path),
        "train_dataset_sha256": _file_sha256(train_path),
        "holdout_dataset": str(holdout_path),
        "holdout_dataset_sha256": _file_sha256(holdout_path),
        "quarantine_dataset": str(quarantine_path) if quarantine_path is not None else None,
        "quarantine_dataset_sha256": (
            _file_sha256(quarantine_path) if quarantine_path is not None else None
        ),
        "seed": seed,
        "holdout_fraction": holdout_fraction,
        "repair_mode": repair_mode,
        "split_strategy": {
            "validity_filter": "scripts.model_30.evaluate_technical_task_router._quarantine_reason",
            "group_columns": list(GROUP_COLUMNS),
            "stratify_columns": list(STRATIFY_COLUMNS),
            "legacy_default_max_cost_usd": LEGACY_DEFAULT_MAX_COST_USD,
        },
        "row_counts": {
            "input_rows": total_rows,
            "valid_rows": len(valid_rows),
            "quarantined_rows": len(quarantined_rows),
            "train_rows": len(train_rows),
            "holdout_rows": len(holdout_rows),
            "actual_holdout_fraction": len(holdout_rows) / len(valid_rows),
        },
        "group_counts": _group_counts(groups, train_rows, holdout_rows),
        "initial_quarantine_reasons": dict(sorted(initial_quarantine_reasons.items())),
        "quarantine_reasons": dict(sorted(quarantine_reasons.items())),
        "repair_reasons": dict(sorted(repair_reasons.items())),
        "distributions": {
            column: {
                "train": _distribution(train_rows, column),
                "holdout": _distribution(holdout_rows, column),
                "valid": _distribution(valid_rows, column),
            }
            for column in STRATIFY_COLUMNS
        },
    }


def _group_counts(
    groups: list[_Group],
    train_rows: list[dict[str, str]],
    holdout_rows: list[dict[str, str]],
) -> dict[str, int]:
    train_ids = {id(row) for row in train_rows}
    holdout_ids = {id(row) for row in holdout_rows}
    train_groups = 0
    holdout_groups = 0
    for group in groups:
        ids = {id(row) for row in group.rows}
        if ids & train_ids:
            train_groups += 1
        if ids & holdout_ids:
            holdout_groups += 1
    return {
        "valid_groups": len(groups),
        "train_groups": train_groups,
        "holdout_groups": holdout_groups,
    }


def _distribution(rows: list[dict[str, str]], column: str) -> dict[str, int]:
    counts = Counter(_normalized_cell(row.get(column)) for row in rows)
    return dict(sorted(counts.items()))


def _file_sha256(path: Path | None) -> str | None:
    if path is None:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Cleaned router dataset CSV")
    parser.add_argument("--train-output", required=True, help="Training CSV output path")
    parser.add_argument("--holdout-output", required=True, help="Holdout CSV output path")
    parser.add_argument("--quarantine-output", help="Optional CSV of rows excluded from benchmark")
    parser.add_argument("--report", help="Optional JSON split report path")
    parser.add_argument(
        "--holdout-fraction",
        type=float,
        default=DEFAULT_HOLDOUT_FRACTION,
        help=f"Target holdout fraction among valid rows; default {DEFAULT_HOLDOUT_FRACTION}",
    )
    parser.add_argument(
        "--seed",
        default=DEFAULT_SEED,
        help="Stable split seed; changing it changes train/holdout assignment",
    )
    parser.add_argument(
        "--repair-mode",
        choices=("none", "conservative"),
        default="none",
        help=(
            "Optionally recover benchmark rows with provenance. conservative adds selected "
            "models back to available pools and infers the legacy $25 budget only when "
            "budget_violation=false and actual_cost_usd <= 25."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the splitter CLI."""
    args = build_parser().parse_args(argv)
    report = split_router_benchmark(
        Path(args.input).expanduser().resolve(),
        Path(args.train_output).expanduser().resolve(),
        Path(args.holdout_output).expanduser().resolve(),
        quarantine_path=(
            Path(args.quarantine_output).expanduser().resolve() if args.quarantine_output else None
        ),
        report_path=Path(args.report).expanduser().resolve() if args.report else None,
        holdout_fraction=args.holdout_fraction,
        seed=args.seed,
        repair_mode=args.repair_mode,
    )
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
