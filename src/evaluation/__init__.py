"""Evaluation package public API with lazy imports."""

from __future__ import annotations

from typing import Any

__all__ = [
    "EvalAdapter",
    "AbstractBenchmarkAdapter",
    "BenchmarkSpec",
    "MetricSpec",
    "KaggleBenchmarkAdapter",
    "register_benchmark_adapter",
    "get_benchmark_adapter",
    "list_benchmark_adapters",
    "clear_benchmark_adapters",
    "register_adapter",
    "get_adapter",
    "list_adapters",
    "clear_adapters",
    "HEM",
    "DeltaOneDecision",
    "DeltaOneEvaluator",
    "DeltaOneMintOrchestrator",
    "MintOutcome",
    "detect_delta_one",
    "send_deltaone_webhook",
    "HEM_V1_SCHEMA",
    "HokusaiEvaluationManifest",
    "create_hem_from_mlflow_run",
    "log_hem_to_mlflow",
    "validate_manifest",
]

_MODULE_MAP: dict[str, tuple[str, str]] = {
    "EvalAdapter": ("src.evaluation.interfaces", "EvalAdapter"),
    "AbstractBenchmarkAdapter": ("src.evaluation.interfaces", "AbstractBenchmarkAdapter"),
    "BenchmarkSpec": ("src.evaluation.adapters.base", "BenchmarkSpec"),
    "MetricSpec": ("src.evaluation.adapters.base", "MetricSpec"),
    "KaggleBenchmarkAdapter": ("src.evaluation.adapters.kaggle", "KaggleBenchmarkAdapter"),
    "register_benchmark_adapter": (
        "src.evaluation.adapters.registry",
        "register_benchmark_adapter",
    ),
    "get_benchmark_adapter": ("src.evaluation.adapters.registry", "get_benchmark_adapter"),
    "list_benchmark_adapters": ("src.evaluation.adapters.registry", "list_benchmark_adapters"),
    "clear_benchmark_adapters": ("src.evaluation.adapters.registry", "clear_benchmark_adapters"),
    "register_adapter": ("src.evaluation.provider_registry", "register_adapter"),
    "get_adapter": ("src.evaluation.provider_registry", "get_adapter"),
    "list_adapters": ("src.evaluation.provider_registry", "list_adapters"),
    "clear_adapters": ("src.evaluation.provider_registry", "clear_adapters"),
    "HEM": ("src.evaluation.hem", "HEM"),
    "DeltaOneDecision": ("src.evaluation.deltaone_evaluator", "DeltaOneDecision"),
    "DeltaOneEvaluator": ("src.evaluation.deltaone_evaluator", "DeltaOneEvaluator"),
    "DeltaOneMintOrchestrator": (
        "src.evaluation.deltaone_mint_orchestrator",
        "DeltaOneMintOrchestrator",
    ),
    "MintOutcome": ("src.evaluation.deltaone_mint_orchestrator", "MintOutcome"),
    "detect_delta_one": ("src.evaluation.deltaone_evaluator", "detect_delta_one"),
    "send_deltaone_webhook": ("src.evaluation.deltaone_evaluator", "send_deltaone_webhook"),
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
