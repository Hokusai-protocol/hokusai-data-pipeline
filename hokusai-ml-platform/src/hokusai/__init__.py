"""Hokusai ML Platform - Unified MLOps infrastructure for model management and tracking."""

from importlib import import_module
from typing import Any

__version__ = "1.0.0"
__author__ = "Hokusai Team"
__email__ = "team@hokus.ai"

__all__ = [
    "__version__",
    "ModelRegistry",
    "ModelVersionManager",
    "HokusaiModel",
    "HokusaiInferencePipeline",
    "ExperimentManager",
    "PerformanceTracker",
    "HokusaiAuth",
    "configure",
    "setup",
    "setup_mlflow_auth",
    "HokusaiException",
    "MLflowConnectionError",
    "MLflowAuthenticationError",
    "ModelNotFoundError",
    "ConfigurationError",
]

_LAZY_IMPORTS = {
    "HokusaiModel": ("hokusai.core.models", "HokusaiModel"),
    "ModelRegistry": ("hokusai.core.registry", "ModelRegistry"),
    "ModelVersionManager": ("hokusai.core.versioning", "ModelVersionManager"),
    "HokusaiInferencePipeline": ("hokusai.core.inference", "HokusaiInferencePipeline"),
    "ExperimentManager": ("hokusai.tracking.experiments", "ExperimentManager"),
    "PerformanceTracker": ("hokusai.tracking.performance", "PerformanceTracker"),
    "HokusaiAuth": ("hokusai.auth", "HokusaiAuth"),
    "configure": ("hokusai.auth.client", "configure"),
    "setup": ("hokusai.auth.client", "setup"),
    "setup_mlflow_auth": ("hokusai.config", "setup_mlflow_auth"),
    "HokusaiException": ("hokusai.exceptions", "HokusaiException"),
    "MLflowConnectionError": ("hokusai.exceptions", "MLflowConnectionError"),
    "MLflowAuthenticationError": ("hokusai.exceptions", "MLflowAuthenticationError"),
    "ModelNotFoundError": ("hokusai.exceptions", "ModelNotFoundError"),
    "ConfigurationError": ("hokusai.exceptions", "ConfigurationError"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        module = import_module(module_path)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'hokusai' has no attribute {name}")
