"""Deterministic custom scorer registry."""

from __future__ import annotations

# Trigger built-in scorer registration side effects.
from src.evaluation.scorers import builtin as _builtin  # noqa: F401
from src.evaluation.scorers.metadata import Aggregation, MetricFamily, ScorerMetadata
from src.evaluation.scorers.registry import (
    ScorerConflictError,
    UnknownScorerError,
    clear_scorers,
    list_scorers,
    register_scorer,
    resolve_scorer,
)

__all__ = [
    "Aggregation",
    "MetricFamily",
    "ScorerMetadata",
    "ScorerConflictError",
    "UnknownScorerError",
    "clear_scorers",
    "list_scorers",
    "register_scorer",
    "resolve_scorer",
]
