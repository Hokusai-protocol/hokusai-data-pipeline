#!/usr/bin/env python3
"""Profile Model 30 inference against a supplied MLflow model artifact.

Example:
-------
    MODEL_30_MLFLOW_URI=/tmp/hok1876/m-f02ce \
    python -m scripts.model_30.profile_inference \
      --model-uri /tmp/hok1876/m-f02ce \
      --warm-iterations 200 \
      --cold-iterations 5

"""

from __future__ import annotations

import argparse
import asyncio
import cProfile
import io
import json
import logging
import os
import pstats
import resource
import socket
import statistics
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from scripts.diagnostics.compare_model_30_vs_21_latency import _serve_model
from src.api.endpoints.model_30_adapter import (
    call_mlflow_model_30,
    model_30_inputs_to_features,
    normalize_model_30_output,
    reset_model_30_cache,
    validate_nested_model_30_inputs,
)
from src.api.endpoints.model_registry_entries import MODEL_CONFIGS
from src.api.endpoints.model_serving import ModelServingService

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAYLOAD = REPO_ROOT / "data/test_fixtures/model_30_curated_payload.json"
DEFAULT_MLFLOW_URI = "file:///tmp/mlruns"
MODEL_30_TRACE_EVENT = "model_30_latency_trace"


@dataclass(slots=True)
class TraceSample:
    """One captured Model 30 latency trace sample."""

    total_ms: float
    request_validation_ms: float
    model_cache_lookup_ms: float
    artifact_load_ms: float
    preprocessor_setup_ms: float
    feature_transformation_ms: float
    model_inference_ms: float
    postprocessing_serialization_ms: float

    def as_dict(self: TraceSample) -> dict[str, float]:
        return {
            "total_ms": self.total_ms,
            "request_validation_ms": self.request_validation_ms,
            "model_cache_lookup_ms": self.model_cache_lookup_ms,
            "artifact_load_ms": self.artifact_load_ms,
            "preprocessor_setup_ms": self.preprocessor_setup_ms,
            "feature_transformation_ms": self.feature_transformation_ms,
            "model_inference_ms": self.model_inference_ms,
            "postprocessing_serialization_ms": self.postprocessing_serialization_ms,
        }


class _TraceCapture(logging.Handler):
    def __init__(self: _TraceCapture) -> None:
        super().__init__(level=logging.INFO)
        self.records: list[logging.LogRecord] = []

    def emit(self: _TraceCapture, record: logging.LogRecord) -> None:
        self.records.append(record)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-uri", required=True)
    parser.add_argument("--payload", type=Path, default=DEFAULT_PAYLOAD)
    parser.add_argument("--warm-iterations", type=int, default=200)
    parser.add_argument("--cold-iterations", type=int, default=5)
    parser.add_argument("--mlflow-uri", default=DEFAULT_MLFLOW_URI)
    parser.add_argument("--profile-top", type=int, default=20)
    parser.add_argument("--output-json", action="store_true")
    return parser.parse_args(argv)


def aggregate_stats(samples: Sequence[float]) -> dict[str, float]:
    """Summarize percentile and central tendency metrics."""
    if not samples:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0, "n": 0}
    ordered = sorted(float(sample) for sample in samples)

    def _percentile(fraction: float) -> float:
        index = max(0, min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1)))))
        return round(ordered[index], 2)

    return {
        "p50": _percentile(0.50),
        "p95": _percentile(0.95),
        "p99": _percentile(0.99),
        "mean": round(statistics.mean(ordered), 2),
        "min": round(ordered[0], 2),
        "max": round(ordered[-1], 2),
        "n": len(ordered),
    }


def aggregate_trace_samples(samples: Sequence[TraceSample]) -> dict[str, dict[str, float]]:
    """Aggregate trace metrics phase by phase."""
    by_phase: dict[str, list[float]] = {}
    for sample in samples:
        for key, value in sample.as_dict().items():
            by_phase.setdefault(key, []).append(value)
    return {key: aggregate_stats(values) for key, values in by_phase.items()}


def _ru_maxrss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return int(value)
    return int(value * 1024)


def _current_rss_bytes() -> int | None:
    try:
        output = subprocess.check_output(  # noqa: S603,S607
            ["/bin/ps", "-o", "rss=", "-p", str(os.getpid())],
            text=True,
        )
    except Exception:
        return None
    rss_kib = output.strip()
    return int(rss_kib) * 1024 if rss_kib else None


