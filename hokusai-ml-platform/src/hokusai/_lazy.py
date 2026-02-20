"""Lazy-import utilities for Hokusai SDK modular installation.

This module provides helpers for deferring imports of ML-heavy dependencies
(mlflow, metaflow, scikit-learn, redis, numpy, pandas) so that users who
only need base SDK features (auth, exceptions, data models) can install
the lightweight ``hokusai-ml-platform`` package without pulling in ~800 MB
of ML libraries.

Usage in ``__init__.py`` files::

    from hokusai._lazy import lazy_import

    _ML_ATTRS = {
        "ModelRegistry": ".core.registry",
        "ExperimentManager": ".tracking.experiments",
    }

    def __getattr__(name: str):
        if name in _ML_ATTRS:
            return lazy_import(name, _ML_ATTRS[name], package=__name__)
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
"""

from __future__ import annotations

import importlib
from typing import Any


class MissingMLExtraError(ImportError):
    """Raised when an ML-dependent feature is accessed without the ``[ml]`` extra.

    The error message tells the user exactly which command to run::

        pip install hokusai-ml-platform[ml]
    """

    def __init__(self: MissingMLExtraError, feature_name: str) -> None:
        self.feature_name = feature_name
        super().__init__(
            f"'{feature_name}' requires ML dependencies that are not installed.\n"
            f"Install them with:  pip install hokusai-ml-platform[ml]"
        )


def require_ml_extra(feature_name: str) -> None:
    """Raise ``MissingMLExtraError`` with an actionable message.

    Call this inside a ``try/except ImportError`` block when an ML-only
    module fails to import.

    Args:
    ----
        feature_name: Human-readable name of the feature the user tried
            to access.

    Raises:
    ------
        MissingMLExtraError: Always.

    """
    raise MissingMLExtraError(feature_name)


def lazy_import(attr_name: str, module_path: str, *, package: str | None = None) -> Any:
    """Import *attr_name* from *module_path* on first access.

    If the import fails because an ML dependency is missing, a
    ``MissingMLExtraError`` error is raised with an actionable message.

    Args:
    ----
        attr_name: The attribute name being requested
            (e.g. ``"ModelRegistry"``).
        module_path: Dotted module path to import from
            (e.g. ``".core.registry"``).
        package: The anchor package for relative imports.

    Returns:
    -------
        The requested attribute.

    Raises:
    ------
        MissingMLExtraError: If the underlying import fails due to a
            missing ML dependency.

    """
    try:
        module = importlib.import_module(module_path, package=package)
    except ImportError as exc:
        raise MissingMLExtraError(attr_name) from exc
    return getattr(module, attr_name)
