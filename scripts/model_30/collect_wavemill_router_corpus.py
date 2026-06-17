"""Collect Model 30 router training rows from Wavemill-enabled repos."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.model_30.clean_router_dataset import clean_router_datasets  # noqa: E402

ROUTER_DATASET_SCHEMA_VERSION = "wavemill-hokusai-router-dataset-v1"
EVAL_FILENAME = "evals.jsonl"
ROUTER_CSV_PATTERNS = (
    "hokusai-router-dataset.csv",
    "*router-dataset*.csv",
)

FIELDNAMES = [
    "schema_version",
    "run_id_hash",
    "task_id_hash",
    "timestamp",
    "source_repo_hash",
    "is_challenge",
    "challenge_pair_hash",
    "task_type",
    "language",
    "domain",
    "complexity",
    "repo_size_bucket",
    "files_touched_bucket",
    "description_length_bucket",
    "is_greenfield",
    "is_migration",
    "requires_tests",
    "cross_service",
    "ui_heavy",
    "risk_level",
    "max_cost_usd",
    "available_planner_models",
    "available_coder_models",
    "available_reviewer_models",
    "planner_model",
    "planner_agent",
    "coder_model",
    "coder_agent",
    "reviewer_model",
    "reviewer_agent",
    "plan_depth",
    "code_depth",
    "review_mode",
    "route_source",
    "router_mode",
    "routing_mode",
    "expected_success_probability",
    "expected_cost_usd",
    "confidence",
    "risk_score",
    "completed_successfully",
    "score",
    "score_band",
    "under_budget",
    "actual_cost_usd",
    "actual_time_seconds",
    "intervention_count",
    "workflow_cost_status",
    "budget_violation",
    "rubric_version",
    "rubric_criterion_count",
    "rubric_mean_score",
    "rubric_completeness",
    "rubric_correctness",
    "rubric_code_quality",
    "rubric_intervention_impact",
    "rubric_autonomy",
    "rubric_determinative_boundary",
    "rubric_provenance",
]


def discover_wavemill_eval_files(
    search_roots: list[Path],
    *,
    include_worktrees: bool = False,
) -> list[Path]:
    """Return current Wavemill eval logs under the provided roots."""
    files: set[Path] = set()
    for root in search_roots:
        if root.is_file() and root.name == EVAL_FILENAME:
            files.add(root.resolve())
            continue
        if not root.exists():
            continue
        files.update(path.resolve() for path in root.glob(f"**/.wavemill/evals/{EVAL_FILENAME}"))
    return sorted(path for path in files if include_worktrees or not _is_worktree_path(path))


def discover_router_csv_exports(
    search_roots: list[Path],
    *,
    include_worktrees: bool = False,
) -> list[Path]:
    """Return prebuilt Wavemill router CSV exports under the provided roots."""
    files: set[Path] = set()
    for root in search_roots:
        if root.is_file() and root.suffix == ".csv":
            files.add(root.resolve())
            continue
        if not root.exists():
            continue
        for pattern in ROUTER_CSV_PATTERNS:
            files.update(path.resolve() for path in root.glob(f"**/.wavemill/evals/{pattern}"))
    return sorted(path for path in files if include_worktrees or not _is_worktree_path(path))


def collect_router_corpus(args: argparse.Namespace) -> dict[str, Any]:
    """Build a cleaned router corpus from discovered Wavemill artifacts."""
    raw_search_roots = args.search_root or [str(REPO_ROOT.parent)]
    search_roots = [Path(path).expanduser().resolve() for path in raw_search_roots]
    output_path = Path(args.output).expanduser().resolve()
    raw_output_path = (
        Path(args.raw_output).expanduser().resolve()
        if args.raw_output
        else output_path.with_name(f"{output_path.stem}.raw.csv")
    )

    eval_files = (
        discover_wavemill_eval_files(search_roots, include_worktrees=args.include_worktrees)
        if args.include_eval_jsonl
        else []
    )
    csv_exports = (
        discover_router_csv_exports(search_roots, include_worktrees=args.include_worktrees)
        if args.include_router_csv
        else []
    )
    csv_exports = [path for path in csv_exports if path != raw_output_path and path != output_path]
    csv_export_dirs = {path.parent for path in csv_exports}
    skipped_eval_files = []
    if not args.derive_when_router_csv_present:
        derivable_eval_files = []
        for eval_file in eval_files:
            if eval_file.parent in csv_export_dirs:
                skipped_eval_files.append(str(eval_file))
                continue
            derivable_eval_files.append(eval_file)
        eval_files = derivable_eval_files

    derived_rows: list[dict[str, str]] = []
    eval_report: dict[str, Any] = {
        "source_files": [],
        "records_read": 0,
        "rows_derived": 0,
        "records_skipped": 0,
        "files_skipped_existing_router_csv": skipped_eval_files,
        "skip_reasons": {},
    }
    skip_reasons: Counter[str] = Counter()
    for eval_file in eval_files:
        file_report = _derive_rows_from_eval_file(eval_file, derived_rows, skip_reasons)
        eval_report["source_files"].append(file_report)
        eval_report["records_read"] += file_report["records_read"]
        eval_report["rows_derived"] += file_report["rows_derived"]
        eval_report["records_skipped"] += file_report["records_skipped"]

    eval_report["skip_reasons"] = dict(sorted(skip_reasons.items()))

    input_paths: list[Path] = []
    if derived_rows:
        _write_router_csv(raw_output_path, derived_rows)
        input_paths.append(raw_output_path)
    input_paths.extend(csv_exports)
    if not input_paths:
        raise ValueError(
            "No Wavemill router corpus inputs found. Provide --search-root containing "
            ".wavemill/evals/evals.jsonl or router CSV exports."
        )

    clean_report_path = (
        Path(args.clean_report).expanduser().resolve()
        if args.clean_report
        else output_path.with_name(f"{output_path.stem}.clean-report.json")
    )
    clean_report = clean_router_datasets(input_paths, output_path, clean_report_path)
    report = {
        "schema_version": "model_30_wavemill_router_corpus/v1",
        "search_roots": [str(path) for path in search_roots],
        "eval_jsonl": eval_report,
        "router_csv_exports": [str(path) for path in csv_exports],
        "raw_output": str(raw_output_path) if derived_rows else None,
        "output": str(output_path),
        "clean_report": clean_report,
    }

    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def _derive_rows_from_eval_file(
    eval_file: Path,
    output_rows: list[dict[str, str]],
    skip_reasons: Counter[str],
) -> dict[str, Any]:
    source_repo = _source_repo_name(eval_file)
    file_report = {
        "path": str(eval_file),
        "source_repo": source_repo,
        "records_read": 0,
        "rows_derived": 0,
        "records_skipped": 0,
        "skip_reasons": {},
    }
    file_skip_reasons: Counter[str] = Counter()
    with eval_file.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            file_report["records_read"] += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                _record_skip("malformed_json", skip_reasons, file_skip_reasons)
                continue

            row, reason = eval_record_to_router_row(record, source_repo=source_repo)
            if reason is not None:
                _record_skip(reason, skip_reasons, file_skip_reasons)
                continue
            if row is None:
                _record_skip("empty_row", skip_reasons, file_skip_reasons)
                continue
            row["run_id_hash"] = _stable_hash(f"{eval_file}:{line_number}:{record.get('id', '')}")
            output_rows.append(row)
            file_report["rows_derived"] += 1

    file_report["records_skipped"] = sum(file_skip_reasons.values())
    file_report["skip_reasons"] = dict(sorted(file_skip_reasons.items()))
    return file_report


def eval_record_to_router_row(
    record: dict[str, Any],
    *,
    source_repo: str,
) -> tuple[dict[str, str] | None, str | None]:
    """Convert one Wavemill eval record to the router training CSV row shape."""
    if not (record.get("trainingEligible") or record.get("budgetEvalEligible")):
        return None, "not_training_or_budget_eligible"

    task_descriptor = _dict(record.get("taskDescriptor"))
    stages = _dict(task_descriptor.get("stages"))
    if not stages:
        stages = _dict(_dict(record.get("routeProvenance")).get("activeRoute"))
    route_prediction = _dict(record.get("routePrediction"))
    constraints = _dict(task_descriptor.get("constraints")) or _dict(record.get("constraints"))
    heuristic = _dict(_dict(task_descriptor.get("signals")).get("heuristic"))
    learned = _dict(_dict(task_descriptor.get("signals")).get("learned"))
    task_context = _dict(record.get("taskContext"))
    repo_context = _dict(record.get("repoContext"))
    outcome = _dict(record.get("outcome"))
    outcomes = _dict(record.get("outcomes"))
    rubric = _dict(task_descriptor.get("rubric")) or _dict(record.get("rubricEval"))
    rubric_criteria = _dict(_dict(rubric.get("criteria_scores")) or _dict(rubric.get("criteria")))

    planner_model = _stage_model(stages, "planner")
    coder_model = _stage_model(stages, "coder") or _string(record.get("modelId"))
    reviewer_model = _stage_model(stages, "reviewer")
    if not planner_model or not coder_model or not reviewer_model:
        return None, "missing_stage_model"

    available_models = _string_list(
        constraints.get("models_available") or constraints.get("allowed_models")
    )
    if not available_models:
        return None, "missing_available_models"

    max_cost = _number(constraints.get("max_cost_usd") or record.get("maxCostUsd"))
    if max_cost is None:
        max_cost = _number(_dict(record.get("constraints")).get("maxCostUsd"))
    if max_cost is None or max_cost <= 0:
        max_cost = 25.0

    actual_cost = _first_number(
        record.get("workflowCost"),
        outcome.get("total_cost_usd"),
        record.get("estimatedCost"),
        route_prediction.get("expectedCostUsd"),
    )
    if actual_cost is None:
        actual_cost = 0.0

    score = _first_number(
        record.get("score"),
        outcome.get("overall_score"),
        rubric.get("mean_score"),
    )
    if score is None:
        score = 1.0 if _completed_successfully(record, outcomes) else 0.0

    task_type = _first_string(
        heuristic.get("task_type"),
        route_prediction.get("taskType"),
        task_context.get("taskType"),
        "unknown",
    )
    language = _first_string(_first_item(heuristic.get("languages")), "unknown")
    domain = _first_string(
        learned.get("domain"),
        task_context.get("requiresDomainKnowledge"),
        "unknown",
    )
    complexity = _first_number(learned.get("complexity"), route_prediction.get("complexityScore"))
    files_touched = _first_number(
        heuristic.get("files_touched"),
        _dict(record.get("difficultySignals")).get("filesTouched"),
    )
    risk_score = _first_number(
        route_prediction.get("riskScore"),
        _dict(record.get("difficultySignals")).get("riskScore"),
    )
    timestamp = _first_string(record.get("timestamp"), record.get("observed_at"), "")

    row = {
        "schema_version": ROUTER_DATASET_SCHEMA_VERSION,
        "run_id_hash": "",
        "task_id_hash": _stable_hash(_first_string(record.get("id"), record.get("issueId"), "")),
        "timestamp": timestamp,
        "source_repo_hash": _stable_hash(source_repo),
        "is_challenge": _bool_string(bool(record.get("challengePairId"))),
        "challenge_pair_hash": _stable_hash(_string(record.get("challengePairId"))),
        "task_type": task_type,
        "language": language,
        "domain": domain,
        "complexity": _format_number(complexity) if complexity is not None else "",
        "repo_size_bucket": _repo_size_bucket(repo_context),
        "files_touched_bucket": _files_bucket(files_touched),
        "description_length_bucket": _description_length_bucket(record.get("originalPrompt")),
        "is_greenfield": _bool_string(heuristic.get("is_greenfield")),
        "is_migration": _bool_string(heuristic.get("has_migration")),
        "requires_tests": _bool_string(heuristic.get("has_tests")),
        "cross_service": _bool_string(heuristic.get("cross_service")),
        "ui_heavy": _bool_string(heuristic.get("has_ui")),
        "risk_level": _risk_level(risk_score),
        "max_cost_usd": _format_number(max_cost),
        "available_planner_models": _json_list(available_models),
        "available_coder_models": _json_list(available_models),
        "available_reviewer_models": _json_list(available_models),
        "planner_model": planner_model,
        "planner_agent": _agent_for_model(planner_model),
        "coder_model": coder_model,
        "coder_agent": _agent_for_model(coder_model),
        "reviewer_model": reviewer_model,
        "reviewer_agent": _agent_for_model(reviewer_model),
        "plan_depth": _first_string(stages.get("planDepth"), record.get("planDepth"), ""),
        "code_depth": _first_string(stages.get("codeDepth"), record.get("codeDepth"), ""),
        "review_mode": _first_string(stages.get("reviewMode"), record.get("reviewMode"), ""),
        "route_source": _first_string(
            _dict(record.get("routeProvenance")).get("decisionSource"),
            "",
        ),
        "router_mode": _first_string(_dict(record.get("routeProvenance")).get("routerMode"), ""),
        "routing_mode": _first_string(_dict(record.get("routeProvenance")).get("routingMode"), ""),
        "expected_success_probability": _format_optional_number(
            route_prediction.get("expectedSuccess")
        ),
        "expected_cost_usd": _format_optional_number(route_prediction.get("expectedCostUsd")),
        "confidence": _format_optional_number(route_prediction.get("confidence")),
        "risk_score": _format_optional_number(risk_score),
        "completed_successfully": _bool_string(_completed_successfully(record, outcomes)),
        "score": _format_number(score),
        "score_band": _first_string(record.get("scoreBand"), ""),
        "under_budget": _bool_string(actual_cost <= max_cost),
        "actual_cost_usd": _format_number(actual_cost),
        "actual_time_seconds": _format_optional_number(_duration_seconds(record, outcome)),
        "intervention_count": _format_optional_number(record.get("interventionCount")),
        "workflow_cost_status": _first_string(record.get("workflowCostStatus"), ""),
        "budget_violation": _bool_string(actual_cost > max_cost),
        "rubric_version": _first_string(rubric.get("rubric_version"), ""),
        "rubric_criterion_count": _format_optional_number(
            rubric.get("criterion_count") or len(rubric_criteria)
        ),
        "rubric_mean_score": _format_optional_number(
            rubric.get("mean_score") or _mean_rubric_score(rubric_criteria)
        ),
        "rubric_completeness": _format_optional_number(
            _rubric_score(rubric_criteria, "completeness")
        ),
        "rubric_correctness": _format_optional_number(
            _rubric_score(rubric_criteria, "correctness")
        ),
        "rubric_code_quality": _format_optional_number(
            _rubric_score(rubric_criteria, "code_quality")
        ),
        "rubric_intervention_impact": _format_optional_number(
            _rubric_score(rubric_criteria, "intervention_impact")
        ),
        "rubric_autonomy": _format_optional_number(_rubric_score(rubric_criteria, "autonomy")),
        "rubric_determinative_boundary": _first_string(
            rubric.get("determinative_boundary"),
            "",
        ),
        "rubric_provenance": "wavemill-evals-jsonl",
    }
    return row, None


def _write_router_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _record_skip(reason: str, global_counter: Counter[str], file_counter: Counter[str]) -> None:
    global_counter[reason] += 1
    file_counter[reason] += 1


def _source_repo_name(path: Path) -> str:
    parts = path.resolve().parts
    if ".wavemill" not in parts:
        return path.parent.name
    index = parts.index(".wavemill")
    return parts[index - 1] if index > 0 else path.parent.name


def _is_worktree_path(path: Path) -> bool:
    return "worktrees" in path.resolve().parts


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _first_string(*values: Any) -> str:
    for value in values:
        text = _string(value)
        if text:
            return text
    return ""


def _first_item(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return sorted({str(item).strip() for item in value if str(item).strip()})
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value.strip()]
        return _string_list(parsed)
    return []


def _stage_model(stages: dict[str, Any], role: str) -> str:
    stage = _dict(stages.get(role))
    return _first_string(stage.get("model"), stages.get(f"{role}_model"))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first_number(*values: Any) -> float | None:
    for value in values:
        number = _number(value)
        if number is not None:
            return number
    return None


def _format_number(value: Any) -> str:
    number = _number(value)
    if number is None:
        return ""
    return f"{number:g}"


def _format_optional_number(value: Any) -> str:
    return _format_number(value)


def _json_list(values: list[str]) -> str:
    return json.dumps(values, separators=(",", ":"))


def _bool_string(value: Any) -> str:
    if isinstance(value, str):
        return "true" if value.strip().lower() in {"1", "true", "yes", "y"} else "false"
    return "true" if bool(value) else "false"


def _stable_hash(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _repo_size_bucket(repo_context: dict[str, Any]) -> str:
    loc = _number(_dict(repo_context.get("repoSize")).get("loc"))
    if loc is None:
        return "unknown"
    if loc < 25_000:
        return "small"
    if loc < 150_000:
        return "medium"
    return "large"


def _files_bucket(value: Any) -> str:
    count = _number(value)
    if count is None:
        return "unknown"
    if count <= 1:
        return "1"
    if count <= 5:
        return "2_5"
    if count <= 15:
        return "6_15"
    return "16_plus"


def _description_length_bucket(value: Any) -> str:
    token_count = len(_string(value).split())
    if token_count <= 200:
        return "short"
    if token_count <= 1000:
        return "medium"
    return "long"


def _risk_level(value: Any) -> str:
    risk_score = _number(value)
    if risk_score is None:
        return "unknown"
    if risk_score < 6:
        return "low"
    if risk_score < 14:
        return "medium"
    return "high"


def _agent_for_model(model_id: str) -> str:
    if model_id.startswith("claude-"):
        return "claude"
    if model_id.startswith("gpt-"):
        return "codex"
    if model_id.startswith("deepseek-"):
        return "deepseek"
    return "unknown"


def _completed_successfully(record: dict[str, Any], outcomes: dict[str, Any]) -> bool:
    if isinstance(outcomes.get("success"), bool):
        return bool(outcomes["success"])
    score = _number(record.get("score"))
    if score is not None:
        return score >= 0.7
    return bool(record.get("trainingEligible") or record.get("budgetEvalEligible"))


def _duration_seconds(record: dict[str, Any], outcome: dict[str, Any]) -> float | None:
    duration = _first_number(
        record.get("timeSeconds"),
        _dict(record.get("phaseDurationsSeconds")).get("total"),
    )
    if duration is not None:
        return duration
    minutes = _number(outcome.get("total_time_minutes"))
    return minutes * 60.0 if minutes is not None else None


def _rubric_score(criteria: dict[str, Any], key: str) -> float | None:
    value = criteria.get(key)
    if isinstance(value, dict):
        return _number(value.get("score"))
    return _number(value)


def _mean_rubric_score(criteria: dict[str, Any]) -> float | None:
    scores = [
        score for score in (_rubric_score(criteria, key) for key in criteria) if score is not None
    ]
    return sum(scores) / len(scores) if scores else None


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--search-root",
        action="append",
        default=None,
        help=(
            "Repo parent or file to scan. Defaults to the parent directory containing "
            "Hokusai repos. Repeat to scan multiple roots."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Cleaned router dataset CSV output path.",
    )
    parser.add_argument("--raw-output", help="Optional raw derived eval CSV output path.")
    parser.add_argument("--clean-report", help="Optional cleaner report path.")
    parser.add_argument("--report", help="Optional combined corpus report JSON path.")
    parser.add_argument(
        "--no-eval-jsonl",
        dest="include_eval_jsonl",
        action="store_false",
        help="Skip deriving rows from .wavemill/evals/evals.jsonl files.",
    )
    parser.add_argument(
        "--no-router-csv",
        dest="include_router_csv",
        action="store_false",
        help="Skip existing router CSV exports discovered under .wavemill/evals.",
    )
    parser.add_argument(
        "--derive-when-router-csv-present",
        action="store_true",
        help=(
            "Also derive rows from evals.jsonl when the same .wavemill/evals directory "
            "already contains a router CSV export. Defaults off to avoid double-counting."
        ),
    )
    parser.add_argument(
        "--include-worktrees",
        action="store_true",
        help="Include Wavemill data under directories named worktrees. Defaults off.",
    )
    parser.set_defaults(include_eval_jsonl=True, include_router_csv=True)
    return parser.parse_args()


def main() -> None:
    """Run the Wavemill corpus collector."""
    report = collect_router_corpus(parse_args())
    print(json.dumps(report, indent=2, sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()
