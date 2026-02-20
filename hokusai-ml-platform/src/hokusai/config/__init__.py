"""Configuration utilities for Hokusai SDK.

All configuration modules depend on MLflow and are loaded lazily.
Accessing them without the ``[ml]`` extra installed raises
``MissingMLExtraError`` with an actionable install command.
"""

from typing import Any

_ML_ATTRS = {
    "MLflowAuthConfig": ".config.mlflow_auth",
    "setup_mlflow_auth": ".config.mlflow_auth",
    "get_mlflow_auth_status": ".config.mlflow_auth",
    "setup_mlflow": ".config.mlflow_setup",
    "get_mlflow_status": ".config.mlflow_setup",
    "ensure_mlflow_configured": ".config.mlflow_setup",
}


def __getattr__(name: str) -> Any:
    if name in _ML_ATTRS:
        from hokusai._lazy import lazy_import

        value = lazy_import(name, _ML_ATTRS[name], package="hokusai")
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "MLflowAuthConfig",
    "setup_mlflow_auth",
    "get_mlflow_auth_status",
    "setup_mlflow",
    "get_mlflow_status",
    "ensure_mlflow_configured",
]
