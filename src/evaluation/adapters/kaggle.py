"""Kaggle benchmark adapter implementation."""

from __future__ import annotations

import csv
import json
import random
import tempfile
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from src.evaluation.adapters.base import BenchmarkSpec, ModelFn
from src.evaluation.manifest import HokusaiEvaluationManifest


class KaggleDatasetDownloader:
    """Protocol-like base for dataset download clients."""

    def download_dataset(
        self: KaggleDatasetDownloader,
        dataset_ref: str,
        dataset_version: int | None,
        destination_dir: Path,
    ) -> Path:
        """Download a dataset archive into destination directory and return its path."""
        raise NotImplementedError


class KaggleApiDatasetDownloader(KaggleDatasetDownloader):
    """Kaggle API-backed dataset downloader."""

    def download_dataset(
        self: KaggleApiDatasetDownloader,
        dataset_ref: str,
        dataset_version: int | None,
        destination_dir: Path,
    ) -> Path:
        try:
            import kaggle  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "kaggle package is required for KaggleBenchmarkAdapter. Install Kaggle API first."
            ) from exc

        api = kaggle.api
        api.authenticate()
        kwargs: dict[str, Any] = {
            "dataset": dataset_ref,
            "path": str(destination_dir),
            "quiet": True,
            "unzip": False,
            "force": True,
        }
        if dataset_version is not None:
            kwargs["dataset_version_number"] = dataset_version

        api.dataset_download_files(**kwargs)
        archives = sorted(destination_dir.glob("*.zip"), key=lambda entry: entry.stat().st_mtime)
        if not archives:
            raise FileNotFoundError(f"No downloaded archive found for dataset '{dataset_ref}'.")
        return archives[-1]


class KaggleBenchmarkAdapter:
    """Adapter that evaluates models against Kaggle benchmark datasets."""

    def __init__(
        self: KaggleBenchmarkAdapter,
        downloader: KaggleDatasetDownloader | None = None,
    ) -> None:
        self.downloader = downloader or KaggleApiDatasetDownloader()

    def run(
        self: KaggleBenchmarkAdapter,
        spec: BenchmarkSpec,
        model_fn: ModelFn,
        seed: int,
    ) -> HokusaiEvaluationManifest:
        """Run Kaggle benchmark evaluation and return HEM manifest."""
        self._validate_spec(spec)
        self._set_seed(seed)

        with tempfile.TemporaryDirectory(prefix="kaggle-benchmark-") as tmp_dir:
            temp_path = Path(tmp_dir)
            archive_path = self.downloader.download_dataset(
                dataset_ref=spec.dataset_ref,
                dataset_version=spec.dataset_version,
                destination_dir=temp_path,
            )
            extracted_path = temp_path / "extracted"
            extracted_path.mkdir(parents=True, exist_ok=True)
            with ZipFile(archive_path, "r") as zip_file:
                zip_file.extractall(path=extracted_path)

            split_path = extracted_path / spec.eval_split_path
            if not split_path.exists():
                raise FileNotFoundError(
                    f"Declared split '{spec.eval_split_path}' not found in dataset."
                )

            dataset_hash = _sha256_bytes(split_path.read_bytes())
            self._verify_dataset_hash(spec, dataset_hash)
            rows = _load_rows(split_path)

            predictions: list[Any] = []
            metric_value = 0.0
            if not spec.dry_run:
                predictions = [
                    model_fn(_build_model_input(row, spec.input_columns)) for row in rows
                ]
                metric_value = _compute_metric(
                    metric_name=spec.metric.name,
                    predictions=predictions,
                    targets=[row[spec.target_column] for row in rows],
                )

            predictions_hash = _sha256_json(predictions)
            dataset_snapshot_hash = f"sha256:{dataset_hash}"
            provenance = {
                "provider": "kaggle_benchmark_adapter",
                "provider_version": "1",
                "parameters": {
                    "dataset_ref": spec.dataset_ref,
                    "dataset_version_hash": spec.dataset_version_hash,
                    "dataset_snapshot_hash": dataset_snapshot_hash,
                    "predictions_hash": f"sha256:{predictions_hash}",
                    "metric_name": spec.metric.name,
                    "metric_version": spec.metric.version,
                    "eval_container_digest": spec.eval_container_digest,
                    "lockfile_hash": spec.lockfile_hash,
                    "code_commit": spec.code_commit,
                    "seed": seed,
                    "dry_run": spec.dry_run,
                    "metric": asdict(spec.metric),
                },
            }

            artifacts = [
                {
                    "name": "dataset_snapshot_hash",
                    "path": spec.eval_split_path,
                    "hash": dataset_snapshot_hash,
                    "type": "sha256",
                },
                {
                    "name": "predictions_hash",
                    "path": "predictions.json",
                    "hash": f"sha256:{predictions_hash}",
                    "type": "sha256",
                },
            ]

            return HokusaiEvaluationManifest(
                model_id=spec.model_id or "unknown-model",
                eval_id=spec.benchmark_id,
                dataset={
                    "id": f"kaggle:{spec.dataset_ref}:{spec.eval_split_path}",
                    "hash": dataset_snapshot_hash,
                    "num_samples": len(rows),
                },
                primary_metric={
                    "name": spec.metric.name,
                    "value": metric_value,
                    "higher_is_better": spec.metric.higher_is_better,
                },
                metrics=[
                    {
                        "name": spec.metric.name,
                        "value": metric_value,
                        "higher_is_better": spec.metric.higher_is_better,
                    }
                ],
                mlflow_run_id=spec.run_id or "local-run",
                artifacts=artifacts,
                provenance=provenance,
            )

    def _validate_spec(self: KaggleBenchmarkAdapter, spec: BenchmarkSpec) -> None:
        if not spec.dataset_ref:
            raise ValueError("benchmark spec missing dataset_ref")
        if not spec.dataset_version_hash:
            raise ValueError("benchmark spec missing dataset_version_hash")
        if not spec.eval_split_path:
            raise ValueError("benchmark spec missing eval_split_path")
        if not spec.target_column:
            raise ValueError("benchmark spec missing target_column")

    def _verify_dataset_hash(
        self: KaggleBenchmarkAdapter,
        spec: BenchmarkSpec,
        observed_hash: str,
    ) -> None:
        expected_hash = spec.expected_dataset_sha256
        if not expected_hash:
            return
        normalized_expected = expected_hash.removeprefix("sha256:")
        if normalized_expected != observed_hash:
            raise ValueError(
                "Dataset hash mismatch. "
                f"expected=sha256:{normalized_expected} observed=sha256:{observed_hash}"
            )

    def _set_seed(self: KaggleBenchmarkAdapter, seed: int) -> None:
        random.seed(seed)
        try:
            import numpy as np  # type: ignore
        except ImportError:
            return
        np.random.seed(seed)