def _load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_trace_sample(record: logging.LogRecord) -> TraceSample:
    return TraceSample(
        total_ms=round(float(getattr(record, "total_ms", 0.0)), 2),
        request_validation_ms=round(float(getattr(record, "request_validation_ms", 0.0)), 2),
        model_cache_lookup_ms=round(float(getattr(record, "model_cache_lookup_ms", 0.0)), 2),
        artifact_load_ms=round(float(getattr(record, "artifact_load_ms", 0.0)), 2),
        preprocessor_setup_ms=round(float(getattr(record, "preprocessor_setup_ms", 0.0)), 2),
        feature_transformation_ms=round(
            float(getattr(record, "feature_transformation_ms", 0.0)), 2
        ),
        model_inference_ms=round(float(getattr(record, "model_inference_ms", 0.0)), 2),
        postprocessing_serialization_ms=round(
            float(getattr(record, "postprocessing_serialization_ms", 0.0)), 2
        ),
    )


def _recorded_trace(
    service: ModelServingService, payload: dict[str, Any], request_id: str
) -> TraceSample:
    capture = _TraceCapture()
    serving_logger = logging.getLogger("src.api.endpoints.model_serving")
    original_level = serving_logger.level
    serving_logger.setLevel(logging.INFO)
    serving_logger.addHandler(capture)
    try:
        asyncio.run(_serve_model(service, "30", payload, request_id=request_id))
    finally:
        serving_logger.removeHandler(capture)
        serving_logger.setLevel(original_level)
    trace_record = next(
        (
            record
            for record in reversed(capture.records)
            if getattr(record, "event", "") == MODEL_30_TRACE_EVENT
        ),
        None,
    )
    if trace_record is None:
        messages = ", ".join(record.getMessage() for record in capture.records[-5:])
        raise RuntimeError(f"Model 30 inference did not emit a latency trace: {messages}")
    return _extract_trace_sample(trace_record)


def _one_cold_sample(payload: dict[str, Any]) -> TraceSample:
    reset_model_30_cache()
    service = ModelServingService()
    return _recorded_trace(service, payload, request_id="model-30-cold")


def _warm_samples(
    payload: dict[str, Any], iterations: int
) -> tuple[list[TraceSample], dict[str, Any]]:
    reset_model_30_cache()
    service = ModelServingService()
    rss_before_warmup = _current_rss_bytes()
    _recorded_trace(service, payload, request_id="model-30-warmup")
    rss_after_warmup = _current_rss_bytes()

    process_start = time.process_time()
    wall_start = time.perf_counter()
    samples = [
        _recorded_trace(service, payload, request_id=f"model-30-warm-{iteration}")
        for iteration in range(iterations)
    ]
    wall_elapsed = max(time.perf_counter() - wall_start, 0.001)
    cpu_elapsed = max(time.process_time() - process_start, 0.0)
    rss_after_loop = _current_rss_bytes()
    return samples, {
        "rss_before_warmup_bytes": rss_before_warmup,
        "rss_after_warmup_bytes": rss_after_warmup,
        "rss_after_loop_bytes": rss_after_loop,
        "ru_maxrss_bytes": _ru_maxrss_bytes(),
        "process_cpu_pct": round((cpu_elapsed / wall_elapsed) * 100, 2),
        "os_cpu_count": os.cpu_count(),
        "cpu_affinity_count": len(os.sched_getaffinity(0))
        if hasattr(os, "sched_getaffinity")
        else None,
    }


@contextmanager
def record_outbound_connects() -> Iterator[Counter[str]]:
    """Count outbound socket connects during the wrapped block."""
    counter: Counter[str] = Counter()
    original_connect = socket.socket.connect

    def _connect(sock: socket.socket, address: Any) -> Any:
        if isinstance(address, tuple) and len(address) >= 2:
            counter[f"{address[0]}:{address[1]}"] += 1
        else:
            counter[str(address)] += 1
        return original_connect(sock, address)

    socket.socket.connect = _connect  # type: ignore[assignment]
    try:
        yield counter
    finally:
        socket.socket.connect = original_connect  # type: ignore[assignment]


