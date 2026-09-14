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
import hashlib
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

from scripts.model_30.assemble_training_set import canonical_manifest_bytes  # noqa: E402
from scripts.model_30.contribution_row_normalization import (  # noqa: E402
    contribution_row_to_router_csv_row,
    router_fieldnames,
)

STAGES = ("plan", "assemble", "prepare", "train", "evaluate", "attribute", "promote", "all")
RUN_MANIFEST = "run_manifest.json"


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


def _router_dataset_path(config: WorkflowConfig) -> Path:
    return _stage_dir(config, "assembled") / str(
        config.model_config.get("router_dataset_filename") or "dataset.csv"
    )


def _contribution_router_dataset_path(config: WorkflowConfig) -> Path:
    return _stage_dir(config, "assembled") / str(
        config.model_config.get("contribution_router_dataset_filename")
        or "contribution_dataset.csv"
    )


def _base_router_dataset_path(config: WorkflowConfig) -> Path | None:
    configured = config.model_config.get("base_router_dataset") or config.raw.get(
        "base_router_dataset"
    )
    if not configured:
        return None
    return Path(str(configured)).expanduser().resolve()


def _training_manifest_path(config: WorkflowConfig) -> Path:
    if _base_router_dataset_path(config) is None:
        return _stage_dir(config, "assembled") / "manifest.json"
    return _stage_dir(config, "assembled") / str(
        config.model_config.get("training_manifest_filename") or "training_manifest.json"
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def merge_router_csvs(base_csv: Path, contribution_csv: Path, output_csv: Path) -> dict[str, Any]:
    """Write a deterministic base-plus-contributions router CSV."""
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = router_fieldnames()
    base_rows = 0
    contribution_rows = 0
    with output_csv.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for source_path, counter_name in (
            (base_csv, "base_rows"),
            (contribution_csv, "contribution_rows"),
        ):
            with source_path.open(newline="", encoding="utf-8") as source:
                for row in csv.DictReader(source):
                    writer.writerow(row)
                    if counter_name == "base_rows":
                        base_rows += 1
                    else:
                        contribution_rows += 1
    return {
        "base_path": str(base_csv),
        "contribution_path": str(contribution_csv),
        "output_path": str(output_csv),
        "base_rows": base_rows,
        "contribution_rows": contribution_rows,
        "rows_written": base_rows + contribution_rows,
        "dataset_hash": _file_sha256(output_csv),
    }


def write_offset_training_manifest(
    source_manifest_path: Path,
    output_manifest_path: Path,
    *,
    base_row_count: int,
    dataset_hash: str,
    row_count: int,
) -> dict[str, Any]:
    """Shift contribution row ranges after prepending a base training set."""
    manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    shifted_blocks = []
    for block in manifest["blocks"]:
        shifted = dict(block)
        shifted["row_start"] = int(block["row_start"]) + base_row_count
        shifted["row_end"] = int(block["row_end"]) + base_row_count
        shifted_blocks.append(shifted)
    manifest["blocks"] = shifted_blocks
    manifest["dataset_hash"] = dataset_hash
    manifest["row_count"] = row_count
    manifest["manifest_digest"] = ""
    manifest["manifest_digest"] = (
        f"sha256:{hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()}"
    )
    output_manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


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
        row_format=str(config.raw.get("row_format") or "auto"),
    )
    return assemble_training_set.assemble(args)


def run_prepare(config: WorkflowConfig) -> dict[str, Any]:
    dataset_jsonl = _stage_dir(config, "assembled") / "dataset.jsonl"
    base_dataset = _base_router_dataset_path(config)
    if base_dataset is None:
        return convert_jsonl_to_router_csv(dataset_jsonl, _router_dataset_path(config))

    contribution_csv = _contribution_router_dataset_path(config)
    contribution_report = convert_jsonl_to_router_csv(dataset_jsonl, contribution_csv)
    merge_report = merge_router_csvs(base_dataset, contribution_csv, _router_dataset_path(config))
    training_manifest = write_offset_training_manifest(
        _stage_dir(config, "assembled") / "manifest.json",
        _training_manifest_path(config),
        base_row_count=int(merge_report["base_rows"]),
        dataset_hash=str(merge_report["dataset_hash"]),
        row_count=int(merge_report["rows_written"]),
    )
    return {
        "contribution_conversion": contribution_report,
        "merge": merge_report,
        "training_manifest_path": str(_training_manifest_path(config)),
        "training_manifest_digest": training_manifest["manifest_digest"],
    }


def run_train(config: WorkflowConfig) -> dict[str, Any]:
    from scripts.model_30.register_technical_task_router import register_model

    dataset_csv = _router_dataset_path(config)
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
        training_manifest=str(_training_manifest_path(config)),
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
    manifest = _training_manifest_path(config)
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
