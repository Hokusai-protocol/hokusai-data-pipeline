#!/usr/bin/env python3
"""Run a Model 30 latency smoke check against a live API instance."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import yaml

REQUIRED_BUDGET_KEYS = (
    "cold_readiness_ms",
    "artifact_load_ms",
    "warm_p50_ms",
    "warm_p95_ms",
    "warm_p99_ms",
    "timeout_rate",
    "warm_memory_mb",
    "cold_memory_mb",
)
MODEL_30_ERROR_PREFIXES = (
    "Technical Task Router MLflow inference failed",
    "Technical Task Router inference timed out",
    "Technical Task Router cold load is already in progress",
)
SETUP_ERROR = 2
LATENCY_BREACH = 10
MODEL_30_ERROR_EXCESS = 11
INFRA_INCONCLUSIVE = 20


class BudgetValidationError(KeyError):
    """Raised when the budget file is missing required keys or shape."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--warmup-timeout-s", type=float, default=90.0)
    parser.add_argument("--num-requests", type=int, default=50)
    parser.add_argument("--budget-file", default="configs/model_30_budget.yaml")
    parser.add_argument(
        "--report-out",
        default="/tmp/model_30_smoke_report.json",  # noqa: S108 - CI scratch path
    )
    parser.add_argument("--cold-mem-mb", type=float, default=None)
    parser.add_argument("--warm-mem-mb", type=float, default=None)
    parser.add_argument("--jwt-env-var", default="MODEL_30_SMOKE_JWT")
    args = parser.parse_args(argv)
    _validate_args(args)
    return args


