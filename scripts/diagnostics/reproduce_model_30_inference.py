"""Run model 30 inference locally with production-like artifacts.

This script bypasses the API server and exercises the same model-loading path
used by the service adapter. MLflow authentication still comes from the shared
environment configuration, including variables such as MLFLOW_TRACKING_TOKEN.
When the PR 195 timing hooks are present, it reads their per-phase timings
directly. On branches where those hooks are absent, it falls back to direct
wall-clock timing so the reproduction workflow still works.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import platform
import resource
import statistics
import sys
import time
import traceback
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import mlflow

from src.api.endpoints.model_30_adapter import (
    call_mlflow_model_30,
    is_model_30_cached,
    model_30_inputs_to_features,
    reset_model_30_cache,
    validate_nested_model_30_inputs,
)

try:
    from src.api.endpoints.latency_trace import Model30LatencyTrace
except ImportError:  # pragma: no cover - exercised on branches without PR 195
    Model30LatencyTrace = None

DEFAULT_CURATED_PAYLOAD = (
    Path(__file__).resolve().parents[2] / "data/test_fixtures/model_30_curated_payload.json"
)
DEFAULT_MINIMAL_PAYLOAD = (
    Path(__file__).resolve().parents[2] / "data/test_fixtures/model_30_minimal_payload.json"
)
MAX_PREVIEW_CHARS = 4096


class _FallbackLatencyTrace:
    """Minimal phase timer used when the PR 195 trace helper is unavailable."""

    def __init__(self: _FallbackLatencyTrace) -> None:
        self.timings: dict[str, float] = {}

    @contextmanager
    def phase(self: _FallbackLatencyTrace, name: str) -> Any:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.timings[f"{name}_ms"] = (time.perf_counter() - started) * 1000


TraceClass = Model30LatencyTrace or _FallbackLatencyTrace


class PayloadValidationError(Exception):
    """Raised when a fixture payload does not satisfy the serving contract."""


def _warm_iterations(value: str) -> int:
    parsed = int(value)
    if parsed < 3:
        msg = "--warm-iterations must be at least 3"
        raise argparse.ArgumentTypeError(msg)
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the local reproduction harness."""
    parser = argparse.ArgumentParser(
        description="Reproduce model 30 inference locally against the MLflow artifact.",
    )
    parser.add_argument(
        "--model-uri",
        default=os.getenv("MODEL_30_MLFLOW_URI"),
        help="MLflow model URI. Defaults to MODEL_30_MLFLOW_URI when set.",
    )
    parser.add_argument(
        "--curated-payload",
        type=Path,
        default=DEFAULT_CURATED_PAYLOAD,
        help="Path to the curated nested payload fixture.",
    )
    parser.add_argument(
        "--minimal-payload",
        type=Path,
        default=DEFAULT_MINIMAL_PAYLOAD,
        help="Path to the minimal nested payload fixture.",
    )
    parser.add_argument(
        "--warm-iterations",
        type=_warm_iterations,
        default=5,
        help="Number of warm inference iterations to measure. Minimum 3.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the JSON report.",
    )
    parser.add_argument(
        "--cold-threshold-seconds",
        type=float,
        default=5.0,
        help="Cold-load threshold used by the verdict logic.",
    )
    parser.add_argument(
        "--warm-threshold-seconds",
        type=float,
        default=1.0,
        help="Warm-inference threshold used by the verdict logic.",
    )
    args = parser.parse_args(argv)
    if not args.model_uri:
        parser.error("--model-uri is required unless MODEL_30_MLFLOW_URI is set")
    return args


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _validate_payload(raw_payload: dict[str, Any], *, label: str) -> Any:
    try:
        return validate_nested_model_30_inputs(raw_payload)
    except Exception as exc:  # noqa: BLE001 - preserve validation failure details
        msg = f"{label} payload validation failed: {exc}"
        raise PayloadValidationError(msg) from exc


def _load_payload_features(
    path: Path,
    *,
    label: str,
    trace: _FallbackLatencyTrace | Any,
) -> tuple[Any, Any]:
    raw_payload = _load_json(path)
    validated = _validate_payload(raw_payload, label=label)
    with trace.phase(f"{label}_feature_transform"):
        features = model_30_inputs_to_features(validated)
    return validated, features


def _try_import_psutil() -> Any | None:
    try:
        import psutil
    except ImportError:
        return None
    return psutil