def profile_warm_path(
    payload: dict[str, Any],
    iterations: int,
    top_n: int,
) -> list[dict[str, Any]]:
    """Run cProfile on the warm direct predict path."""
    reset_model_30_cache()
    validated = validate_nested_model_30_inputs(payload)
    features = model_30_inputs_to_features(validated)
    call_mlflow_model_30(os.environ["MODEL_30_MLFLOW_URI"], features, {})

    profiler = cProfile.Profile()
    profiler.enable()
    for _iteration in range(iterations):
        raw = call_mlflow_model_30(os.environ["MODEL_30_MLFLOW_URI"], features, {})
        normalize_model_30_output(raw, validated)
    profiler.disable()

    stats = pstats.Stats(profiler, stream=io.StringIO()).sort_stats("cumulative")
    # sort_stats populates fcn_list with the sorted order; stats.stats is an
    # unordered dict, so we iterate fcn_list to get the true top N by cumulative time.
    top_rows: list[dict[str, Any]] = []
    sorted_funcs = stats.fcn_list or list(stats.stats.keys())
    for func in sorted_funcs[:top_n]:
        cc, nc, tt, ct, callers = stats.stats[func]
        top_rows.append(
            {
                "function": pstats.func_std_string(func),
                "primitive_calls": cc,
                "total_calls": nc,
                "total_time_s": round(tt, 4),
                "cumulative_time_s": round(ct, 4),
                "callers": len(callers),
            }
        )
    return top_rows


@contextmanager
def override_model_30_uri(model_uri: str) -> Iterator[None]:
    """Temporarily override the registered Model 30 URI."""
    original = MODEL_CONFIGS["30"]
    MODEL_CONFIGS["30"] = replace(original, model_uri=model_uri)
    try:
        yield
    finally:
        MODEL_CONFIGS["30"] = original


def benchmark(
    *,
    payload: dict[str, Any],
    warm_iterations: int,
    cold_iterations: int,
    profile_top: int,
) -> dict[str, Any]:
    """Collect cold/warm timing, RSS, network, and profile data."""
    cold_samples = [_one_cold_sample(payload) for _ in range(cold_iterations)]
    warm_samples, env_stats = _warm_samples(payload, warm_iterations)
    with record_outbound_connects() as outbound:
        _warm_samples(payload, min(10, warm_iterations))
    top_profile = profile_warm_path(payload, min(50, warm_iterations), profile_top)
    return {
        "cold": {
            "samples": [sample.as_dict() for sample in cold_samples],
            "stats": aggregate_trace_samples(cold_samples),
        },
        "warm": {
            "samples": [sample.as_dict() for sample in warm_samples],
            "stats": aggregate_trace_samples(warm_samples),
        },
        "environment": env_stats,
        "network_audit": {
            "warm_iterations": min(10, warm_iterations),
            "outbound_connects": dict(outbound),
            "outbound_connect_count": sum(outbound.values()),
        },
        "profile_top": top_profile,
    }


def _print_human(result: dict[str, Any]) -> None:
    """Print a human-readable CLI summary."""
    print("Cold stats:")  # noqa: T201
    print(json.dumps(result["cold"]["stats"], indent=2, sort_keys=True))  # noqa: T201
    print("\nWarm stats:")  # noqa: T201
    print(json.dumps(result["warm"]["stats"], indent=2, sort_keys=True))  # noqa: T201
    print("\nEnvironment:")  # noqa: T201
    print(json.dumps(result["environment"], indent=2, sort_keys=True))  # noqa: T201
    print("\nNetwork audit:")  # noqa: T201
    print(json.dumps(result["network_audit"], indent=2, sort_keys=True))  # noqa: T201
    print("\nTop profile rows:")  # noqa: T201
    for row in result["profile_top"]:
        print(  # noqa: T201
            f"{row['cumulative_time_s']:>7.4f}s  {row['total_calls']:>6}  " f"{row['function']}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the profiling helper."""
    args = parse_args(argv)
    os.environ["MODEL_30_MLFLOW_URI"] = args.model_uri
    os.environ.setdefault("MLFLOW_TRACKING_URI", args.mlflow_uri)
    payload = _load_payload(args.payload)
    with override_model_30_uri(args.model_uri):
        result = benchmark(
            payload=payload,
            warm_iterations=args.warm_iterations,
            cold_iterations=args.cold_iterations,
            profile_top=args.profile_top,
        )
    if args.output_json:
        print(json.dumps(result, indent=2, sort_keys=True))  # noqa: T201
    else:
        _print_human(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