def _validate_args(args: argparse.Namespace) -> None:
    parsed = urlparse(args.api_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--api-url must include http:// or https:// and a hostname")
    if args.warmup_timeout_s <= 0:
        raise ValueError("--warmup-timeout-s must be greater than 0")
    if args.num_requests < 1:
        raise ValueError("--num-requests must be at least 1")


def load_budget_file(path: str | Path) -> dict[str, dict[str, float]]:
    """Load and validate the budget YAML."""
    budget_path = Path(path)
    with budget_path.open(encoding="utf-8") as budget_file:
        raw = yaml.safe_load(budget_file)
    if not isinstance(raw, dict):
        raise BudgetValidationError("Budget file must contain a mapping")

    budget: dict[str, dict[str, float]] = {}
    for key in REQUIRED_BUDGET_KEYS:
        if key not in raw:
            raise BudgetValidationError(f"Missing budget metric: {key}")
        entry = raw[key]
        if not isinstance(entry, dict):
            raise BudgetValidationError(f"Budget metric {key} must be a mapping")
        if "soft" not in entry or "hard" not in entry:
            raise BudgetValidationError(f"Budget metric {key} must include soft and hard")
        budget[key] = {"soft": float(entry["soft"]), "hard": float(entry["hard"])}
    return budget


def load_smoke_jwt(env_var_name: str) -> str:
    """Read the bearer token from the environment."""
    token = os.getenv(env_var_name)
    if not token:
        raise ValueError(f"Environment variable {env_var_name} is required")
    return token


def load_curated_payload() -> dict[str, Any]:
    """Load the canonical valid Model 30 payload."""
    fixture_path = Path("data/test_fixtures/model_30_curated_payload.json")
    with fixture_path.open(encoding="utf-8") as fixture_file:
        payload = json.load(fixture_file)
    if not isinstance(payload, dict):
        raise ValueError("Curated payload fixture must contain a JSON object")
    return payload


def compute_percentiles(samples: list[float]) -> dict[str, float | None]:
    """Compute inclusive p50/p95/p99 percentiles."""
    if not samples:
        return {"warm_p50_ms": None, "warm_p95_ms": None, "warm_p99_ms": None}
    if len(samples) == 1:
        value = round(samples[0], 2)
        return {"warm_p50_ms": value, "warm_p95_ms": value, "warm_p99_ms": value}

    quantiles = statistics.quantiles(samples, n=100, method="inclusive")
    return {
        "warm_p50_ms": round(quantiles[49], 2),
        "warm_p95_ms": round(quantiles[94], 2),
        "warm_p99_ms": round(quantiles[98], 2),
    }


def parse_json_body(text: str) -> Any:
    """Parse a JSON response body when present."""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def is_model_30_error_payload(status: int | None, body: Any) -> bool:
    """Return whether a response body looks like a route-specific Model 30 failure."""
    if status is None or body is None:
        return False
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail.startswith(MODEL_30_ERROR_PREFIXES)
        if isinstance(detail, dict):
            error = detail.get("error")
            if isinstance(error, str):
                return error == "model_not_ready" or error.startswith("Technical Task Router")
    return False


def classify_response(
    *,
    status: int | None,
    body: Any,
    error: BaseException | None = None,
) -> str:
    """Classify a response for gating purposes."""
    if error is not None:
        return "infra_network"
    if status is None:
        return "infra_network"
    if 200 <= status < 300:
        return "success"
    if status in {401, 403}:
        return "infra_auth"
    if status == 504:
        return "model_30_timeout"
    if status == 502 and not is_model_30_error_payload(status, body):
        return "infra_upstream"
    if is_model_30_error_payload(status, body):
        return "model_30_error"
    if 400 <= status < 600:
        return "infra_upstream"
    return "infra_upstream"


def build_report(
    *,
    metrics: dict[str, float | None],
    budget: dict[str, dict[str, float]],
    breaches: dict[str, list[str]],
    classification: str,
    exit_code: int,
    infra_summary: dict[str, int],
    samples: list[dict[str, Any]],
    model_30_error_count: int,
) -> dict[str, Any]:
    """Build the JSON report."""
    return {
        "metrics": metrics,
        "budget": budget,
        "breaches": breaches,
        "classification": classification,
        "exit_code": exit_code,
        "infra_summary": infra_summary,
        "model_30_error_count": model_30_error_count,
        "samples": samples,
    }


def evaluate_budgets(
    *,
    metrics: dict[str, float | None],
    budget: dict[str, dict[str, float]],
    samples: list[dict[str, Any]],
) -> tuple[int, str, dict[str, list[str]], dict[str, int], int]:
    """Evaluate collected samples against the configured budget."""
    counts = Counter(sample["classification"] for sample in samples)
    total_samples = len(samples)
    infra_summary = {
        "auth": counts["infra_auth"],
        "upstream": counts["infra_upstream"],
        "network": counts["infra_network"],
    }
    infra_failures = sum(infra_summary.values())
    breaches = {"hard": [], "soft": []}

    if total_samples and infra_failures / total_samples >= 0.2:
        return (
            INFRA_INCONCLUSIVE,
            "infra_inconclusive",
            breaches,
            infra_summary,
            counts["model_30_error"],
        )

    for metric_name, value in metrics.items():
        if value is None:
            continue
        thresholds = budget[metric_name]
        if value > thresholds["hard"]:
            breaches["hard"].append(metric_name)
        elif value > thresholds["soft"]:
            breaches["soft"].append(metric_name)

    model_30_error_count = counts["model_30_error"]
    if model_30_error_count > 0:
        return (
            MODEL_30_ERROR_EXCESS,
            "model_30_error_excess",
            breaches,
            infra_summary,
            model_30_error_count,
        )
    if breaches["hard"]:
        return LATENCY_BREACH, "hard_breach", breaches, infra_summary, model_30_error_count
    return 0, "pass", breaches, infra_summary, model_30_error_count


def _poll_ready(
    session: requests.Session,
    *,
    ready_url: str,
    timeout_s: float,
) -> tuple[dict[str, float | None], str | None]:
    """Poll the ready endpoint until Model 30 is warmed or clearly failed."""
    started_at = time.perf_counter()
    last_payload: Any = None
    while time.perf_counter() - started_at < timeout_s:
        try:
            response = session.get(ready_url, timeout=5)
        except requests.RequestException:
            time.sleep(0.25)
            continue

        payload = parse_json_body(response.text)
        last_payload = payload
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        warmup_duration = None
        if isinstance(payload, dict):
            warmup_duration = payload.get("warmup_duration_ms")
        if (
            response.status_code == 200
            and isinstance(payload, dict)
            and payload.get("ready") is True
            and isinstance(payload.get("model_30"), dict)
            and payload["model_30"].get("warmed") is True
        ):
            return {
                "cold_readiness_ms": elapsed_ms,
                "artifact_load_ms": float(warmup_duration) if warmup_duration is not None else None,
            }, None
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("model_30"), dict)
            and payload["model_30"].get("state") == "failed"
        ):
            return {
                "cold_readiness_ms": elapsed_ms,
                "artifact_load_ms": float(warmup_duration) if warmup_duration is not None else None,
            }, "model_30_failed_to_warm"
        time.sleep(0.25)

    warmup_duration = (
        last_payload.get("warmup_duration_ms") if isinstance(last_payload, dict) else None
    )
    return {
        "cold_readiness_ms": round((time.perf_counter() - started_at) * 1000, 2),
        "artifact_load_ms": float(warmup_duration) if warmup_duration is not None else None,
    }, "infra_inconclusive"


