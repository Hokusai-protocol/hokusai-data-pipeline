"""Integration-style tests for KaggleBenchmarkAdapter using local fixture archives."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

import pytest

from src.evaluation.adapters import BenchmarkSpec, KaggleBenchmarkAdapter, MetricSpec


class StaticDownloader:
    def __init__(self, archive_path: Path) -> None:
        self.archive_path = archive_path

    def download_dataset(
        self,
        dataset_ref: str,
        dataset_version: int | None,
        destination_dir: Path,
    ) -> Path:
        _ = dataset_ref
        _ = dataset_version
        _ = destination_dir
        return self.archive_path


def _create_fixture_archive(tmp_path: Path) -> tuple[Path, str]:
    csv_payload = "text,label\nalpha,yes\nbeta,no\n"
    split_path = tmp_path / "eval.csv"
    split_path.write_text(csv_payload, encoding="utf-8")

    archive_path = tmp_path / "dataset.zip"
    with ZipFile(archive_path, "w") as zip_file:
        zip_file.write(split_path, arcname="eval.csv")

    expected_hash = sha256(csv_payload.encode("utf-8")).hexdigest()
    return archive_path, expected_hash


def _base_spec(expected_hash: str, dry_run: bool = False) -> BenchmarkSpec:
    return BenchmarkSpec(
        benchmark_id="bench-kaggle-1",
        dataset_ref="owner/sample-dataset",
        dataset_version_hash="vhash-123",
        dataset_version=7,
        expected_dataset_sha256=expected_hash,
        eval_split_path="eval.csv",
        input_columns=["text"],
        target_column="label",
        metric=MetricSpec(name="accuracy", version="1", higher_is_better=True),
        eval_container_digest="sha256:container",
        code_commit="abc123",
        lockfile_hash="sha256:lock",
        model_id="model-a",
        run_id="run-a",
        dry_run=dry_run,
    )


def test_kaggle_adapter_runs_and_emits_manifest(tmp_path: Path) -> None:
    archive_path, expected_hash = _create_fixture_archive(tmp_path)
    adapter = KaggleBenchmarkAdapter(downloader=StaticDownloader(archive_path))
    spec = _base_spec(expected_hash)

    def model_fn(text: str) -> str:
        return "yes" if text == "alpha" else "no"

    manifest = adapter.run(spec=spec, model_fn=model_fn, seed=42)

    assert manifest.eval_id == "bench-kaggle-1"
    assert manifest.dataset["hash"] == f"sha256:{expected_hash}"
    assert manifest.primary_metric["name"] == "accuracy"
    assert manifest.primary_metric["value"] == 1.0
    assert manifest.provenance is not None
    assert manifest.provenance["parameters"]["metric_version"] == "1"
    assert manifest.provenance["parameters"]["predictions_hash"].startswith("sha256:")


def test_kaggle_adapter_supports_dry_run(tmp_path: Path) -> None:
    archive_path, expected_hash = _create_fixture_archive(tmp_path)
    adapter = KaggleBenchmarkAdapter(downloader=StaticDownloader(archive_path))
    spec = _base_spec(expected_hash, dry_run=True)

    def model_fn(_: str) -> str:
        raise AssertionError("model_fn should not be called in dry-run mode")

    manifest = adapter.run(spec=spec, model_fn=model_fn, seed=7)
    assert manifest.primary_metric["value"] == 0.0
    assert manifest.dataset["num_samples"] == 2


def test_kaggle_adapter_detects_hash_mismatch(tmp_path: Path) -> None:
    archive_path, expected_hash = _create_fixture_archive(tmp_path)
    adapter = KaggleBenchmarkAdapter(downloader=StaticDownloader(archive_path))
    spec = _base_spec(expected_hash + "bad")

    with pytest.raises(ValueError, match="Dataset hash mismatch"):
        adapter.run(spec=spec, model_fn=lambda _: "yes", seed=1)
