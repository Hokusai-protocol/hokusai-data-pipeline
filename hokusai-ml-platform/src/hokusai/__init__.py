"""Hokusai ML Platform - Unified MLOps infrastructure for model management and tracking."""

from typing import Any

__version__ = "1.0.0"
__author__ = "Hokusai Team"
__email__ = "team@hokus.ai"

__all__ = [
    "__version__",
    # Base (always available)
    "HokusaiAuth",
    "configure",
    "setup",
    "HokusaiException",
    "MLflowConnectionError",
    "MLflowAuthenticationError",
    "ModelNotFoundError",
    "ConfigurationError",
    "HokusaiModel",
    # ML-dependent (require hokusai-ml-platform[ml])
    "ModelRegistry",
    "ModelVersionManager",
    "HokusaiInferencePipeline",
    "ExperimentManager",
    "PerformanceTracker",
    "setup_mlflow_auth",
]

# --- Base imports: always available without [ml] extra -----------------------

_BASE_IMPORTS = {
    "HokusaiModel": ("hokusai.core.models", "HokusaiModel"),
    "HokusaiAuth": ("hokusai.auth", "HokusaiAuth"),
    "configure": ("hokusai.auth.client", "configure"),
    "setup": ("hokusai.auth.client", "setup"),
    "HokusaiException": ("hokusai.exceptions", "HokusaiException"),
    "MLflowConnectionError": ("hokusai.exceptions", "MLflowConnectionError"),
    "MLflowAuthenticationError": ("hokusai.exceptions", "MLflowAuthenticationError"),
    "ModelNotFoundError": ("hokusai.exceptions", "ModelNotFoundError"),
    "ConfigurationError": ("hokusai.exceptions", "ConfigurationError"),
}

# --- ML imports: require [ml] extra -----------------------------------------

_ML_IMPORTS = {
    "ModelRegistry": ("hokusai.core.registry", "ModelRegistry"),
    "ModelVersionManager": ("hokusai.core.versioning", "ModelVersionManager"),
    "HokusaiInferencePipeline": ("hokusai.core.inference", "HokusaiInferencePipeline"),
    "ExperimentManager": ("hokusai.tracking.experiments", "ExperimentManager"),
    "PerformanceTracker": ("hokusai.tracking.performance", "PerformanceTracker"),
    "setup_mlflow_auth": ("hokusai.config", "setup_mlflow_auth"),
}


def __getattr__(name: str) -> Any:
    if name in _BASE_IMPORTS:
        from importlib import import_module

        module_path, attr_name = _BASE_IMPORTS[name]
        module = import_module(module_path)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value

    if name in _ML_IMPORTS:
        from importlib import import_module

        module_path, attr_name = _ML_IMPORTS[name]
        try:
            module = import_module(module_path)
        except ImportError:
            from hokusai._lazy import require_ml_extra

            require_ml_extra(name)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value

    raise AttributeError(f"module 'hokusai' has no attribute {name!r}")
