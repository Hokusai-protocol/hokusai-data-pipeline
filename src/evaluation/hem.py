"""Hokusai Evaluation Metric (HEM) primitives for DeltaOne evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class HEM:
    """Minimal metric record used by DeltaOne statistical comparisons."""

    metric_name: str
    metric_value: float
    sample_size: int
    dataset_hash: str
    timestamp: datetime
    source_mlflow_run_id: str
    model_id: str
    experiment_id: str
    confidence_interval_lower: float | None = None
    confidence_interval_upper: float | None = None
