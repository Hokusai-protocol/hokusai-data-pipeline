"""Provider-agnostic evaluation interfaces."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class EvalAdapter(Protocol):
    """Lightweight adapter for external evaluation frameworks.

    Implementations run an evaluation and log results to MLflow,
    returning the MLflow run ID for tracking.
    """

    def run(self: "EvalAdapter", eval_spec: str, model_ref: str) -> str:
        """Run an evaluation and return the MLflow run ID."""
        ...
