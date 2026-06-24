"""Run repeatable contribution retraining workflows.

The workflow is intentionally model-configured. Model 30 is the first adapter:
it assembles accepted contribution rows, converts the assembler JSONL into the
router CSV expected by the existing trainer, then composes the existing train,
evaluate, attribution, and promotion scripts behind explicit stages.
"""
# ruff: noqa: ANN101, D103, S603

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

STAGES = ("plan", "assemble", "prepare", "train", "evaluate", "attribute", "promote", "all")
RUN_MANIFEST = "run_manifest.json"


def router_fieldnames() -> list[str]:
    from scripts.model_30.collect_wavemill_router_corpus import FIELDNAMES

    if "task_description" in FIELDNAMES:
        return list(FIELDNAMES)
    return [*FIELDNAMES, "task_description"]


@dataclass(frozen=True)
class WorkflowConfig:
    """Validated contribution-training workflow configuration."""

    raw: dict[str, Any]
    path: Path

    @property
    def model_id(self) -> str:
        return str(self.raw["model_id"])

    @property
    def run_name(self) -> str:
        return str(self.raw.get("run_name") or f"model-{self.model_id}-contribution-training")

    @property
    def output_dir(self) -> Path:
        return Path(str(self.raw["output_dir"])).expanduser().resolve()

    @property
    def model_config(self) -> dict[str, Any]:
        return dict(self.raw.get(f"model_{self.model_id}") or {})


def load_config(path: Path) -> WorkflowConfig:
    """Load and minimally validate a JSON workflow config."""
    raw = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    required = ("model_id", "as_of", "output_dir", "s3_bucket", "holdout_dataset")
    missing = [key for key in required if not raw.get(key)]
    if missing:
        raise ValueError(f"Workflow config is missing required keys: {missing}")
    model_id = str(raw["model_id"])
    if model_id != "30":
        raise ValueError(f"Unsupported contribution training model_id: {model_id}")
    return WorkflowConfig(raw=raw, path=path.expanduser().resolve())


def _json_list(values: Any) -> str:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        values = []
    return json.dumps([str(value) for value in values if str(value)], separators=(",", ":"))


def _descriptor(row: dict[str, Any]) -> dict[str, Any]:
    descriptor = row.get("task_descriptor")
    return descriptor if isinstance(descriptor, dict) else {}


def _descriptor_text(descriptor: dict[str, Any], row: dict[str, Any]) -> str:
    for key in ("description", "task_description", "title", "prompt"):
        value = descriptor.get(key) or row.get(key)
        if value:
            return str(value)
    return json.dumps(descriptor, sort_keys=True, separators=(",", ":"))


def _selected_by_role(selected_models: list[str]) -> tuple[str, str, str]:
    if not selected_models:
        return "", "", ""
    if len(selected_models) == 1:
        return selected_models[0], selected_models[0], selected_models[0]
    if len(selected_models) == 2:
        return selected_models[0], selected_models[1], selected_models[1]
    return selected_models[0], selected_models[1], selected_models[2]


