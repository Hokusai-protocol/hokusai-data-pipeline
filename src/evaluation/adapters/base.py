"""Benchmark adapter protocol and benchmark spec models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from src.evaluation.manifest import HokusaiEvaluationManifest


@dataclass
class MetricSpec:
    """Metric configuration declared by a benchmark spec."""

    name: str
    version: str
    higher_is_better: bool = True


@dataclass
class BenchmarkSpec:
    """Normalized benchmark specification consumed by adapters."""

    benchmark_id: str
    dataset_ref: str
    dataset_version_hash: str
    eval_split_path: str
    metric: MetricSpec
    target_column: str
    input_columns: list[str] = field(default_factory=list)
    expected_dataset_sha256: str | None = None
    dataset_version: int | None = None
    eval_container_digest: str | None = None
    lockfile_hash: str | None = None
    code_commit: str | None = None
    run_id: str | None = None
    model_id: str | None = None
    dry_run: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls: type[BenchmarkSpec], payload: dict[str, Any]) -> BenchmarkSpec:
        """Build a normalized benchmark spec from a dictionary payload."""
        metric_payload = payload.get("metric") or {}
        metric = MetricSpec(
            name=str(metric_payload.get("name", "accuracy")),
            version=str(metric_payload.get("version", "1")),
            higher_is_better=bool(metric_payload.get("higher_is_better", True)),
        )
        input_columns = payload.get("input_columns")
        if input_columns is None:
            input_columns = []
        if isinstance(input_columns, str):
            input_columns = [input_columns]

        return cls(
            benchmark_id=str(payload.get("benchmark_id") or payload.get("eval_id") or "unknown"),
            dataset_ref=str(payload.get("dataset_ref") or payload.get("dataset") or ""),
            dataset_version_hash=str(payload.get("dataset_version_hash") or ""),
            expected_dataset_sha256=payload.get("expected_dataset_sha256"),
            dataset_version=payload.get("dataset_version"),
            eval_split_path=str(payload.get("eval_split_path") or payload.get("split") or ""),
            metric=metric,
            target_column=str(payload.get("target_column") or "label"),
            input_columns=[str(column) for column in input_columns],
            eval_container_digest=payload.get("eval_container_digest"),
            lockfile_hash=payload.get("lockfile_hash"),
            code_commit=payload.get("code_commit"),
            run_id=payload.get("run_id"),
            model_id=payload.get("model_id"),
            dry_run=bool(payload.get("dry_run", False)),
            metadata=dict(payload.get("metadata") or {}),
        )


@runtime_checkable
class AbstractBenchmarkAdapter(Protocol):
    """Protocol for benchmark adapters that emit HEM outputs."""

    def run(
        self: AbstractBenchmarkAdapter,
        spec: BenchmarkSpec,
        model_fn: ModelFn,
        seed: int,
    ) -> HokusaiEvaluationManifest:
        """Run benchmark evaluation and return a HEM manifest."""
        ...


class ModelFn(Protocol):
    """Callable protocol for model prediction functions."""

    def __call__(self: ModelFn, inputs: Any) -> Any:
        """Return model prediction(s) for a single input payload."""
        ...
