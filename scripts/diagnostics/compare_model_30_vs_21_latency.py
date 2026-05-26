#!/usr/bin/env python3
"""Compare model 30 latency against known-good model 21 through the shared route.

MLflow access relies on the shared environment configuration, including
`MLFLOW_TRACKING_TOKEN` and related transport settings already used by the app.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mlflow
from huggingface_hub import hf_hub_download, snapshot_download

from src.api.endpoints.model_30_adapter import get_model_30_uri, reset_model_30_cache
from src.api.endpoints.model_serving import MODEL_CONFIGS, ModelServingService

LOGGER = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs"
DEFAULT_MODEL_21_PAYLOAD = REPO_ROOT / "data/test_fixtures/model_21_payload.json"
DEFAULT_MODEL_30_PAYLOAD = REPO_ROOT / "data/test_fixtures/model_30_curated_payload.json"
RAW_TRACE_FILENAME = "raw_traces.jsonl"
REPORT_FILENAME = "model_30_vs_21_latency_report.md"
MODEL_30_TRACE_EVENT = "model_30_latency_trace"
MODEL_30_PHASES = (
    "request_validation",
    "model_cache_lookup",
    "artifact_load",
    "preprocessor_setup",
    "feature_transformation",
    "model_inference",
    "postprocessing_serialization",
)
MODEL_21_PHASES = ("artifact_load", "model_inference", "total")


@dataclass(slots=True)
class MeasurementBundle:
    """Collected samples plus per-iteration failures for one benchmark slice."""

    samples: list[dict[str, Any]]
    errors: list[dict[str, Any]]


class BenchmarkError(RuntimeError):
    """Raised for benchmark setup or execution failures."""


class _TraceCapture(logging.Handler):
    """Intercept model 30 latency trace records emitted by the serving path."""

    def __init__(self: _TraceCapture) -> None:
        super().__init__(level=logging.INFO)
        self.records: list[logging.LogRecord] = []

    def emit(self: _TraceCapture, record: logging.LogRecord) -> None:
        self.records.append(record)


def _iteration_count(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        msg = "iteration counts must be >= 1"
        raise argparse.ArgumentTypeError(msg)
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse and validate CLI arguments."""
    parser = argparse.ArgumentParser(
        description=("Benchmark model 21 and model 30 through the shared serve_prediction route.")
    )
    parser.add_argument("--model", choices=("21", "30", "both"), default="both")
    parser.add_argument("--mode", choices=("warm", "cold", "both"), default="both")
    parser.add_argument("--warm-iterations", type=_iteration_count, default=20)
    parser.add_argument("--cold-iterations", type=_iteration_count, default=3)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--mlflow-uri",
        default=os.getenv("MLFLOW_SERVER_URL"),
        help="MLflow tracking URI. Defaults to MLFLOW_SERVER_URL.",
    )
    parser.add_argument("--model-21-payload", type=Path, default=DEFAULT_MODEL_21_PAYLOAD)
    parser.add_argument("--model-30-payload", type=Path, default=DEFAULT_MODEL_30_PAYLOAD)
    parser.add_argument(
        "--_cold-one-shot",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    if not args.mlflow_uri:
        parser.exit(1, "MLflow URI is required via --mlflow-uri or MLFLOW_SERVER_URL\n")
    if args.warm_iterations < 1:
        parser.error("--warm-iterations must be >= 1")
    if args.cold_iterations < 1:
        parser.error("--cold-iterations must be >= 1")
    try:
        _ensure_output_dir_writable(args.output_dir)
    except BenchmarkError as exc:
        parser.exit(1, f"{exc}\n")
    return args


def _ensure_output_dir_writable(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        msg = f"Output directory is not writable: {path} ({exc})"
        raise BenchmarkError(msg) from exc

    probe = path / ".write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        msg = f"Output directory is not writable: {path} ({exc})"
        raise BenchmarkError(msg) from exc


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _quantize_ms(value: float) -> float:
    return round(float(value), 2)


def _serialize_error(exc: BaseException) -> dict[str, str]:
    return {"type": type(exc).__name__, "message": str(exc)}


def aggregate_stats(samples: list[float]) -> dict[str, float]:
    """Summarize latency samples using percentile and central-tendency metrics."""
    if not samples:
        return {"p50": 0.0, "p95": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0, "n": 0}

    ordered = sorted(samples)
    nearest_rank_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "p50": _quantize_ms(statistics.median(ordered)),
        "p95": _quantize_ms(ordered[nearest_rank_index]),
        "mean": _quantize_ms(statistics.mean(ordered)),
        "min": _quantize_ms(ordered[0]),
        "max": _quantize_ms(ordered[-1]),
        "n": len(ordered),
    }


def aggregate_phase_stats(samples: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Aggregate successful per-phase measurements and ignore error samples."""
    phase_samples: dict[str, list[float]] = {}
    for sample in samples:
        if sample.get("error"):
            continue
        for key, value in sample.items():
            if not key.endswith("_ms") or key == "error":
                continue
            phase = key.removesuffix("_ms")
            phase_samples.setdefault(phase, []).append(float(value))
    return {phase: aggregate_stats(values) for phase, values in phase_samples.items()}


def analyze_divergence(
    m21_warm: dict[str, dict[str, float]],
    m30_warm: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    """Identify the warm-path phases where model 30 materially diverges."""
    findings: list[dict[str, Any]] = []
    for phase, m30_stats in m30_warm.items():
        m21_stats = m21_warm.get(phase)
        if not m21_stats:
            continue
        m21_p50 = float(m21_stats.get("p50", 0.0))
        m30_p50 = float(m30_stats.get("p50", 0.0))
        if m21_p50 <= 0:
            continue
        delta = _quantize_ms(m30_p50 - m21_p50)
        ratio = round(m30_p50 / m21_p50, 2)
        if m30_p50 >= 2 * m21_p50 or delta >= 100.0:
            findings.append(
                {
                    "phase": phase,
                    "model_21_p50_ms": _quantize_ms(m21_p50),
                    "model_30_p50_ms": _quantize_ms(m30_p50),
                    "delta_ms": delta,
                    "ratio": ratio,
                }
            )

    if findings:
        return sorted(findings, key=lambda item: abs(float(item["delta_ms"])), reverse=True)

    total_21 = float(m21_warm.get("total", {}).get("p50", 0.0))
    total_30 = float(m30_warm.get("total", {}).get("p50", 0.0))
    ratio = round(total_30 / total_21, 2) if total_21 > 0 else None
    return [
        {
            "phase": "no_divergence",
            "model_21_p50_ms": _quantize_ms(total_21),
            "model_30_p50_ms": _quantize_ms(total_30),
            "delta_ms": _quantize_ms(total_30 - total_21),
            "ratio": ratio,
        }
    ]


async def _serve_model(
    service: ModelServingService,
    model_id: str,
    payload: dict[str, Any],
    *,
    request_id: str,
) -> dict[str, Any]:
    options = {"inference_method": "mlflow_pyfunc" if model_id == "30" else "local"}
    return await service.serve_prediction(model_id, payload, options, request_id=request_id)


def _extract_model_30_sample(record: logging.LogRecord) -> dict[str, float]:
    sample: dict[str, float] = {"total_ms": _quantize_ms(getattr(record, "total_ms", 0.0))}
    for phase in MODEL_30_PHASES:
        sample[f"{phase}_ms"] = _quantize_ms(getattr(record, f"{phase}_ms", 0.0))
    return sample


def _measure_model_30_warm(
    payload: dict[str, Any],
    *,
    n: int,
    model_uri: str,
) -> MeasurementBundle:
    del model_uri
    reset_model_30_cache()
    service = ModelServingService()
    errors: list[dict[str, Any]] = []

    asyncio.run(_serve_model(service, "30", payload, request_id="model-30-warmup"))

    samples: list[dict[str, Any]] = []
    for iteration in range(n):
        capture = _TraceCapture()
        root_logger = logging.getLogger()
        root_logger.addHandler(capture)
        try:
            asyncio.run(
                _serve_model(
                    service,
                    "30",
                    payload,
                    request_id=f"model-30-warm-{iteration}",
                )
            )
            trace_record = next(
                (
                    record
                    for record in reversed(capture.records)
                    if getattr(record, "event", "") == MODEL_30_TRACE_EVENT
                ),
                None,
            )
            if trace_record is None:
                raise BenchmarkError("Model 30 warm sample did not emit a latency trace")
            samples.append(_extract_model_30_sample(trace_record))
        except Exception as exc:  # noqa: BLE001 - preserve benchmark loop
            error = {"iteration": iteration, **_serialize_error(exc)}
            errors.append(error)
            samples.append({"error": error})
        finally:
            root_logger.removeHandler(capture)
    return MeasurementBundle(samples=samples, errors=errors)


def _measure_model_21_warm(payload: dict[str, Any], *, n: int) -> MeasurementBundle:
    service = ModelServingService()
    errors: list[dict[str, Any]] = []

    asyncio.run(_serve_model(service, "21", payload, request_id="model-21-warmup"))

    samples: list[dict[str, Any]] = []
    for iteration in range(n):
        started = time.perf_counter()
        try:
            asyncio.run(
                _serve_model(
                    service,
                    "21",
                    payload,
                    request_id=f"model-21-warm-{iteration}",
                )
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            elapsed_rounded = _quantize_ms(elapsed_ms)
            samples.append(
                {
                    "model_inference_ms": elapsed_rounded,
                    "total_ms": elapsed_rounded,
                }
            )
        except Exception as exc:  # noqa: BLE001 - preserve benchmark loop
            error = {"iteration": iteration, **_serialize_error(exc)}
            errors.append(error)
            samples.append({"error": error})
    return MeasurementBundle(samples=samples, errors=errors)


def _measure_cold_via_subprocess(
    model_id: str,
    *,
    n: int,
    args: argparse.Namespace,
) -> MeasurementBundle:
    errors: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    for iteration in range(n):
        command = [
            sys.executable,
            "-m",
            "scripts.diagnostics.compare_model_30_vs_21_latency",
            "--model",
            model_id,
            "--mode",
            "cold",
            "--warm-iterations",
            str(args.warm_iterations),
            "--cold-iterations",
            "1",
            "--output-dir",
            str(args.output_dir),
            "--mlflow-uri",
            args.mlflow_uri,
            "--model-21-payload",
            str(args.model_21_payload),
            "--model-30-payload",
            str(args.model_30_payload),
            "--_cold-one-shot",
        ]
        completed = subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(REPO_ROOT),
        )
        if completed.returncode != 0:
            error = {
                "iteration": iteration,
                "type": "SubprocessError",
                "message": completed.stderr.strip() or completed.stdout.strip(),
            }
            errors.append(error)
            samples.append({"error": error})
            continue
        try:
            samples.append(json.loads(completed.stdout))
        except json.JSONDecodeError as exc:
            error = {"iteration": iteration, "type": "JSONDecodeError", "message": str(exc)}
            errors.append(error)
            samples.append({"error": error})
    return MeasurementBundle(samples=samples, errors=errors)


def inspect_mlflow_artifact(model_uri: str) -> dict[str, Any]:
    """Download and summarize the MLflow artifact directory when accessible."""
    try:
        local_path = Path(mlflow.artifacts.download_artifacts(artifact_uri=model_uri))
    except Exception as exc:  # noqa: BLE001 - best effort metadata only
        return {
            "size_bytes": None,
            "file_count": 0,
            "top_files": [],
            "dependencies": [],
            "runtime": [],
            "error": str(exc),
        }
    return _summarize_artifact_directory(local_path)


def inspect_hf_artifact(repository_id: str, token: str | None) -> dict[str, Any]:
    """Download and summarize the HuggingFace artifact directory when accessible."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(
                hf_hub_download(
                    repo_id=repository_id,
                    filename="model.pkl",
                    token=token,
                    cache_dir=tmpdir,
                )
            )
            artifact_dir = model_path.parent
            try:
                snapshot_download(
                    repo_id=repository_id,
                    token=token,
                    cache_dir=tmpdir,
                    allow_patterns=["requirements.txt", "conda.yaml", "runtime.txt"],
                    local_dir=str(artifact_dir),
                )
            except Exception as exc:  # noqa: BLE001 - auxiliary metadata only
                LOGGER.debug("Unable to fetch optional HF metadata files: %s", exc)
            return _summarize_artifact_directory(artifact_dir, preferred_file=model_path.name)
    except Exception as exc:  # noqa: BLE001 - best effort metadata only
        return {
            "size_bytes": None,
            "file_count": 0,
            "top_files": [],
            "dependencies": [],
            "runtime": [],
            "error": str(exc),
        }


def _summarize_artifact_directory(
    directory: Path,
    *,
    preferred_file: str | None = None,
) -> dict[str, Any]:
    files = [path for path in directory.rglob("*") if path.is_file()]
    file_entries = []
    size_bytes = 0
    for path in files:
        stat = path.stat()
        size_bytes += stat.st_size
        file_entries.append(
            {
                "path": str(path.relative_to(directory)),
                "size_bytes": stat.st_size,
            }
        )
    file_entries.sort(
        key=lambda item: (
            item["path"] != preferred_file,
            -int(item["size_bytes"]),
            item["path"],
        )
    )
    dependencies = _read_dependency_files(directory)
    return {
        "size_bytes": size_bytes,
        "file_count": len(files),
        "top_files": [
            f"{entry['path']} ({entry['size_bytes']} bytes)" for entry in file_entries[:5]
        ],
        "dependencies": dependencies["dependencies"],
        "runtime": dependencies["runtime"],
    }


def _read_dependency_files(directory: Path) -> dict[str, list[str]]:
    dependencies: list[str] = []
    runtime: list[str] = []
    requirements_path = directory / "requirements.txt"
    conda_path = directory / "conda.yaml"
    runtime_path = directory / "runtime.txt"
    mlmodel_path = directory / "MLmodel"

    for path in (requirements_path, runtime_path):
        if path.exists():
            values = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            if path.name == "runtime.txt":
                runtime.extend(values)
            else:
                dependencies.extend(values)

    if conda_path.exists():
        for line in conda_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("- ") and stripped != "- pip:":
                dependencies.append(stripped[2:])

    if mlmodel_path.exists():
        for line in mlmodel_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("python_env:"):
                runtime.append(stripped.split(":", 1)[1].strip())

    return {
        "dependencies": sorted(dict.fromkeys(dependencies)),
        "runtime": sorted(dict.fromkeys(runtime)),
    }


def describe_preprocessing() -> dict[str, dict[str, Any]]:
    """Return the static preprocessing shape for model 21 and model 30."""
    return {
        "21": {
            "feature_count": 10,
            "features": [
                "company_size",
                "engagement_score",
                "website_visits",
                "email_opens",
                "content_downloads",
                "demo_requested",
                "budget_confirmed",
                "industry_score",
                "timeline_score",
                "title_score",
            ],
            "summary": (
                "Simple numeric/boolean extraction plus two small lookup tables "
                "and one title heuristic."
            ),
        },
        "30": {
            "feature_count": 32,
            "features": [
                "schema_version",
                "task_descriptor",
                "task_description",
                "task_type",
                "language",
                "framework",
                "repo_type",
                "allowed_models",
                "preferred_models",
                "max_cost_usd",
                "max_latency_seconds",
                "prioritize_quality",
                "prioritize_speed",
                "domain",
                "repo_size_bucket",
                "requires_tests",
                "risk_level",
                "file_count",
                "estimated_complexity",
                "security_sensitive",
                "surface",
                "workflow_stages",
                "execution_environment",
                "human_review_required",
                "expected_duration_seconds",
                "expected_cost_usd",
                "expected_success_probability",
                "external_task_id",
                "run_id",
                "integration_version",
                "idempotency_key",
                "request_metadata",
            ],
            "summary": (
                "Nested request validation, JSON serialization, and one-row "
                "DataFrame assembly across routing, context, workflow, "
                "prediction, and metadata fields."
            ),
        },
    }


def _format_ratio(numerator: float | None, denominator: float | None) -> str:
    if numerator is None or denominator is None or denominator <= 0:
        return "n/a"
    return f"{numerator / denominator:.2f}x"


def _format_ms(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value / (1024 * 1024):.2f} MiB"


def render_report(
    m21_data: dict[str, Any],
    m30_data: dict[str, Any],
    divergences: list[dict[str, Any]],
    *,
    run_date: str,
    mlflow_uri: str,
) -> str:
    """Render the markdown comparison report consumed by the task artifact."""
    warm_rows = []
    all_phases = sorted(set(m21_data["warm"]["stats"]) | set(m30_data["warm"]["stats"]))
    for phase in all_phases:
        m21_stats = m21_data["warm"]["stats"].get(phase, {})
        m30_stats = m30_data["warm"]["stats"].get(phase, {})
        warm_rows.append(
            "| "
            + " | ".join(
                [
                    phase,
                    _format_ms(m21_stats.get("p50")),
                    _format_ms(m21_stats.get("p95")),
                    _format_ms(m21_stats.get("mean")),
                    _format_ms(m30_stats.get("p50")),
                    _format_ms(m30_stats.get("p95")),
                    _format_ms(m30_stats.get("mean")),
                    _format_ratio(
                        m30_stats.get("p50"),
                        m21_stats.get("p50"),
                    ),
                ]
            )
            + " |"
        )

    cold_rows = []
    cold_phases = sorted(set(m21_data["cold"]["stats"]) | set(m30_data["cold"]["stats"]))
    for phase in cold_phases:
        m21_mean = m21_data["cold"]["stats"].get(phase, {}).get("mean")
        m30_mean = m30_data["cold"]["stats"].get(phase, {}).get("mean")
        cold_rows.append(
            f"| {phase} | {_format_ms(m21_mean)} | {_format_ms(m30_mean)} | "
            f"{_format_ratio(m30_mean, m21_mean)} |"
        )

    divergence_lines = []
    for finding in divergences:
        if finding["phase"] == "no_divergence":
            divergence_lines.append(
                "- No single phase crossed the divergence threshold; total warm p50 remained "
                f"{finding['model_30_p50_ms']:.2f} ms vs "
                f"{finding['model_21_p50_ms']:.2f} ms "
                f"({_format_ratio(finding['model_30_p50_ms'], finding['model_21_p50_ms'])})."
            )
        else:
            divergence_lines.append(
                f"- `{finding['phase']}` diverged: model 30 p50 "
                f"{finding['model_30_p50_ms']:.2f} ms vs model 21 "
                f"{finding['model_21_p50_ms']:.2f} ms "
                f"({finding['ratio']:.2f}x, +{finding['delta_ms']:.2f} ms)."
            )

    preprocessing = describe_preprocessing()
    return "\n".join(
        [
            "# Model 30 vs Model 21 Latency Comparison",
            "",
            f"Generated {run_date}. MLflow tracking URI: `{mlflow_uri}`.",
            "",
            "## Warm Latency Breakdown",
            "",
            (
                "| Phase | M21 p50 (ms) | M21 p95 (ms) | M21 mean (ms) | "
                "M30 p50 (ms) | M30 p95 (ms) | M30 mean (ms) | Ratio |"
            ),
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            *warm_rows,
            "",
            "## Cold-Start Breakdown",
            "",
            "| Phase | M21 mean (ms) | M30 mean (ms) | Ratio |",
            "| --- | ---: | ---: | ---: |",
            *cold_rows,
            "",
            "## Artifact Comparison",
            "",
            "| Model | Size | Files | Top files |",
            "| --- | ---: | ---: | --- |",
            (
                f"| 21 | {_format_bytes(m21_data['artifact'].get('size_bytes'))} | "
                f"{m21_data['artifact'].get('file_count', 0)} | "
                f"{'; '.join(m21_data['artifact'].get('top_files', [])) or 'n/a'} |"
            ),
            (
                f"| 30 | {_format_bytes(m30_data['artifact'].get('size_bytes'))} | "
                f"{m30_data['artifact'].get('file_count', 0)} | "
                f"{'; '.join(m30_data['artifact'].get('top_files', [])) or 'n/a'} |"
            ),
            "",
            "## Runtime And Dependencies",
            "",
            "| Model | Runtime | Dependencies |",
            "| --- | --- | --- |",
            (
                f"| 21 | {', '.join(m21_data['artifact'].get('runtime', [])) or 'n/a'} | "
                f"{', '.join(m21_data['artifact'].get('dependencies', [])) or 'n/a'} |"
            ),
            (
                f"| 30 | {', '.join(m30_data['artifact'].get('runtime', [])) or 'n/a'} | "
                f"{', '.join(m30_data['artifact'].get('dependencies', [])) or 'n/a'} |"
            ),
            "",
            "## Preprocessing Complexity",
            "",
            (
                f"- Model 21: {preprocessing['21']['feature_count']} derived features. "
                f"{preprocessing['21']['summary']}"
            ),
            (
                f"- Model 30: {preprocessing['30']['feature_count']} flattened features. "
                f"{preprocessing['30']['summary']}"
            ),
            f"- Model 21 features: {', '.join(preprocessing['21']['features'])}",
            f"- Model 30 features: {', '.join(preprocessing['30']['features'])}",
            "",
            "## Divergence Analysis",
            "",
            *divergence_lines,
            "",
            "## Reproduction",
            "",
            "```bash",
            "python -m scripts.diagnostics.compare_model_30_vs_21_latency \\",
            "  --model both --mode both --warm-iterations 20 --cold-iterations 3 \\",
            '  --mlflow-uri "$MLFLOW_SERVER_URL"',
            "```",
        ]
    )


def _model_scope(selected: str) -> tuple[str, ...]:
    if selected == "both":
        return ("21", "30")
    return (selected,)


def _mode_scope(selected: str) -> tuple[str, ...]:
    if selected == "both":
        return ("warm", "cold")
    return (selected,)


def _bundle_to_stats(bundle: MeasurementBundle) -> dict[str, Any]:
    return {
        "samples": bundle.samples,
        "errors": bundle.errors,
        "stats": aggregate_phase_stats(bundle.samples),
    }


def _load_payload_for_model(model_id: str, args: argparse.Namespace) -> dict[str, Any]:
    payload_path = args.model_21_payload if model_id == "21" else args.model_30_payload
    return _load_json(payload_path)


def _run_cold_one_shot(args: argparse.Namespace) -> int:
    """Execute one cold measurement and emit a single JSON sample to stdout."""
    model_id = "21" if args.model == "both" else args.model
    payload = _load_payload_for_model(model_id, args)
    if model_id == "30":
        reset_model_30_cache()
        capture = _TraceCapture()
        root_logger = logging.getLogger()
        root_logger.addHandler(capture)
        try:
            asyncio.run(
                _serve_model(
                    ModelServingService(),
                    "30",
                    payload,
                    request_id="model-30-cold-one-shot",
                )
            )
        finally:
            root_logger.removeHandler(capture)
        trace_record = next(
            (
                record
                for record in reversed(capture.records)
                if getattr(record, "event", "") == MODEL_30_TRACE_EVENT
            ),
            None,
        )
        if trace_record is None:
            raise BenchmarkError("Model 30 cold run did not emit a latency trace")
        sys.stdout.write(f"{json.dumps(_extract_model_30_sample(trace_record))}\n")
        return 0

    started = time.perf_counter()
    asyncio.run(
        _serve_model(
            ModelServingService(),
            "21",
            payload,
            request_id="model-21-cold-one-shot",
        )
    )
    elapsed_ms = _quantize_ms((time.perf_counter() - started) * 1000)
    sys.stdout.write(f"{json.dumps({'artifact_load_ms': elapsed_ms, 'total_ms': elapsed_ms})}\n")
    return 0


def _write_raw_jsonl(output_dir: Path, rows: Iterable[dict[str, Any]]) -> None:
    destination = output_dir / RAW_TRACE_FILENAME
    with destination.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")


def _build_empty_model_result(model_id: str) -> dict[str, Any]:
    del model_id
    return {
        "warm": {"samples": [], "errors": [], "stats": {}},
        "cold": {"samples": [], "errors": [], "stats": {}},
        "artifact": {
            "size_bytes": None,
            "file_count": 0,
            "top_files": [],
            "dependencies": [],
            "runtime": [],
        },
    }


def _run_full_benchmark(args: argparse.Namespace) -> int:
    os.environ["MLFLOW_TRACKING_URI"] = args.mlflow_uri
    mlflow.set_tracking_uri(args.mlflow_uri)
    _ensure_output_dir_writable(args.output_dir)

    results = {"21": _build_empty_model_result("21"), "30": _build_empty_model_result("30")}
    raw_rows: list[dict[str, Any]] = []

    for model_id in _model_scope(args.model):
        payload = _load_payload_for_model(model_id, args)
        if "warm" in _mode_scope(args.mode):
            bundle = (
                _measure_model_21_warm(payload, n=args.warm_iterations)
                if model_id == "21"
                else _measure_model_30_warm(
                    payload,
                    n=args.warm_iterations,
                    model_uri=get_model_30_uri(),
                )
            )
            results[model_id]["warm"] = _bundle_to_stats(bundle)
            raw_rows.extend(
                {"model_id": model_id, "mode": "warm", **sample} for sample in bundle.samples
            )
        if "cold" in _mode_scope(args.mode):
            bundle = _measure_cold_via_subprocess(model_id, n=args.cold_iterations, args=args)
            results[model_id]["cold"] = _bundle_to_stats(bundle)
            raw_rows.extend(
                {"model_id": model_id, "mode": "cold", **sample} for sample in bundle.samples
            )

    service = ModelServingService()
    results["21"]["artifact"] = inspect_hf_artifact(
        MODEL_CONFIGS["21"]["repository_id"],
        service.hf_token,
    )
    results["30"]["artifact"] = inspect_mlflow_artifact(get_model_30_uri())

    divergences = analyze_divergence(
        results["21"]["warm"]["stats"],
        results["30"]["warm"]["stats"],
    )
    report = render_report(
        results["21"],
        results["30"],
        divergences,
        run_date=time.strftime("%Y-%m-%d"),
        mlflow_uri=args.mlflow_uri,
    )
    _write_raw_jsonl(args.output_dir, raw_rows)
    (args.output_dir / REPORT_FILENAME).write_text(report, encoding="utf-8")

    top_finding = divergences[0]
    if top_finding["phase"] == "no_divergence":
        sys.stdout.write(
            "No major divergence detected; "
            f"warm total p50 is {top_finding['model_30_p50_ms']:.2f} ms for model 30 "
            f"vs {top_finding['model_21_p50_ms']:.2f} ms for model 21.\n"
        )
    else:
        sys.stdout.write(
            f"Primary divergence: {top_finding['phase']} at "
            f"{top_finding['model_30_p50_ms']:.2f} ms for model 30 "
            f"vs {top_finding['model_21_p50_ms']:.2f} ms for model 21.\n"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the latency comparison CLI."""
    logging.basicConfig(level=logging.INFO)
    try:
        args = parse_args(argv)
        if args._cold_one_shot:
            return _run_cold_one_shot(args)
        return _run_full_benchmark(args)
    except BenchmarkError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    except FileNotFoundError as exc:
        sys.stderr.write(f"Required file not found: {exc}\n")
        return 1
    except Exception as exc:  # noqa: BLE001 - top-level CLI guard
        sys.stderr.write(f"Benchmark failed: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
