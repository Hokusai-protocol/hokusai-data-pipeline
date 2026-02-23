"""Provider-agnostic evaluation interfaces."""

from typing import Protocol, runtime_checkable

from src.evaluation.adapters.base import BenchmarkSpec, ModelFn
from src.evaluation.manifest import HokusaiEvaluationManifest


@runtime_checkable
class EvalAdapter(Protocol):
    """Lightweight adapter for external evaluation frameworks.

    Implementations run an evaluation and log results to MLflow,
    returning the MLflow run ID for tracking.
    """

    def run(self: "EvalAdapter", eval_spec: str, model_ref: str) -> str:
        """Run an evaluation and return the MLflow run ID."""
        ...


@runtime_checkable
class AbstractBenchmarkAdapter(Protocol):
    """Protocol for benchmark adapters that produce HEM manifests."""

    def run(
        self: "AbstractBenchmarkAdapter",
        spec: BenchmarkSpec,
        model_fn: ModelFn,
        seed: int,
    ) -> HokusaiEvaluationManifest:
        """Run a benchmark and return a HokusaiEvaluationManifest."""
        ...