def _rss_mb() -> float:
    psutil = _try_import_psutil()
    if psutil is not None:
        return round(psutil.Process().memory_info().rss / (1024**2), 3)

    # ru_maxrss is the process lifetime *peak* RSS, not current — deltas between
    # samples may be zero even after allocation. Install psutil for current RSS.
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        bytes_per_unit = 1
    else:
        bytes_per_unit = 1024
    return round((rss * bytes_per_unit) / (1024**2), 3)


def _truncate_preview(value: Any) -> str:
    preview = repr(value)
    if len(preview) <= MAX_PREVIEW_CHARS:
        return preview
    return f"{preview[: MAX_PREVIEW_CHARS - 3]}..."


def _serialize_error(exc: BaseException) -> dict[str, str]:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": "".join(traceback.format_exception(exc)),
    }


def _invoke_model(model_uri: str, features: Any) -> tuple[Any, dict[str, float], str]:
    supports_internal_timings = "_timings" in inspect.signature(call_mlflow_model_30).parameters
    if supports_internal_timings:
        timings: dict[str, float] = {}
        started = time.perf_counter()
        result = call_mlflow_model_30(model_uri, features, _timings=timings)
        elapsed_ms = (time.perf_counter() - started) * 1000
        timings.setdefault("total_call_ms", elapsed_ms)
        return result, timings, "adapter_timings"

    cache_hit_before = is_model_30_cached(model_uri)
    started = time.perf_counter()
    result = call_mlflow_model_30(model_uri, features)
    elapsed_ms = (time.perf_counter() - started) * 1000
    timings = {"total_call_ms": elapsed_ms}
    if cache_hit_before:
        timings["inference_only_ms"] = elapsed_ms
    else:
        timings["artifact_load_ms"] = elapsed_ms
    return result, timings, "wall_clock_fallback"


def _seconds_from_ms(timings: Mapping[str, float], key: str) -> float | None:
    value = timings.get(key)
    if value is None:
        return None
    return round(value / 1000, 6)


def _run_payload(
    *,
    label: str,
    model_uri: str,
    features: Any,
    warm_iterations: int,
    trace: _FallbackLatencyTrace | Any,
) -> tuple[dict[str, Any], str]:
    payload_report: dict[str, Any] = {
        "result_preview": None,
        "error": None,
        "warmup_error": None,
        "timed_iteration_errors": [],
    }
    timing_source = "unknown"

    with trace.phase(f"{label}_warmup"):
        try:
            warmup_result, _, timing_source = _invoke_model(model_uri, features)
            payload_report["result_preview"] = _truncate_preview(warmup_result)
        except Exception as exc:  # noqa: BLE001 - report runtime failures verbatim
            payload_report["warmup_error"] = _serialize_error(exc)

    samples: list[float] = []
    for _ in range(warm_iterations):
        try:
            result, timings, timing_source = _invoke_model(model_uri, features)
            inference_seconds = _seconds_from_ms(timings, "inference_only_ms")
            if inference_seconds is None:
                inference_seconds = _seconds_from_ms(timings, "total_call_ms")
            if inference_seconds is None:
                msg = "Inference timing data was not captured"
                raise RuntimeError(msg)
            samples.append(inference_seconds)
            payload_report["result_preview"] = _truncate_preview(result)
            payload_report["error"] = None  # clear error from any prior failed iteration
        except Exception as exc:  # noqa: BLE001 - report all failures in output JSON
            err = _serialize_error(exc)
            payload_report["error"] = err
            payload_report["timed_iteration_errors"].append(err)

    if samples:
        payload_report["warm_seconds"] = {
            "min": min(samples),
            "median": statistics.median(samples),
            "max": max(samples),
            "samples": samples,
        }
    else:
        payload_report["warm_seconds"] = {
            "min": None,
            "median": None,
            "max": None,
            "samples": [],
        }

    return payload_report, timing_source


