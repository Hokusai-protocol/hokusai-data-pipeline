"""Shared utilities for creating and registering MLflow judges.

Authentication for MLflow judge execution is expected via ``MLFLOW_TRACKING_TOKEN``
or equivalent tracking server auth configuration in the runtime environment.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class JudgeConfig:
    """Configuration shared by all judge template factories."""

    model: str = "anthropic:/claude-opus-4-1-20250805"
    temperature: float = 0.0
    name_prefix: str = "hokusai"

    def __post_init__(self: JudgeConfig) -> None:
        """Validate basic config constraints."""
        if not 0.0 <= self.temperature <= 1.0:
            raise ValueError("temperature must be between 0.0 and 1.0")
        if not self.name_prefix:
            raise ValueError("name_prefix must be non-empty")


def _build_name(base_name: str, config: JudgeConfig) -> str:
    """Build a stable judge name with configurable prefix."""
    return f"{config.name_prefix}_{base_name}" if config.name_prefix else base_name


def _import_make_judge() -> Any:
    """Import ``mlflow.genai.make_judge`` lazily."""
    from mlflow.genai import make_judge

    return make_judge


def _import_list_scorers() -> Any:
    """Import ``mlflow.genai.scorers.list_scorers`` lazily."""
    from mlflow.genai.scorers import list_scorers

    return list_scorers


def create_judge(base_name: str, instructions: str, config: JudgeConfig | None = None) -> Any:
    """Create an MLflow judge with the verified ``make_judge`` runtime API."""
    cfg = config or JudgeConfig()
    make_judge = _import_make_judge()
    return make_judge(
        name=_build_name(base_name=base_name, config=cfg),
        instructions=instructions,
        model=cfg.model,
    )


def register_judge(judge: Any, name: str | None = None, experiment_id: str | None = None) -> Any:
    """Register a judge when the runtime object exposes ``register``.

    MLflow 3.4 does not provide ``mlflow.genai.register_judge`` as a module-level
    function. Registration is performed via ``judge.register(...)`` when available.
    """
    register = getattr(judge, "register", None)
    if callable(register):
        return register(name=name, experiment_id=experiment_id)

    warnings.warn(
        "Judge object does not support register(); returning the original object.",
        RuntimeWarning,
        stacklevel=2,
    )
    return judge


def list_registered_judges(experiment_id: str | None = None) -> list[Any]:
    """List registered judges/scorers from MLflow if supported by the runtime."""
    try:
        list_scorers = _import_list_scorers()
    except Exception:
        return []

    return list(list_scorers(experiment_id=experiment_id))
