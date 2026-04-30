"""Scorer metadata types for the deterministic custom scorer registry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class MetricFamily(str, Enum):
    """High-level category for the metric a scorer produces."""

    OUTCOME = "OUTCOME"
    QUALITY = "QUALITY"
    COST = "COST"
    LATENCY = "LATENCY"


class Aggregation(str, Enum):
    """Deterministic aggregation semantics for a scorer over a list of values."""

    MEAN = "MEAN"
    SUM = "SUM"
    PASS_RATE = "PASS_RATE"
    WEIGHTED_MEAN = "WEIGHTED_MEAN"
    MIN = "MIN"
    MAX = "MAX"


@dataclass(frozen=True)
class ScorerMetadata:
    """Immutable metadata describing a deterministic outcome scorer."""

    scorer_ref: str
    version: str
    input_schema: dict[str, Any]
    output_metric_keys: tuple[str, ...]
    metric_family: MetricFamily
    aggregation: Aggregation
    source_hash: str
    description: str | None = None
