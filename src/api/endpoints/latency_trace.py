"""Structured request-scoped latency tracing for model 30 inference."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager


class Model30LatencyTrace:
    """Collect phase timings and emit a single structured log record."""

    PHASES = (
        "request_validation",
        "model_cache_lookup",
        "artifact_load",
        "preprocessor_setup",
        "feature_transformation",
        "model_inference",
        "postprocessing_serialization",
    )

    def __init__(self: Model30LatencyTrace, request_id: str, model_uri: str) -> None:
        self.request_id = request_id
        self.model_uri = model_uri
        self.path_type = "unknown"
        self.run_id: str | None = None
        self.outcome = "success"
        self.deadline_boundary_ms = 0.0
        self._timings: dict[str, float] = {}
        self._started_at: dict[str, float] = {}

    def start_phase(self: Model30LatencyTrace, phase: str) -> None:
        """Start timing a named phase."""
        self._started_at[phase] = time.perf_counter()

    def end_phase(self: Model30LatencyTrace, phase: str) -> None:
        """Stop timing a named phase and accumulate its duration."""
        started_at = self._started_at.pop(phase, None)
        if started_at is None:
            return
        self._timings[phase] = (
            self._timings.get(phase, 0.0) + (time.perf_counter() - started_at) * 1000
        )

    @contextmanager
    def phase(self: Model30LatencyTrace, name: str) -> Iterator[None]:
        """Context manager wrapper around start/end timing."""
        self.start_phase(name)
        try:
            yield
        finally:
            self.end_phase(name)

    def record_ms(self: Model30LatencyTrace, phase: str, duration_ms: float) -> None:
        """Set a phase duration directly from external instrumentation."""
        self._timings[phase] = max(float(duration_ms), 0.0)

    def set_path_type(self: Model30LatencyTrace, cached: bool) -> None:
        """Mark the request as a warm or cold path based on cache state."""
        self.path_type = "warm" if cached else "cold"

    def emit(self: Model30LatencyTrace, logger: logging.Logger) -> None:
        """Emit the correlated latency trace as a single structured record."""
        phase_timings = {phase: round(self._timings.get(phase, 0.0), 2) for phase in self.PHASES}
        dominant_candidates = dict(phase_timings)
        dominant_candidates["timeout_deadline_boundary_ms"] = round(self.deadline_boundary_ms, 2)
        dominant_phase_key = max(dominant_candidates, key=dominant_candidates.get)
        dominant_phase = dominant_phase_key.removesuffix("_ms")
        total_ms = round(sum(phase_timings.values()), 2)

        logger.info(
            "model_30_latency_trace",
            extra={
                "event": "model_30_latency_trace",
                "request_id": self.request_id,
                "model_id": "30",
                "model_uri": self.model_uri,
                "path_type": self.path_type,
                "outcome": self.outcome,
                "run_id": self.run_id,
                "dominant_phase": dominant_phase,
                "total_ms": total_ms,
                "timeout_deadline_boundary_ms": round(self.deadline_boundary_ms, 2),
                **{f"{phase}_ms": duration_ms for phase, duration_ms in phase_timings.items()},
            },
        )