def _build_model_input(row: dict[str, str], input_columns: list[str]) -> Any:
    if not input_columns:
        return dict(row)
    if len(input_columns) == 1:
        return row[input_columns[0]]
    return {column: row[column] for column in input_columns}


def _sha256_bytes(content: bytes) -> str:
    return sha256(content).hexdigest()


def _sha256_json(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _load_rows(split_path: Path) -> list[dict[str, str]]:
    suffix = split_path.suffix.lower()
    if suffix == ".csv":
        with split_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [dict(row) for row in reader]
    if suffix == ".jsonl":
        rows: list[dict[str, str]] = []
        with split_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("jsonl rows must be JSON objects")
                rows.append({str(key): str(value) for key, value in payload.items()})
        return rows
    raise ValueError(f"Unsupported split file format: {split_path.suffix}")


def _compute_metric(metric_name: str, predictions: list[Any], targets: list[str]) -> float:
    if len(predictions) != len(targets):
        raise ValueError("Predictions and targets length mismatch")
    if not targets:
        return 0.0

    normalized_name = metric_name.lower()
    if normalized_name in {"accuracy", "exact_match"}:
        correct = sum(
            1 for predicted, actual in zip(predictions, targets) if str(predicted) == str(actual)
        )
        return correct / len(targets)
    if normalized_name == "mse":
        errors = [
            (_as_float(predicted) - _as_float(actual)) ** 2
            for predicted, actual in zip(predictions, targets)
        ]
        return sum(errors) / len(errors)
    if normalized_name == "mae":
        errors = [
            abs(_as_float(predicted) - _as_float(actual))
            for predicted, actual in zip(predictions, targets)
        ]
        return sum(errors) / len(errors)

    raise ValueError(f"Unsupported metric '{metric_name}'.")


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Metric expects numeric values, got {value!r}") from exc