def _build_verdict(
    *,
    cold_load_seconds: float,
    payloads: Mapping[str, Mapping[str, Any]],
    cold_threshold_seconds: float,
    warm_threshold_seconds: float,
) -> tuple[str, str]:
    warm_medians = {label: payload["warm_seconds"]["median"] for label, payload in payloads.items()}
    if cold_load_seconds >= cold_threshold_seconds:
        reason = (
            f"Cold artifact load was {cold_load_seconds:.3f}s, exceeding the "
            f"{cold_threshold_seconds:.3f}s threshold."
        )
        return "model_runtime", reason

    slow_payloads = [
        label
        for label, median in warm_medians.items()
        if median is not None and median >= warm_threshold_seconds
    ]
    if slow_payloads:
        joined = ", ".join(sorted(slow_payloads))
        reason = f"Warm inference median exceeded {warm_threshold_seconds:.3f}s for: {joined}."
        return "model_runtime", reason

    half_cold_threshold = cold_threshold_seconds / 2
    half_warm_threshold = warm_threshold_seconds / 2
    both_payloads_fast = all(
        payload["warm_seconds"]["median"] is not None
        and payload["warm_seconds"]["median"] < half_warm_threshold
        for payload in payloads.values()
    )
    both_payloads_succeeded = all(payload["error"] is None for payload in payloads.values())
    if cold_load_seconds < half_cold_threshold and both_payloads_fast and both_payloads_succeeded:
        reason = (
            "Local cold load and warm inference both stayed well below the thresholds, "
            "so the deployed API path or cache behavior is the more likely source."
        )
        return "api_or_cache", reason

    reason = (
        "Local measurements did not isolate a clear bottleneck. Review payload-specific "
        "errors and timing samples."
    )
    return "inconclusive", reason


def generate_report(args: argparse.Namespace) -> dict[str, Any]:
    """Run the reproduction flow and return the structured diagnostic report."""
    trace = TraceClass()
    _, curated_features = _load_payload_features(
        args.curated_payload,
        label="curated",
        trace=trace,
    )
    _, minimal_features = _load_payload_features(
        args.minimal_payload,
        label="minimal",
        trace=trace,
    )

    rss_before_load_mb = _rss_mb()
    reset_model_30_cache()
    cold_result, cold_timings, timing_source = _invoke_model(args.model_uri, curated_features)
    cold_load_seconds = _seconds_from_ms(cold_timings, "artifact_load_ms")
    if cold_load_seconds is None:
        cold_load_seconds = _seconds_from_ms(cold_timings, "total_call_ms")
    if cold_load_seconds is None:
        msg = "Cold-load timing data was not captured"
        raise RuntimeError(msg)

    rss_after_load_mb = _rss_mb()
    curated_report, curated_timing_source = _run_payload(
        label="curated",
        model_uri=args.model_uri,
        features=curated_features,
        warm_iterations=args.warm_iterations,
        trace=trace,
    )
    minimal_report, minimal_timing_source = _run_payload(
        label="minimal",
        model_uri=args.model_uri,
        features=minimal_features,
        warm_iterations=args.warm_iterations,
        trace=trace,
    )
    rss_after_inference_mb = _rss_mb()

    payloads = {
        "curated": curated_report,
        "minimal": minimal_report,
    }
    verdict, verdict_reason = _build_verdict(
        cold_load_seconds=cold_load_seconds,
        payloads=payloads,
        cold_threshold_seconds=args.cold_threshold_seconds,
        warm_threshold_seconds=args.warm_threshold_seconds,
    )

    return {
        "model_uri": args.model_uri,
        "mlflow_tracking_uri": mlflow.get_tracking_uri(),
        "python_version": platform.python_version(),
        "mlflow_version": mlflow.__version__,
        "timing_source": {
            "cold": timing_source,
            "curated": curated_timing_source,
            "minimal": minimal_timing_source,
        },
        "trace_timings_ms": getattr(trace, "timings", {}),
        "cold_cache_preloaded": False,
        "cold_load_seconds": cold_load_seconds,
        "cold_result_preview": _truncate_preview(cold_result),
        "rss_before_load_mb": rss_before_load_mb,
        "rss_after_load_mb": rss_after_load_mb,
        "rss_after_inference_mb": rss_after_inference_mb,
        "payloads": payloads,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the CLI and emit the JSON report to stdout and optionally a file."""
    args = parse_args(argv)
    try:
        report = generate_report(args)
    except PayloadValidationError as exc:
        print(exc, file=sys.stderr)  # noqa: T201
        return 1
    except FileNotFoundError as exc:
        print(f"Fixture file not found: {exc}", file=sys.stderr)  # noqa: T201
        return 1
    except json.JSONDecodeError as exc:
        print(f"Payload file is not valid JSON: {exc}", file=sys.stderr)  # noqa: T201
        return 1

    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)  # noqa: T201
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
