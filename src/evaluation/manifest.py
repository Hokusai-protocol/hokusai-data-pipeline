"""Hokusai Evaluation Manifest (HEM) data model and MLflow integration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from src.evaluation.validation import validate_manifest

HEM_SCHEMA_VERSION = "hokusai.eval.manifest/v1"


@dataclass
class HokusaiEvaluationManifest:
    """Versioned, provider-agnostic evaluation result manifest."""

    model_id: str
    eval_id: str
    dataset: dict[str, Any]
    primary_metric: dict[str, Any]
    metrics: list[dict[str, Any]]
    mlflow_run_id: str
    schema_version: str = HEM_SCHEMA_VERSION
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    mlflow_dataset_id: str | None = None
    uncertainty: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] | None = None
    provenance: dict[str, Any] | None = None

    def to_dict(self: HokusaiEvaluationManifest) -> dict[str, Any]:
        """Serialize the manifest to a JSON-serializable dictionary."""
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "model_id": self.model_id,
            "eval_id": self.eval_id,
            "dataset": self.dataset,
            "primary_metric": self.primary_metric,
            "metrics": self.metrics,
            "created_at": self.created_at,
            "mlflow_run_id": self.mlflow_run_id,
        }
        if self.mlflow_dataset_id is not None:
            result["mlflow_dataset_id"] = self.mlflow_dataset_id
        if self.uncertainty is not None:
            result["uncertainty"] = self.uncertainty
        if self.artifacts is not None:
            result["artifacts"] = self.artifacts
        if self.provenance is not None:
            result["provenance"] = self.provenance
        return result

    @classmethod
    def from_dict(
        cls: type[HokusaiEvaluationManifest], data: dict[str, Any]
    ) -> HokusaiEvaluationManifest:
        """Create a manifest from a dictionary after schema validation."""
        errors = validate_manifest(data)
        if errors:
            joined = "; ".join(errors)
            raise ValueError(f"Invalid HokusaiEvaluationManifest: {joined}")
        return cls(
            schema_version=data["schema_version"],
            model_id=data["model_id"],
            eval_id=data["eval_id"],
            dataset=data["dataset"],
            primary_metric=data["primary_metric"],
            metrics=data["metrics"],
            created_at=data["created_at"],
            mlflow_run_id=data["mlflow_run_id"],
            mlflow_dataset_id=data.get("mlflow_dataset_id"),
            uncertainty=data.get("uncertainty"),
            artifacts=data.get("artifacts"),
            provenance=data.get("provenance"),
        )

    def compute_hash(self: HokusaiEvaluationManifest) -> str:
        """Compute deterministic SHA-256 content hash for attestation.

        The hash excludes `created_at` and `mlflow_run_id` so equivalent manifests
        are stable across re-logging.
        """
        payload = self.to_dict()
        payload.pop("created_at", None)
        payload.pop("mlflow_run_id", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()

    def is_comparable_to(self: HokusaiEvaluationManifest, other: HokusaiEvaluationManifest) -> bool:
        """Return whether two manifests are comparable for DeltaOne checks."""
        return (
            self.eval_id == other.eval_id
            and self.dataset.get("hash") == other.dataset.get("hash")
            and self.primary_metric.get("name") == other.primary_metric.get("name")
        )

    def to_json(self: HokusaiEvaluationManifest, indent: int = 2) -> str:
        """Serialize manifest as pretty-printed JSON."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def _load_mlflow() -> Any:
    """Load mlflow lazily so base installs can import manifest utilities."""
    # Authentication (Authorization / MLFLOW_TRACKING_TOKEN) is handled by
    # repository-wide MLflow configuration before these helpers are invoked.
    try:
        import mlflow  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "mlflow is required for MLflow integration. Install the mlflow extra/dependency."
        ) from exc
    return mlflow


def create_hem_from_mlflow_run(
    run_id: str, eval_id: str | None = None, primary_metric_name: str | None = None
) -> HokusaiEvaluationManifest:
    """Construct a HEM from an MLflow run."""
    mlflow = _load_mlflow()
    run = mlflow.get_run(run_id)
    tags = run.data.tags or {}
    params = run.data.params or {}
    metric_map = run.data.metrics or {}

    resolved_eval_id = eval_id or tags.get("hokusai.eval_id")
    if not resolved_eval_id:
        raise ValueError(
            "Missing eval_id. Provide eval_id argument or set run tag 'hokusai.eval_id'."
        )

    resolved_primary_metric = (
        primary_metric_name or tags.get("hokusai.primary_metric") or tags.get("primary_metric")
    )
    if not resolved_primary_metric:
        raise ValueError(
            "Missing primary metric. Provide primary_metric_name or set run tag "
            "'hokusai.primary_metric'."
        )
    if resolved_primary_metric not in metric_map:
        raise ValueError(
            f"Primary metric '{resolved_primary_metric}' not found in MLflow run metrics."
        )

    dataset_id = tags.get("hokusai.dataset.id") or params.get("hokusai.dataset.id")
    dataset_hash = tags.get("hokusai.dataset.hash") or params.get("hokusai.dataset.hash")
    if not dataset_id:
        raise ValueError("Missing dataset id. Set tag/param 'hokusai.dataset.id'.")
    if not dataset_hash:
        raise ValueError("Missing dataset hash. Set tag/param 'hokusai.dataset.hash'.")

    num_samples_raw = (
        tags.get("hokusai.dataset.num_samples")
        or params.get("hokusai.dataset.num_samples")
        or tags.get("dataset:n_examples")
        or 0
    )
    try:
        num_samples = int(num_samples_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid dataset sample count: {num_samples_raw!r}") from exc

    metrics = [
        {"name": name, "value": value}
        for name, value in sorted(metric_map.items(), key=lambda item: item[0])
    ]

    provenance = {
        "provider": tags.get("hokusai.provider", "mlflow"),
        "provider_version": tags.get("hokusai.provider_version"),
        "parameters": dict(params),
    }
    clean_provenance = {key: value for key, value in provenance.items() if value is not None}

    manifest = HokusaiEvaluationManifest(
        model_id=tags.get("hokusai.model_id") or tags.get("mlflow.runName") or "unknown-model",
        eval_id=resolved_eval_id,
        dataset={
            "id": dataset_id,
            "hash": dataset_hash,
            "num_samples": num_samples,
        },
        primary_metric={
            "name": resolved_primary_metric,
            "value": metric_map[resolved_primary_metric],
            "higher_is_better": tags.get("hokusai.primary_metric.higher_is_better", "true").lower()
            == "true",
        },
        metrics=metrics,
        mlflow_run_id=run.info.run_id,
        mlflow_dataset_id=tags.get("hokusai.mlflow_dataset_id") or tags.get("mlflow.dataset_id"),
        provenance=clean_provenance,
    )
    errors = validate_manifest(manifest.to_dict())
    if errors:
        joined = "; ".join(errors)
        raise ValueError(f"Created manifest is invalid: {joined}")
    return manifest


def log_hem_to_mlflow(manifest: HokusaiEvaluationManifest, run_id: str | None = None) -> None:
    """Persist HEM to MLflow as `hem/manifest.json`."""
    mlflow = _load_mlflow()
    payload = manifest.to_dict()

    if run_id:
        with mlflow.start_run(run_id=run_id):
            mlflow.log_dict(payload, artifact_file="hem/manifest.json")
        return

    mlflow.log_dict(payload, artifact_file="hem/manifest.json")