def _optional_number(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def contribution_row_to_router_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert an assembled Model 30 contribution row into router-training CSV shape."""
    descriptor = _descriptor(row)
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    allowed_models = [str(value) for value in row.get("allowed_models", []) if str(value)]
    selected_models = [str(value) for value in row.get("selected_models", []) if str(value)]
    planner_model, coder_model, reviewer_model = _selected_by_role(selected_models)
    expected_success = row.get("estimated_success_under_budget")
    if expected_success is None:
        expected_success = 1.0 if row.get("completed_successfully") is True else 0.0
    max_cost = row.get("max_cost_usd")
    actual_cost = row.get("actual_cost_usd")
    under_budget = (
        isinstance(max_cost, (int, float))
        and isinstance(actual_cost, (int, float))
        and actual_cost <= max_cost
    )
    completed = row.get("completed_successfully") is True
    score = 1.0 if completed and under_budget else 0.0

    converted = {field: "" for field in router_fieldnames()}
    converted.update(
        {
            "schema_version": "wavemill-hokusai-router-dataset-v1",
            "run_id_hash": str(row.get("eval_id", "")),
            "task_id_hash": str(row.get("row_id", "")),
            "timestamp": str(row.get("observed_at", "")),
            "task_type": str(descriptor.get("task_type") or metadata.get("task_type") or "unknown"),
            "language": str(descriptor.get("language") or metadata.get("language") or "unknown"),
            "domain": str(descriptor.get("domain") or metadata.get("domain") or "backend"),
            "complexity": str(
                descriptor.get("complexity")
                or descriptor.get("estimated_complexity")
                or metadata.get("complexity")
                or ""
            ),
            "repo_size_bucket": str(
                descriptor.get("repo_size_bucket") or metadata.get("repo_size_bucket") or "medium"
            ),
            "description_length_bucket": "medium",
            "requires_tests": str(
                descriptor.get("requires_tests") or metadata.get("requires_tests") or False
            ).lower(),
            "risk_level": str(descriptor.get("risk_level") or metadata.get("risk_level") or "low"),
            "max_cost_usd": _optional_number(max_cost),
            "available_planner_models": _json_list(allowed_models),
            "available_coder_models": _json_list(allowed_models),
            "available_reviewer_models": _json_list(allowed_models),
            "planner_model": planner_model,
            "coder_model": coder_model,
            "reviewer_model": reviewer_model,
            "route_source": "contribution",
            "expected_success_probability": _optional_number(expected_success),
            "expected_cost_usd": _optional_number(row.get("estimated_cost_usd") or actual_cost),
            "confidence": _optional_number(expected_success),
            "completed_successfully": str(completed).lower(),
            "score": str(score),
            "under_budget": str(under_budget).lower(),
            "actual_cost_usd": _optional_number(actual_cost),
            "actual_time_seconds": _optional_number(row.get("actual_time_seconds")),
        }
    )
    converted["task_description"] = _descriptor_text(descriptor, row)
    return converted


def convert_jsonl_to_router_csv(jsonl_path: Path, csv_path: Path) -> dict[str, Any]:
    """Convert assembler output JSONL into the CSV consumed by Model 30 trainer."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0
    with (
        jsonl_path.open(encoding="utf-8") as source,
        csv_path.open("w", newline="", encoding="utf-8") as target,
    ):
        writer = csv.DictWriter(target, fieldnames=router_fieldnames(), extrasaction="ignore")
        writer.writeheader()
        for line in source:
            if not line.strip():
                continue
            writer.writerow(contribution_row_to_router_csv_row(json.loads(line)))
            rows_written += 1
    return {
        "input_path": str(jsonl_path),
        "output_path": str(csv_path),
        "rows_written": rows_written,
    }


def _stage_dir(config: WorkflowConfig, stage: str) -> Path:
    return config.output_dir / stage


def run_assemble(config: WorkflowConfig) -> dict[str, Any]:
    from scripts.model_30 import assemble_training_set

    output_dir = _stage_dir(config, "assembled")
    args = SimpleNamespace(
        as_of=str(config.raw["as_of"]),
        model_id=config.model_id,
        s3_bucket=str(config.raw["s3_bucket"]),
        s3_prefix=str(config.raw.get("s3_prefix") or ""),
        output_dir=str(output_dir),
        on_missing_wallet=str(config.raw.get("on_missing_wallet") or "hold"),
        mlflow_run_id=None,
        mlflow_tracking_uri=config.raw.get("mlflow_tracking_uri"),
        row_schema=str(REPO_ROOT / "schema" / "technical_task_router_row.v1.json"),
    )
    return assemble_training_set.assemble(args)


def run_prepare(config: WorkflowConfig) -> dict[str, Any]:
    dataset_jsonl = _stage_dir(config, "assembled") / "dataset.jsonl"
    dataset_csv = _stage_dir(config, "assembled") / str(
        config.model_config.get("router_dataset_filename") or "dataset.csv"
    )
    return convert_jsonl_to_router_csv(dataset_jsonl, dataset_csv)


def run_train(config: WorkflowConfig) -> dict[str, Any]:
    from scripts.model_30.register_technical_task_router import register_model

    dataset_csv = _stage_dir(config, "assembled") / str(
        config.model_config.get("router_dataset_filename") or "dataset.csv"
    )
    args = SimpleNamespace(
        router_dataset=str(dataset_csv),
        tracking_uri=config.raw.get("mlflow_tracking_uri"),
        experiment_name=config.raw.get("mlflow_experiment_name"),
        run_name=config.run_name,
        k_neighbors=int(config.model_config.get("k_neighbors") or 40),
        holdout_dataset=str(Path(str(config.raw["holdout_dataset"])).expanduser().resolve()),
        evaluation_objectives=str(config.model_config.get("evaluation_objectives") or "all"),
        benchmark_version=str(config.raw.get("benchmark_version") or "v2"),
        primary_metric=config.raw.get("primary_metric"),
        benchmark_spec_id=config.raw.get("benchmark_spec_id"),
        in_pool_coverage_gate=str(config.raw.get("in_pool_coverage_gate") or "warn"),
        min_in_pool_evidence_coverage=float(
            config.raw.get("min_in_pool_evidence_coverage") or 0.70
        ),
        min_group_in_pool_evidence_coverage=float(
            config.raw.get("min_group_in_pool_evidence_coverage") or 0.50
        ),
        launch_priority_models=str(
            config.raw.get(
                "launch_priority_models",
                REPO_ROOT / "configs" / "model_30_launch_priority_models.v1.json",
            )
        ),
        launch_priority_gate=str(config.raw.get("launch_priority_gate") or "warn"),
        smoke=False,
        training_manifest=str(_stage_dir(config, "assembled") / "report.json"),
        model_id_uint=int(config.raw.get("model_id_uint") or 30),
        baseline_artifact_uri=config.raw.get("baseline_model_uri"),
        eth_rpc_url=config.raw.get("eth_rpc_url"),
        delta_verifier_address=config.raw.get("delta_verifier_address"),
        model_registry_address=config.raw.get("model_registry_address"),
        onchain_timeout_seconds=float(config.raw.get("onchain_timeout_seconds") or 5.0),
    )
    return register_model(args)


def _script_command(script: str, args: list[str]) -> list[str]:
    return [sys.executable, str(REPO_ROOT / script), *args]


def planned_commands(config: WorkflowConfig) -> dict[str, list[str]]:
    dataset_jsonl = _stage_dir(config, "assembled") / "dataset.jsonl"
    manifest = _stage_dir(config, "assembled") / "report.json"
    evaluation_report = _stage_dir(config, "evaluation") / "comparison_report.json"
    attribution_report = _stage_dir(config, "attribution") / "attribution_report.json"
    candidate_uri = "<candidate-model-uri-from-train-stage>"
    return {
        "evaluate": _script_command(
            "scripts/model_30/evaluate_technical_task_router.py",
            [
                "--holdout-dataset",
                str(Path(str(config.raw["holdout_dataset"])).expanduser().resolve()),
                "--baseline-model-uri",
                str(config.raw["baseline_model_uri"]),
                "--candidate-model-uri",
                candidate_uri,
                "--benchmark-version",
                str(config.raw.get("benchmark_version") or "v2"),
                "--output-report",
                str(evaluation_report),
                "--training-manifest",
                str(manifest),
                "--log-mlflow",
            ],
        ),
        "attribute": _script_command(
            "scripts/model_30/attribute_retraining.py",
            [
                "--manifest",
                str(manifest),
                "--dataset",
                str(dataset_jsonl),
                "--holdout",
                str(Path(str(config.raw["holdout_dataset"])).expanduser().resolve()),
                "--baseline-run-id",
                "<baseline-evaluation-run-id>",
                "--candidate-run-id",
                "<candidate-evaluation-run-id>",
                "--output",
                str(attribution_report),
            ],
        ),
        "promote": _script_command(
            "scripts/model_30/promote_technical_task_router.py",
            ["--model-uri", candidate_uri, "--alias", "production"],
        ),
    }


def write_run_manifest(
    config: WorkflowConfig,
    *,
    stage: str,
    reports: dict[str, Any],
) -> Path:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "contribution_training_flow_run/v1",
        "created_at": datetime.now(UTC).isoformat(),
        "config_path": str(config.path),
        "model_id": config.model_id,
        "stage": stage,
        "reports": reports,
        "planned_commands": planned_commands(config),
        "promotion_enabled": bool(config.raw.get("allow_promotion")),
        "reward_publish_enabled": bool(config.raw.get("allow_reward_publish")),
    }
    path = config.output_dir / RUN_MANIFEST
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _run_command(command: list[str], *, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"dry_run": True, "command": command}
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    return {
        "dry_run": False,
        "command": command,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def run_stage(config: WorkflowConfig, stage: str, *, dry_run: bool) -> dict[str, Any]:
    reports: dict[str, Any] = {}
    if stage in {"plan"}:
        reports["plan"] = {"planned_commands": planned_commands(config)}
    if stage in {"assemble", "all"}:
        reports["assemble"] = (
            _run_command(["assemble"], dry_run=dry_run) if dry_run else run_assemble(config)
        )
    if stage in {"prepare", "all"}:
        reports["prepare"] = (
            _run_command(["prepare"], dry_run=dry_run) if dry_run else run_prepare(config)
        )
    if stage in {"train", "all"}:
        reports["train"] = (
            _run_command(["train"], dry_run=dry_run) if dry_run else run_train(config)
        )
    if stage in {"evaluate", "all"}:
        reports["evaluate"] = _run_command(planned_commands(config)["evaluate"], dry_run=dry_run)
    if stage in {"attribute", "all"}:
        reports["attribute"] = _run_command(planned_commands(config)["attribute"], dry_run=dry_run)
    if stage in {"promote", "all"}:
        if not config.raw.get("allow_promotion"):
            reports["promote"] = {"skipped": True, "reason": "allow_promotion is false"}
        else:
            reports["promote"] = _run_command(planned_commands(config)["promote"], dry_run=dry_run)
    manifest = write_run_manifest(config, stage=stage, reports=reports)
    reports["run_manifest_path"] = str(manifest)
    return reports


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        required=True,
        help="Path to contribution workflow JSON config.",
    )
    parser.add_argument("--stage", choices=STAGES, default="plan")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run the selected stage. Omit for dry-run planning output.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(Path(args.config))
    report = run_stage(config, args.stage, dry_run=not args.execute)
    print(json.dumps(report, indent=2, sort_keys=True))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