def _run_warm_requests(
    session: requests.Session,
    *,
    predict_url: str,
    payload: dict[str, Any],
    num_requests: int,
) -> list[dict[str, Any]]:
    """Issue sequential warm prediction requests."""
    samples: list[dict[str, Any]] = []
    for _ in range(num_requests):
        started_at = time.perf_counter()
        status: int | None = None
        body: Any = None
        error: BaseException | None = None
        try:
            response = session.post(predict_url, json={"inputs": payload}, timeout=30)
            status = response.status_code
            body = parse_json_body(response.text)
        except requests.RequestException as exc:
            error = exc

        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        samples.append(
            {
                "latency_ms": latency_ms,
                "status": status,
                "classification": classify_response(status=status, body=body, error=error),
            }
        )
    return samples


def run_smoke_check(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    """Execute the end-to-end smoke check and return its exit code plus report."""
    budget = load_budget_file(args.budget_file)
    token = load_smoke_jwt(args.jwt_env_var)
    payload = load_curated_payload()

    api_url = args.api_url.rstrip("/")
    ready_url = f"{api_url}/ready"
    predict_url = f"{api_url}/api/v1/models/30/predict"

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    )

    readiness_metrics, readiness_state = _poll_ready(
        session,
        ready_url=ready_url,
        timeout_s=args.warmup_timeout_s,
    )

    base_metrics: dict[str, float | None] = {
        **readiness_metrics,
        "warm_p50_ms": None,
        "warm_p95_ms": None,
        "warm_p99_ms": None,
        "timeout_rate": 0.0,
        "warm_memory_mb": args.warm_mem_mb,
        "cold_memory_mb": args.cold_mem_mb,
    }

    if readiness_state == "infra_inconclusive":
        report = build_report(
            metrics=base_metrics,
            budget=budget,
            breaches={"hard": [], "soft": []},
            classification="infra_inconclusive",
            exit_code=INFRA_INCONCLUSIVE,
            infra_summary={"auth": 0, "upstream": 0, "network": 0},
            samples=[],
            model_30_error_count=0,
        )
        return INFRA_INCONCLUSIVE, report

    if readiness_state == "model_30_failed_to_warm":
        report = build_report(
            metrics=base_metrics,
            budget=budget,
            breaches={"hard": [], "soft": []},
            classification="model_30_error_excess",
            exit_code=MODEL_30_ERROR_EXCESS,
            infra_summary={"auth": 0, "upstream": 0, "network": 0},
            samples=[],
            model_30_error_count=1,
        )
        return MODEL_30_ERROR_EXCESS, report

    samples = _run_warm_requests(
        session,
        predict_url=predict_url,
        payload=payload,
        num_requests=args.num_requests,
    )

    successful_latencies = [
        sample["latency_ms"] for sample in samples if sample["classification"] == "success"
    ]
    percentiles = compute_percentiles(successful_latencies)
    timeout_denominator = sum(
        1 for sample in samples if sample["classification"] in {"success", "model_30_timeout"}
    )
    timeout_count = sum(1 for sample in samples if sample["classification"] == "model_30_timeout")
    timeout_rate = round(timeout_count / timeout_denominator, 4) if timeout_denominator else 0.0
    metrics = {**base_metrics, **percentiles, "timeout_rate": timeout_rate}

    exit_code, classification, breaches, infra_summary, model_30_error_count = evaluate_budgets(
        metrics=metrics,
        budget=budget,
        samples=samples,
    )
    report = build_report(
        metrics=metrics,
        budget=budget,
        breaches=breaches,
        classification=classification,
        exit_code=exit_code,
        infra_summary=infra_summary,
        samples=samples,
        model_30_error_count=model_30_error_count,
    )
    return exit_code, report


