"""Tracking module for experiment management and performance tracking.

Both ``ExperimentManager`` and ``PerformanceTracker`` depend on MLflow and
are loaded lazily.  Accessing them without the ``[ml]`` extra installed
raises ``MissingMLExtraError`` with an actionable install command.
"""

from typing import Any

_ML_ATTRS = {
    "ExperimentManager": ".tracking.experiments",
    "PerformanceTracker": ".tracking.performance",
}


def __getattr__(name: str) -> Any:
    if name in _ML_ATTRS:
        from hokusai._lazy import lazy_import

        value = lazy_import(name, _ML_ATTRS[name], package="hokusai")
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ExperimentManager", "PerformanceTracker"]
