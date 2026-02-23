"""Evaluation package public API with lazy imports."""

from __future__ import annotations

from typing import Any

__all__ = [
    "EvalAdapter",
    "register_adapter",
    "get_adapter",
    "list_adapters",
    "clear_adapters",
    "HEM_V1_SCHEMA",
    "HokusaiEvaluationManifest",
    "create_hem_from_mlflow_run",
    "log_hem_to_mlflow",
    "validate_manifest",
]

_MODULE_MAP: dict[str, tuple[str, str]] = {
    "EvalAdapter": ("src.evaluation.interfaces", "EvalAdapter"),
    "register_adapter": ("src.evaluation.provider_registry", "register_adapter"),
    "get_adapter": ("src.evaluation.provider_registry", "get_adapter"),
    "list_adapters": ("src.evaluation.provider_registry", "list_adapters"),
    "clear_adapters": ("src.evaluation.provider_registry", "clear_adapters"),
    "HEM_V1_SCHEMA": ("src.evaluation.schema", "HEM_V1_SCHEMA"),
    "HokusaiEvaluationManifest": ("src.evaluation.manifest", "HokusaiEvaluationManifest"),
    "create_hem_from_mlflow_run": ("src.evaluation.manifest", "create_hem_from_mlflow_run"),
    "log_hem_to_mlflow": ("src.evaluation.manifest", "log_hem_to_mlflow"),
    "validate_manifest": ("src.evaluation.validation", "validate_manifest"),
}


def __getattr__(name: str) -> Any:
    """Dynamically resolve module attributes on first access."""
    try:
        module_path, attr_name = _MODULE_MAP[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    module = __import__(module_path, fromlist=[attr_name])
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return the module attributes for introspection."""
    return sorted(set(globals()) | set(__all__))