def write_report(path: str | Path, report: dict[str, Any]) -> None:
    """Write the JSON report to disk."""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(f"{json.dumps(report, indent=2, sort_keys=True)}\n", encoding="utf-8")


def print_summary(report: dict[str, Any]) -> None:
    """Emit a short human-readable summary."""
    metrics = report["metrics"]
    summary = {
        "classification": report["classification"],
        "exit_code": report["exit_code"],
        "cold_readiness_ms": metrics["cold_readiness_ms"],
        "artifact_load_ms": metrics["artifact_load_ms"],
        "warm_p95_ms": metrics["warm_p95_ms"],
        "timeout_rate": metrics["timeout_rate"],
        "hard_breaches": report["breaches"]["hard"],
        "soft_breaches": report["breaches"]["soft"],
        "infra_summary": report["infra_summary"],
        "model_30_error_count": report["model_30_error_count"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))  # noqa: T201


def _write_infra_inconclusive_report(args: argparse.Namespace, reason: str) -> None:
    """Persist a minimal infra_inconclusive report so downstream steps can read it."""
    try:
        budget = load_budget_file(args.budget_file)
    except (OSError, ValueError, BudgetValidationError, yaml.YAMLError):
        budget = {}
    report = build_report(
        metrics={
            "cold_readiness_ms": None,
            "artifact_load_ms": None,
            "warm_p50_ms": None,
            "warm_p95_ms": None,
            "warm_p99_ms": None,
            "timeout_rate": 0.0,
            "warm_memory_mb": args.warm_mem_mb,
            "cold_memory_mb": args.cold_mem_mb,
        },
        budget=budget,
        breaches={"hard": [], "soft": []},
        classification="infra_inconclusive",
        exit_code=INFRA_INCONCLUSIVE,
        infra_summary={"auth": 0, "upstream": 0, "network": 0},
        samples=[],
        model_30_error_count=0,
    )
    report["reason"] = reason
    write_report(args.report_out, report)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    try:
        args = parse_args(argv)
    except (OSError, ValueError, BudgetValidationError, yaml.YAMLError) as exc:
        print(f"model_30_smoke_check setup error: {exc}", file=sys.stderr)  # noqa: T201
        return SETUP_ERROR

    if not os.getenv(args.jwt_env_var):
        reason = (
            f"Environment variable {args.jwt_env_var} is not set; "
            "cannot exercise authenticated Model 30 predictions."
        )
        print(  # noqa: T201
            f"::warning::model_30_smoke_check infra_inconclusive: {reason}",
            file=sys.stderr,
        )
        _write_infra_inconclusive_report(args, reason)
        return INFRA_INCONCLUSIVE

    try:
        exit_code, report = run_smoke_check(args)
        write_report(args.report_out, report)
        print_summary(report)
        return exit_code
    except (OSError, ValueError, BudgetValidationError, yaml.YAMLError) as exc:
        print(f"model_30_smoke_check setup error: {exc}", file=sys.stderr)  # noqa: T201
        return SETUP_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
