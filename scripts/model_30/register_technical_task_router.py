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
    evaluate_model,
    parse_objectives,
)
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


@dataclass(frozen=True)
class RouterDatasetSummary:
    """Provenance summary for the Wavemill router dataset."""

    row_count: int
    sha256: str
    selected_model_distribution: dict[str, dict[str, int]]

    def to_mlflow_dict(self: RouterDatasetSummary) -> dict[str, Any]:
        """Return a JSON-serializable summary suitable for MLflow artifacts."""
        return {
            "row_count": self.row_count,
            "sha256": f"sha256:{self.sha256}",
            "selected_model_distribution": self.selected_model_distribution,
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
    )


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


def register_model(args: argparse.Namespace) -> dict[str, Any]:
    """Log and register the callable Technical Task Router model."""
    dataset_path = Path(args.router_dataset).expanduser().resolve()
    if not dataset_path.exists():
        raise FileNotFoundError(f"Router dataset not found: {dataset_path}")
    dataset_summary = validate_router_dataset_model_ids(dataset_path)

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
        mlflow.log_param("k_neighbors", args.k_neighbors)
        mlflow.set_tag("hokusai.dataset.id", "wavemill-hokusai-router-dataset-v1")
        mlflow.set_tag("hokusai.dataset.hash", f"sha256:{dataset_summary.sha256}")
        mlflow.set_tag("hokusai.dataset.num_samples", str(dataset_summary.row_count))
        mlflow.set_tag("hokusai.dataset.source", "wavemill-router-export")
        mlflow.log_dict(dataset_summary.to_mlflow_dict(), "router_dataset_summary.json")
        training_manifest = getattr(args, "training_manifest", None)
        if training_manifest:
            _log_training_manifest(training_manifest)
        if evaluation_report is not None:
            for metric_name, metric_value in evaluation_report["metrics"].items():
                if metric_value is None:
                    continue
                mlflow.log_metric(metric_name, float(metric_value))
            mlflow.set_tag(
                "hokusai.model_30.holdout_hash",
                evaluation_report["holdout_dataset_sha256"],
            )
            mlflow.set_tag(
                "hokusai.model_30.holdout_rows",
                str(evaluation_report["row_counts"]["evaluated_rows"]),
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

    version = getattr(model_info, "registered_model_version", None)
    model_uri = _registered_model_uri(MODEL_NAME, str(version) if version else None)
    result = {
        "run_id": run.info.run_id,
        "artifact_uri": model_info.model_uri,
        "registered_model_name": MODEL_NAME,
        "registered_model_version": str(version) if version else None,
        "registered_model_uri": model_uri,
    }

    if args.smoke:
        loaded = mlflow.pyfunc.load_model(model_uri)
        prediction = loaded.predict(sample_features)
        result["smoke_prediction"] = prediction.to_dict(orient="records")
    if evaluation_report is not None:
        result["evaluation_report"] = {
            key: value for key, value in evaluation_report.items() if key != "benchmark_rows"
        }

    return result


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
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Load the registered model URI and call predict after registration.",
    )
    parser.add_argument(
        "--training-manifest",
        help="Optional assembler report.json used to tag the MLflow training run.",
    )
    return parser.parse_args()


def main() -> None:
    """Run model registration from the command line."""
    result = register_model(parse_args())
    for key, value in result.items():
        print(f"{key}: {value}")  # noqa: T201


if __name__ == "__main__":
    main()
