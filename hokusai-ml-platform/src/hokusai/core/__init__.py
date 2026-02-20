"""Core components of Hokusai ML Platform.

Base modules (``models``, ``ab_testing``) are always importable.
ML-dependent modules (``registry``, ``inference``, ``versioning``,
``mlflow_rest_store``) require the ``[ml]`` extra and are loaded lazily.
"""

from typing import Any

from .ab_testing import (
    ABTestConfig,
    ABTestException,
    ABTestResult,
    ModelTrafficRouter,
    TrafficSplit,
)
from .models import (
    ClassificationModel,
    CustomModel,
    HokusaiModel,
    ModelFactory,
    ModelType,
    RegressionModel,
)

# --- Lazy ML-dependent exports ----------------------------------------------

_ML_ATTRS = {
    # registry
    "ModelRegistry": ".core.registry",
    "ModelRegistryEntry": ".core.registry",
    "ModelLineage": ".core.registry",
    "RegistryException": ".core.registry",
    # versioning
    "ModelVersionManager": ".core.versioning",
    "Version": ".core.versioning",
    "VersionComparisonResult": ".core.versioning",
    "VersioningException": ".core.versioning",
    # inference
    "HokusaiInferencePipeline": ".core.inference",
    "InferenceRequest": ".core.inference",
    "InferenceResponse": ".core.inference",
    "CacheConfig": ".core.inference",
    "BatchProcessor": ".core.inference",
    "InferenceException": ".core.inference",
}


def __getattr__(name: str) -> Any:
    if name in _ML_ATTRS:
        from hokusai._lazy import lazy_import

        value = lazy_import(name, _ML_ATTRS[name], package="hokusai")
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Models (base)
    "HokusaiModel",
    "ModelFactory",
    "ModelType",
    "ClassificationModel",
    "RegressionModel",
    "CustomModel",
    # A/B Testing (base)
    "ModelTrafficRouter",
    "ABTestConfig",
    "ABTestResult",
    "TrafficSplit",
    "ABTestException",
    # Registry (ml)
    "ModelRegistry",
    "ModelRegistryEntry",
    "ModelLineage",
    "RegistryException",
    # Versioning (ml)
    "ModelVersionManager",
    "Version",
    "VersionComparisonResult",
    "VersioningException",
    # Inference (ml)
    "HokusaiInferencePipeline",
    "InferenceRequest",
    "InferenceResponse",
    "CacheConfig",
    "BatchProcessor",
    "InferenceException",
]
