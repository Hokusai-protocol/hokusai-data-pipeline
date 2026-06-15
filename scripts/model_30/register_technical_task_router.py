"""Register the callable Technical Task Router pyfunc model.

This script intentionally uses direct ``mlflow.pyfunc.log_model`` registration
with ``registered_model_name="Technical Task Router"``. It does not use the
artifact-reference helper that produced the non-callable model 30 wrapper.
MLflow authentication is provided by the SDK environment, including
``MLFLOW_TRACKING_TOKEN`` when the registry requires bearer auth.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mlflow
import mlflow.pyfunc
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.model_30.assemble_training_set import load_json  # noqa: E402
from scripts.model_30.evaluate_technical_task_router import (  # noqa: E402
    DEFAULT_V2_PRIMARY_METRIC,
    V2_BENCHMARK_SPEC_ID,
    evaluate_model,
    parse_objectives,
)
from src.eip712 import read_model_weight_head  # noqa: E402
from src.evaluation.tags import (  # noqa: E402
    BENCHMARK_SPEC_ID_TAG,
    MLFLOW_NAME_TAG,
    PRIMARY_METRIC_TAG,
    SCORER_REF_TAG,
    WEIGHT_COMMITMENT_BASELINE_TAG,
    WEIGHT_COMMITMENT_CANDIDATE_TAG,
)
from src.lineage.weight_commitment import compute_weight_commitment  # noqa: E402
from src.models.technical_task_router import (  # noqa: E402
    MODEL_NAME,
    ROUTER_DATASET_ARTIFACT,
    TechnicalTaskRouterModel,
)

MODEL_ID_PATTERN = re.compile(r"^(claude-|gpt-|deepseek-)")
MODEL_ID_COLUMNS = (
    "available_planner_models",
    "available_coder_models",
    "available_reviewer_models",
    "planner_model",
    "coder_model",
    "reviewer_model",
)
SELECTED_MODEL_ID_COLUMNS = ("planner_model", "coder_model", "reviewer_model")
ROLE_MODEL_COLUMNS = {
    "planner": ("planner_model", "available_planner_models"),
    "coder": ("coder_model", "available_coder_models"),
    "reviewer": ("reviewer_model", "available_reviewer_models"),
}
IN_POOL_GROUP_COLUMNS = ("task_type", "domain", "complexity")
DEFAULT_BASELINE_ARTIFACT_URI = "models:/Technical Task Router@production"
DEFAULT_MIN_IN_POOL_EVIDENCE_COVERAGE = 0.70
DEFAULT_MIN_GROUP_IN_POOL_EVIDENCE_COVERAGE = 0.50
MODEL_30_V2_METRIC_FAMILY = "continuous"
MODEL_30_V2_COMPONENT_METRICS = (
    "technical_task_router.success_under_budget_v1",
    "technical_task_router.cost_efficiency_v2",
    "technical_task_router.sparse_cell_generalization_v2",
    "technical_task_router.candidate_pool_robustness_v2",
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RouterDatasetSummary:
    """Provenance summary for the Wavemill router dataset."""

    row_count: int
    sha256: str
    selected_model_distribution: dict[str, dict[str, int]]
    in_pool_evidence_coverage: dict[str, Any]

    def to_mlflow_dict(self: RouterDatasetSummary) -> dict[str, Any]:
        """Return a JSON-serializable summary suitable for MLflow artifacts."""
        return {
            "row_count": self.row_count,
            "sha256": f"sha256:{self.sha256}",
            "selected_model_distribution": self.selected_model_distribution,
            "in_pool_evidence_coverage": self.in_pool_evidence_coverage,
        }


def _sample_features() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "schema_version": "technical_task_router_inputs/v2",
                "task_descriptor": "{}",
                "task_description": "Refactor billing webhook retry handling",
                "task_type": "refactor",
                "language": "python",
                "framework": "fastapi",
                "repo_type": "monorepo",
                "allowed_models": '["claude-sonnet-4-5-20250929","gpt-5.4"]',
                "preferred_models": '["claude-sonnet-4-5-20250929"]',
                "max_cost_usd": 10.0,
                "domain": "backend",
                "repo_size_bucket": "large",
                "requires_tests": True,
                "risk_level": "medium",
                "file_count": 6,
                "estimated_complexity": "medium",
                "security_sensitive": False,
                "surface": "wavemill",
                "workflow_stages": '["plan","code","review"]',
                "routing_objective": "highest_reliability",
                "expected_cost_usd": 5.0,
                "expected_success_probability": 0.8,
            }
        ]
    )


def _parse_model_values(raw_value: str) -> list[str]:
    value = raw_value.strip()
    if not value:
        return []
    if value.startswith("["):
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise ValueError(f"Expected model list, got {type(parsed).__name__}")
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [value]


def _dataset_sha256(dataset_path: Path) -> str:
    digest = hashlib.sha256()
    with dataset_path.open("rb") as dataset_file:
        for chunk in iter(lambda: dataset_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_model_columns(fieldnames: list[str] | None) -> None:
    missing_columns = sorted(set(MODEL_ID_COLUMNS) - set(fieldnames or []))
    if missing_columns:
        raise ValueError(
            "Router dataset is missing model identifier columns: " f"{missing_columns}"
        )


def _validate_model_row(
    row: dict[str, str],
    row_number: int,
    selected_distribution: dict[str, Counter[str]],
) -> list[str]:
    invalid: list[str] = []
    for column in MODEL_ID_COLUMNS:
        try:
            model_ids = _parse_model_values(row.get(column, ""))
        except (json.JSONDecodeError, ValueError) as exc:
            invalid.append(f"row {row_number} {column}: malformed model list ({exc})")
            continue

        if column in SELECTED_MODEL_ID_COLUMNS and not model_ids:
            invalid.append(f"row {row_number} {column}=<empty>")

        for model_id in model_ids:
            if not MODEL_ID_PATTERN.match(model_id):
                invalid.append(f"row {row_number} {column}={model_id!r}")
            elif column in SELECTED_MODEL_ID_COLUMNS:
                selected_distribution[column][model_id] += 1

    return invalid


def _empty_coverage_counts() -> dict[str, dict[str, int]]:
    return {
        role: {
            "selected_rows": 0,
            "in_pool_rows": 0,
            "out_of_pool_rows": 0,
        }
        for role in ROLE_MODEL_COLUMNS
    }


def _coverage_fraction(in_pool_rows: int, selected_rows: int) -> float:
    return in_pool_rows / selected_rows if selected_rows else 0.0


def _coverage_counts_to_report(counts: dict[str, dict[str, int]]) -> dict[str, dict[str, Any]]:
    return {
        role: {
            **role_counts,
            "in_pool_fraction": _coverage_fraction(
                role_counts["in_pool_rows"],
                role_counts["selected_rows"],
            ),
        }
        for role, role_counts in counts.items()
    }


def _group_value(row: dict[str, str], column: str) -> str:
    value = str(row.get(column, "")).strip()
    return value or "<missing>"


def _build_in_pool_evidence_coverage(dataset_path: Path) -> dict[str, Any]:
    """Summarize selected-label support that remains usable under available pools."""
    overall_counts = _empty_coverage_counts()
    excluded_labels = {role: Counter() for role in ROLE_MODEL_COLUMNS}
    group_counts: dict[str, dict[str, dict[str, dict[str, int]]]] = {
        column: {} for column in IN_POOL_GROUP_COLUMNS
    }

    with dataset_path.open(newline="", encoding="utf-8") as dataset_file:
        reader = csv.DictReader(dataset_file)
        for row in reader:
            for role, (selected_column, available_column) in ROLE_MODEL_COLUMNS.items():
                selected_models = _parse_model_values(row.get(selected_column, ""))
                available_models = set(_parse_model_values(row.get(available_column, "")))
                if not selected_models:
                    continue
                selected_model = selected_models[0]
                in_pool = selected_model in available_models
                overall_counts[role]["selected_rows"] += 1
                if in_pool:
                    overall_counts[role]["in_pool_rows"] += 1
                else:
                    overall_counts[role]["out_of_pool_rows"] += 1
                    excluded_labels[role][selected_model] += 1

                for group_column in IN_POOL_GROUP_COLUMNS:
                    group_key = _group_value(row, group_column)
                    role_counts = group_counts[group_column].setdefault(
                        group_key,
                        _empty_coverage_counts(),
                    )[role]
                    role_counts["selected_rows"] += 1
                    if in_pool:
                        role_counts["in_pool_rows"] += 1
                    else:
                        role_counts["out_of_pool_rows"] += 1

    return {
        "overall": _coverage_counts_to_report(overall_counts),
        "by_group": {
            group_column: {
                group_key: _coverage_counts_to_report(counts)
                for group_key, counts in sorted(groups.items())
            }
            for group_column, groups in group_counts.items()
        },
        "excluded_selected_model_distribution": {
            role: dict(sorted(counter.items())) for role, counter in excluded_labels.items()
        },
    }


def validate_router_dataset_model_ids(dataset_path: Path) -> RouterDatasetSummary:
    """Reject router datasets with synthetic or malformed model identifiers."""
    invalid: list[str] = []
    selected_distribution = {column: Counter() for column in SELECTED_MODEL_ID_COLUMNS}
    row_count = 0
    with dataset_path.open(newline="", encoding="utf-8") as dataset_file:
        reader = csv.DictReader(dataset_file)
        _validate_model_columns(reader.fieldnames)

        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            invalid.extend(_validate_model_row(row, row_number, selected_distribution))
            if len(invalid) >= 10:
                break

    if row_count == 0:
        raise ValueError("Router dataset must contain at least one row")

    if invalid:
        details = "; ".join(invalid)
        raise ValueError(
            "Router dataset contains non-public or malformed model identifiers: "
            f"{details}. Regenerate or clean the Wavemill export before registration."
        )

    return RouterDatasetSummary(
        row_count=row_count,
        sha256=_dataset_sha256(dataset_path),
        selected_model_distribution={
            column: dict(sorted(counter.items()))
            for column, counter in selected_distribution.items()
        },
        in_pool_evidence_coverage=_build_in_pool_evidence_coverage(dataset_path),
    )


def _in_pool_coverage_gate_violations(
    coverage: dict[str, Any],
    *,
    min_role_coverage: float,
    min_group_coverage: float,
) -> list[str]:
    violations: list[str] = []
    for role, role_report in coverage.get("overall", {}).items():
        if (
            role_report.get("selected_rows", 0)
            and role_report["in_pool_fraction"] < min_role_coverage
        ):
            violations.append(
                f"{role} overall in-pool coverage "
                f"{role_report['in_pool_rows']}/{role_report['selected_rows']}="
                f"{role_report['in_pool_fraction']:.3f} below {min_role_coverage:.3f}"
            )

    for group_column, group_reports in coverage.get("by_group", {}).items():
        for group_value, roles in group_reports.items():
            for role, role_report in roles.items():
                if (
                    role_report.get("selected_rows", 0)
                    and role_report["in_pool_fraction"] < min_group_coverage
                ):
                    violations.append(
                        f"{role} {group_column}={group_value!r} in-pool coverage "
                        f"{role_report['in_pool_rows']}/{role_report['selected_rows']}="
                        f"{role_report['in_pool_fraction']:.3f} below {min_group_coverage:.3f}"
                    )
    return violations


def _enforce_in_pool_evidence_gate(
    summary: RouterDatasetSummary,
    *,
    mode: str,
    min_role_coverage: float,
    min_group_coverage: float,
) -> list[str]:
    if mode == "off":
        return []
    violations = _in_pool_coverage_gate_violations(
        summary.in_pool_evidence_coverage,
        min_role_coverage=min_role_coverage,
        min_group_coverage=min_group_coverage,
    )
    if not violations:
        return []
    message = "Router dataset in-pool evidence coverage gate violated: " + "; ".join(violations)
    if mode == "fail":
        raise ValueError(message)
    logger.warning(message)
    return violations


def _resolve_coverage_threshold(
    args: argparse.Namespace,
    attr_name: str,
    default: float,
) -> float:
    raw_value = getattr(args, attr_name, None)
    if raw_value is None:
        raw_value = default
    value = float(raw_value)
    if not 0 <= value <= 1:
        raise ValueError(f"{attr_name} must be between 0 and 1, got {value}")
    return value


def _resolve_in_pool_coverage_gate_mode(args: argparse.Namespace) -> str:
    mode = str(getattr(args, "in_pool_coverage_gate", "warn") or "warn")
    if mode not in {"off", "warn", "fail"}:
        raise ValueError(f"in_pool_coverage_gate must be off, warn, or fail, got {mode!r}")
    return mode


def _registered_model_uri(model_name: str, version: str | None) -> str:
    if version:
        return f"models:/{model_name}/{version}"
    return f"models:/{model_name}/latest"


def _log_training_manifest(report_path: str) -> None:
    report = load_json(Path(report_path).expanduser().resolve())
    mlflow.set_tag("training_dataset_hash", report["dataset_hash"])
    mlflow.set_tag("training_manifest_digest", report["manifest_digest"])
    mlflow.set_tag("training_as_of", report["as_of"])
    mlflow.log_dict(report, "training_manifest_report.json")


def _normalize_commitment_root(root: str) -> str:
    return f"0x{root.lower()}"


def _resolve_required_arg(args: argparse.Namespace, attr_name: str, env_name: str) -> str:
    value = getattr(args, attr_name, None) or os.getenv(env_name)
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{env_name} or --{attr_name.replace('_', '-')} is required")
    return normalized


def _resolve_model_id_uint(args: argparse.Namespace) -> int:
    raw = getattr(args, "model_id_uint", None)
    if raw is None:
        raw = os.getenv("MODEL_30_MODEL_ID_UINT", "30")
    try:
        model_id_uint = int(str(raw).strip())
    except ValueError as exc:
        raise ValueError(f"model_id_uint must be an integer, got {raw!r}") from exc
    if model_id_uint < 0:
        raise ValueError(f"model_id_uint must be non-negative, got {model_id_uint}")
    return model_id_uint


def _resolve_baseline_artifact_uri(args: argparse.Namespace) -> str | None:
    raw_value = getattr(args, "baseline_artifact_uri", None)
    if raw_value is None:
        raw_value = os.getenv("MODEL_30_BASELINE_ARTIFACT_URI", DEFAULT_BASELINE_ARTIFACT_URI)
    normalized = str(raw_value or "").strip()
    return normalized or None


def _resolve_onchain_timeout_seconds(args: argparse.Namespace) -> float:
    raw = getattr(args, "onchain_timeout_seconds", None)
    if raw is None:
        raw = os.getenv("MINT_ONCHAIN_TIMEOUT_SECONDS", "5.0")
    try:
        timeout = float(str(raw).strip())
    except ValueError as exc:
        raise ValueError(f"on-chain timeout must be numeric, got {raw!r}") from exc
    if timeout <= 0:
        raise ValueError(f"on-chain timeout must be positive, got {timeout}")
    return timeout


def _compute_weight_commitment_for_uri(uri: str) -> tuple[str, str]:
    artifact_dir = mlflow.artifacts.download_artifacts(artifact_uri=uri)
    commitment = compute_weight_commitment(artifact_dir)
    return _normalize_commitment_root(commitment.root), artifact_dir


def _tag_weight_commitments(
    *,
    model_uri: str,
    model_id_uint: int,
    rpc_url: str,
    delta_verifier_address: str,
    model_registry_address: str,
    baseline_artifact_uri: str | None,
    onchain_timeout: float,
) -> dict[str, str | None]:
    candidate_commitment, candidate_artifact_dir = _compute_weight_commitment_for_uri(model_uri)
    baseline_commitment = read_model_weight_head(
        rpc_url,
        delta_verifier_address=delta_verifier_address,
        model_registry_address=model_registry_address,
        model_id_uint=model_id_uint,
        timeout=onchain_timeout,
    )
    mlflow.set_tag(WEIGHT_COMMITMENT_CANDIDATE_TAG, candidate_commitment)
    mlflow.set_tag(WEIGHT_COMMITMENT_BASELINE_TAG, baseline_commitment)

    baseline_local_commitment: str | None = None
    if baseline_artifact_uri is None:
        logger.info(
            "event=weight_commitment_baseline_drift_skipped " "reason=no_baseline_artifact_uri"
        )
    else:
        baseline_local_commitment, _ = _compute_weight_commitment_for_uri(baseline_artifact_uri)
        if baseline_local_commitment != baseline_commitment:
            logger.warning(
                "event=weight_commitment_baseline_drift model_id_uint=%s "
                "onchain_commitment=%s local_commitment=%s baseline_artifact_uri=%s",
                model_id_uint,
                baseline_commitment,
                baseline_local_commitment,
                baseline_artifact_uri,
            )
    return {
        "candidate_commitment": candidate_commitment,
        "candidate_commitment_artifact_dir": candidate_artifact_dir,
        "baseline_commitment": baseline_commitment,
        "baseline_artifact_uri": baseline_artifact_uri,
        "baseline_local_commitment": baseline_local_commitment,
    }


def register_model(args: argparse.Namespace) -> dict[str, Any]:
    """Log and register the callable Technical Task Router model."""
    dataset_path = Path(args.router_dataset).expanduser().resolve()
    if not dataset_path.exists():
        raise FileNotFoundError(f"Router dataset not found: {dataset_path}")
    dataset_summary = validate_router_dataset_model_ids(dataset_path)
    gate_mode = _resolve_in_pool_coverage_gate_mode(args)
    min_role_coverage = _resolve_coverage_threshold(
        args,
        "min_in_pool_evidence_coverage",
        DEFAULT_MIN_IN_POOL_EVIDENCE_COVERAGE,
    )
    min_group_coverage = _resolve_coverage_threshold(
        args,
        "min_group_in_pool_evidence_coverage",
        DEFAULT_MIN_GROUP_IN_POOL_EVIDENCE_COVERAGE,
    )
    gate_violations = _enforce_in_pool_evidence_gate(
        dataset_summary,
        mode=gate_mode,
        min_role_coverage=min_role_coverage,
        min_group_coverage=min_group_coverage,
    )
    model_id_uint = _resolve_model_id_uint(args)
    rpc_url = _resolve_required_arg(args, "eth_rpc_url", "ETH_RPC_URL")
    delta_verifier_address = _resolve_required_arg(
        args,
        "delta_verifier_address",
        "DELTA_VERIFIER_ADDRESS",
    )
    model_registry_address = _resolve_required_arg(
        args,
        "model_registry_address",
        "MODEL_REGISTRY_ADDRESS",
    )
    baseline_artifact_uri = _resolve_baseline_artifact_uri(args)
    onchain_timeout = _resolve_onchain_timeout_seconds(args)

    if args.tracking_uri:
        mlflow.set_tracking_uri(args.tracking_uri)

    experiment_name = args.experiment_name or os.getenv(
        "MODEL_30_EXPERIMENT_NAME",
        "technical-task-router",
    )
    mlflow.set_experiment(experiment_name)

    sample_features = _sample_features()
    local_model = TechnicalTaskRouterModel(k_neighbors=args.k_neighbors)
    local_model.load_context(
        type(
            "Context",
            (),
            {"artifacts": {ROUTER_DATASET_ARTIFACT: str(dataset_path)}},
        )()
    )
    local_model.predict(None, sample_features)
    evaluation_report = None
    holdout_dataset = getattr(args, "holdout_dataset", None)
    if holdout_dataset:
        holdout_path = Path(holdout_dataset).expanduser().resolve()
        evaluation_report = evaluate_model(
            local_model,
            model_id=MODEL_NAME,
            holdout_path=holdout_path,
            objectives=parse_objectives(getattr(args, "evaluation_objectives", "all")),
            benchmark_spec_id=getattr(args, "benchmark_spec_id", None),
            benchmark_version=getattr(args, "benchmark_version", "v2"),
            primary_metric=getattr(args, "primary_metric", None),
        )

    with mlflow.start_run(run_name=args.run_name) as run:
        mlflow.log_param("model_name", MODEL_NAME)
        mlflow.log_param("router_dataset", str(dataset_path))
        mlflow.log_param("router_dataset_rows", dataset_summary.row_count)
        mlflow.log_param("router_dataset_sha256", f"sha256:{dataset_summary.sha256}")
        mlflow.log_param(
            "router_dataset_model_distribution",
            json.dumps(dataset_summary.selected_model_distribution, sort_keys=True),
        )
        mlflow.log_param("in_pool_coverage_gate", gate_mode)
        mlflow.log_param("min_in_pool_evidence_coverage", min_role_coverage)
        mlflow.log_param("min_group_in_pool_evidence_coverage", min_group_coverage)
        mlflow.log_param("k_neighbors", args.k_neighbors)
        mlflow.set_tag("hokusai.dataset.id", "wavemill-hokusai-router-dataset-v1")
        mlflow.set_tag("hokusai.dataset.hash", f"sha256:{dataset_summary.sha256}")
        mlflow.set_tag("hokusai.dataset.num_samples", str(dataset_summary.row_count))
        mlflow.set_tag("hokusai.dataset.source", "wavemill-router-export")
        mlflow.set_tag(
            "hokusai.model_30.in_pool_coverage_gate_violations",
            json.dumps(gate_violations, sort_keys=True),
        )
        mlflow.log_dict(dataset_summary.to_mlflow_dict(), "router_dataset_summary.json")
        training_manifest = getattr(args, "training_manifest", None)
        if training_manifest:
            _log_training_manifest(training_manifest)
        if evaluation_report is not None:
            _log_evaluation_report_to_mlflow(evaluation_report, model_id_uint=model_id_uint)
            mlflow.log_dict(
                {key: value for key, value in evaluation_report.items() if key != "benchmark_rows"},
                "model_30_evaluation_report.json",
            )
        # Do not log a strict signature: the public adapter sends nullable
        # optional columns, and the router normalizes them inside predict().
        model_info = mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=TechnicalTaskRouterModel(k_neighbors=args.k_neighbors),
            artifacts={ROUTER_DATASET_ARTIFACT: str(dataset_path)},
            registered_model_name=MODEL_NAME,
            pip_requirements=[
                "mlflow==3.9.0",
                "pandas",
            ],
        )
        commitment_result = _tag_weight_commitments(
            model_uri=model_info.model_uri,
            model_id_uint=model_id_uint,
            rpc_url=rpc_url,
            delta_verifier_address=delta_verifier_address,
            model_registry_address=model_registry_address,
            baseline_artifact_uri=baseline_artifact_uri,
            onchain_timeout=onchain_timeout,
        )

    version = getattr(model_info, "registered_model_version", None)
    model_uri = _registered_model_uri(MODEL_NAME, str(version) if version else None)
    result = {
        "run_id": run.info.run_id,
        "artifact_uri": model_info.model_uri,
        "registered_model_name": MODEL_NAME,
        "registered_model_version": str(version) if version else None,
        "registered_model_uri": model_uri,
    }
    result.update(commitment_result)

    if args.smoke:
        loaded = mlflow.pyfunc.load_model(model_uri)
        prediction = loaded.predict(sample_features)
        result["smoke_prediction"] = prediction.to_dict(orient="records")
    if evaluation_report is not None:
        result["evaluation_report"] = {
            key: value for key, value in evaluation_report.items() if key != "benchmark_rows"
        }

    return result


def _log_evaluation_report_to_mlflow(
    evaluation_report: dict[str, Any],
    *,
    model_id_uint: int,
) -> None:
    """Log Model 30 evaluation metrics and reward metadata to the active MLflow run."""
    for metric_name, metric_value in evaluation_report["metrics"].items():
        if metric_value is None:
            continue
        mlflow.log_metric(metric_name, float(metric_value))
    primary_metric = str(evaluation_report.get("primary_metric") or DEFAULT_V2_PRIMARY_METRIC)
    benchmark_spec_id = str(evaluation_report.get("benchmark_spec_id") or V2_BENCHMARK_SPEC_ID)
    benchmark_version = str(evaluation_report.get("benchmark_version") or "v2")
    metric_family = MODEL_30_V2_METRIC_FAMILY if benchmark_version == "v2" else "proportion"
    mlflow.set_tag(PRIMARY_METRIC_TAG, _metric_name_from_mlflow_key(primary_metric))
    mlflow.set_tag(MLFLOW_NAME_TAG, primary_metric)
    mlflow.set_tag(SCORER_REF_TAG, _metric_name_from_mlflow_key(primary_metric))
    mlflow.set_tag(BENCHMARK_SPEC_ID_TAG, benchmark_spec_id)
    mlflow.set_tag("hokusai.metric_family", metric_family)
    mlflow.set_tag("hokusai.model_id_uint", str(model_id_uint))
    mlflow.set_tag("hokusai.model_30.benchmark_version", benchmark_version)
    mlflow.set_tag("hokusai.model_30.primary_metric", primary_metric)
    mlflow.set_tag("hokusai.model_30.holdout_hash", evaluation_report["holdout_dataset_sha256"])
    mlflow.set_tag(
        "hokusai.model_30.holdout_rows",
        str(evaluation_report["row_counts"]["evaluated_rows"]),
    )
    mlflow.set_tag(
        "hokusai.model_30.benchmark_rows",
        str(evaluation_report["row_counts"]["benchmark_rows"]),
    )
    mlflow.set_tag(
        "hokusai.model_30.quarantined_rows",
        str(evaluation_report["row_counts"]["quarantined_rows"]),
    )
    mlflow.set_tag(
        "hokusai.model_30.duration_positive_label_rows",
        str(evaluation_report["duration_coverage"]["positive_label_rows"]),
    )
    mlflow.set_tag(
        "hokusai.model_30.duration_positive_label_fraction",
        str(evaluation_report["duration_coverage"]["positive_label_fraction"]),
    )
    mlflow.set_tag(
        "hokusai.model_30.duration_mae_available",
        str(evaluation_report["duration_coverage"]["duration_mae_available"]).lower(),
    )
    mlflow.set_tag(
        "hokusai.model_30.scenario_counts",
        json.dumps(evaluation_report.get("scenario_counts", {}), sort_keys=True),
    )
    mlflow.set_tag(
        "hokusai.model_30.support_coverage",
        json.dumps(evaluation_report.get("support_coverage", {}), sort_keys=True),
    )
    component_summary = _component_metric_summary(evaluation_report["metrics"])
    if component_summary:
        mlflow.set_tag(
            "hokusai.model_30.component_summary",
            json.dumps(component_summary, sort_keys=True),
        )


def _component_metric_summary(metrics: dict[str, Any]) -> dict[str, float]:
    return {
        metric_name: float(metrics[metric_name])
        for metric_name in MODEL_30_V2_COMPONENT_METRICS
        if metrics.get(metric_name) is not None
    }


def _metric_name_from_mlflow_key(metric_key: str) -> str:
    if metric_key == DEFAULT_V2_PRIMARY_METRIC:
        return "technical_task_router.benchmark_score/v2"
    if metric_key == "technical_task_router.benchmark_score_v1":
        return "technical_task_router.benchmark_score/v1"
    return metric_key


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--router-dataset",
        required=True,
        help="Path to the Wavemill hokusai-router-dataset.csv artifact.",
    )
    parser.add_argument("--tracking-uri", default=os.getenv("MLFLOW_TRACKING_URI"))
    parser.add_argument("--experiment-name")
    parser.add_argument("--run-name", default="technical-task-router-callable")
    parser.add_argument("--k-neighbors", type=int, default=40)
    parser.add_argument(
        "--holdout-dataset",
        help=(
            "Optional cleaned holdout CSV. Logs Model 30 benchmark diagnostics "
            "during registration."
        ),
    )
    parser.add_argument(
        "--evaluation-objectives",
        default="all",
        help="Routing objectives to evaluate: all or comma-separated objective names.",
    )
    parser.add_argument("--benchmark-version", choices=("v1", "v2"), default="v2")
    parser.add_argument("--primary-metric")
    parser.add_argument("--benchmark-spec-id")
    parser.add_argument(
        "--in-pool-coverage-gate",
        choices=("off", "warn", "fail"),
        default="warn",
        help=(
            "How to enforce selected-model evidence coverage after applying each "
            "role's available candidate pool."
        ),
    )
    parser.add_argument(
        "--min-in-pool-evidence-coverage",
        type=float,
        default=DEFAULT_MIN_IN_POOL_EVIDENCE_COVERAGE,
        help="Minimum overall per-role selected-label coverage required by the gate.",
    )
    parser.add_argument(
        "--min-group-in-pool-evidence-coverage",
        type=float,
        default=DEFAULT_MIN_GROUP_IN_POOL_EVIDENCE_COVERAGE,
        help="Minimum per-role coverage required within task_type/domain/complexity groups.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Load the registered model URI and call predict after registration.",
    )
    parser.add_argument(
        "--training-manifest",
        help="Optional assembler report.json used to tag the MLflow training run.",
    )
    parser.add_argument(
        "--model-id-uint",
        type=int,
        default=int(os.getenv("MODEL_30_MODEL_ID_UINT", "30")),
    )
    parser.add_argument(
        "--baseline-artifact-uri",
        default=os.getenv("MODEL_30_BASELINE_ARTIFACT_URI", DEFAULT_BASELINE_ARTIFACT_URI),
        help="MLflow artifact URI used for local baseline drift checks.",
    )
    parser.add_argument(
        "--eth-rpc-url",
        default=os.getenv("ETH_RPC_URL"),
        help="Ethereum JSON-RPC endpoint used to read the authoritative weight head.",
    )
    parser.add_argument(
        "--delta-verifier-address",
        default=os.getenv("DELTA_VERIFIER_ADDRESS"),
        help="DeltaVerifier contract address.",
    )
    parser.add_argument(
        "--model-registry-address",
        default=os.getenv("MODEL_REGISTRY_ADDRESS"),
        help="ModelRegistry contract address.",
    )
    parser.add_argument(
        "--onchain-timeout-seconds",
        type=float,
        default=float(os.getenv("MINT_ONCHAIN_TIMEOUT_SECONDS", "5.0")),
        help="Timeout for on-chain commitment reads.",
    )
    return parser.parse_args()


def main() -> None:
    """Run model registration from the command line."""
    result = register_model(parse_args())
    for key, value in result.items():
        print(f"{key}: {value}")  # noqa: T201


if __name__ == "__main__":
    main()
