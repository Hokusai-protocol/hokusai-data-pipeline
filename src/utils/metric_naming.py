"""Canonical metric-name normalization for Hokusai.

Single source of truth for the Hokusai-name → MLflow-key contract.
Any change to the replacement rules here MUST be reflected in MetricLogger
(src/utils/metrics.py) and validated against DeltaOne lookup
(src/evaluation/deltaone_evaluator.py).

Invariant (v1): only colon → underscore substitution is performed.

Authentication note: this module performs pure string transformation and does not
interact with the MLflow tracking API directly.  Authentication (MLFLOW_TRACKING_TOKEN /
Authorization headers) is configured at the MetricLogger and MlflowClient call sites.
"""

from __future__ import annotations

import re

# MLflow rejects keys containing colons; allow alphanumeric, underscore, dash,
# dot, slash, and space (MLflow's own documented allowed characters).
MLFLOW_METRIC_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_\-./ ]+$")


def normalize_mlflow_metric_key(name: str) -> str:
    """Return the MLflow-safe key for *name*.

    Strips leading/trailing whitespace and replaces colons with underscores,
    matching the substitution MetricLogger performs before calling the MLflow
    tracking API.

    Raises ``ValueError`` if the resulting key is empty.
    """
    key = name.strip().replace(":", "_")
    if not key:
        raise ValueError(f"Metric name {name!r} produces an empty MLflow key after normalization.")
    return key


def derive_mlflow_name(name: str, override: str | None = None) -> str:
    """Return the MLflow key to use for a metric.

    Uses *override* when it is non-empty; otherwise derives it from *name* via
    ``normalize_mlflow_metric_key``.  An explicit empty-string override is
    treated the same as *None* (i.e. auto-derived).
    """
    if override:
        validate_mlflow_metric_key(override)
        return override
    return normalize_mlflow_metric_key(name)


def validate_mlflow_metric_key(key: str) -> None:
    """Raise ``ValueError`` if *key* is not a valid MLflow metric key.

    Valid keys match ``MLFLOW_METRIC_KEY_PATTERN`` (alphanumeric plus
    ``_``, ``-``, ``.``, ``/``, and space).  Colons are not allowed because
    MLflow rejects them at ingest time.
    """
    if not key:
        raise ValueError("MLflow metric key must not be empty.")
    if not MLFLOW_METRIC_KEY_PATTERN.match(key):
        raise ValueError(
            f"Invalid MLflow metric key {key!r}. "
            "Keys may only contain letters, digits, underscores, hyphens, "
            "dots, forward-slashes, and spaces (no colons)."
        )
