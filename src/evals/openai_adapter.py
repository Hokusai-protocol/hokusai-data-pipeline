"""Lightweight adapter for running OpenAI Evals via the `oaieval` CLI."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any

import mlflow

_UNSAFE_TOKEN_PATTERN = re.compile(r"[;&|`$<>\\\n\r]")
_TEXT_METRIC_PATTERN = re.compile(r"([A-Za-z][\w\-.]+)\s*[:=]\s*(-?\d+(?:\.\d+)?)")


class OpenAIEvalsAdapter:
    """Run `oaieval` and persist parsed metrics plus raw output to MLflow."""

    def __init__(self: OpenAIEvalsAdapter, experiment_name: str | None = None) -> None:
        # MLflow SDK reads MLFLOW_TRACKING_TOKEN for Authorization automatically.
        self.tracking_token = os.getenv("MLFLOW_TRACKING_TOKEN")
        self.experiment_name = experiment_name
        tracking_uri = os.getenv(
            "MLFLOW_SERVER_URL", "http://mlflow.hokusai-development.local:5000"
        )
        mlflow.set_tracking_uri(tracking_uri)
        if experiment_name:
            mlflow.set_experiment(experiment_name)

    def run(
        self: OpenAIEvalsAdapter,
        eval_spec: str,
        model_ref: str,
        tags: dict[str, str] | None = None,
    ) -> str:
        """Execute an OpenAI eval run and return the created MLflow run ID."""
        self._validate_input(eval_spec)
        self._validate_input(model_ref)

        try:
            completed = self._execute_oaieval(eval_spec=eval_spec, model_ref=model_ref)
            metrics = self._parse_results(completed.stdout)
            return self._log_to_mlflow(
                metrics=metrics,
                raw_output=completed.stdout,
                eval_spec=eval_spec,
                model_ref=model_ref,
                tags=tags,
                failed=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "OpenAI Evals CLI not found. Install `openai-evals` so `oaieval` is available."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raw_output = "\n".join(part for part in [exc.stdout, exc.stderr] if part)
            self._log_to_mlflow(
                metrics={},
                raw_output=raw_output or "oaieval failed with no output",
                eval_spec=eval_spec,
                model_ref=model_ref,
                tags=tags,
                failed=True,
                error_message=(exc.stderr or str(exc)).strip(),
            )
            raise RuntimeError(f"oaieval failed with exit code {exc.returncode}") from exc

    def _validate_input(self: OpenAIEvalsAdapter, value: str) -> None:
        if not value.strip():
            raise ValueError("eval_spec and model_ref must be non-empty strings")
        if _UNSAFE_TOKEN_PATTERN.search(value):
            raise ValueError("eval_spec and model_ref contain unsupported shell metacharacters")

    def _execute_oaieval(
        self: OpenAIEvalsAdapter, eval_spec: str, model_ref: str
    ) -> subprocess.CompletedProcess[str]:
        binary = shutil.which("oaieval")
        if not binary:
            raise FileNotFoundError("oaieval")
        return subprocess.run(  # noqa: S603
            [binary, model_ref, eval_spec],  # noqa: S603
            check=True,
            capture_output=True,
            text=True,
        )

    def _parse_results(self: OpenAIEvalsAdapter, stdout: str) -> dict[str, float]:
        metrics: dict[str, float] = {}
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            report = payload.get("final_report") if isinstance(payload, dict) else None
            if isinstance(report, dict):
                for key, value in report.items():
                    if isinstance(value, (int, float)):
                        metrics[str(key)] = float(value)
        if metrics:
            return metrics
        for key, value in _TEXT_METRIC_PATTERN.findall(stdout):
            metrics[key] = float(value)
        return metrics

    def _log_to_mlflow(
        self: OpenAIEvalsAdapter,
        metrics: dict[str, float],
        raw_output: str,
        eval_spec: str,
        model_ref: str,
        tags: dict[str, str] | None,
        failed: bool,
        error_message: str | None = None,
    ) -> str:
        with mlflow.start_run() as run:
            if metrics:
                mlflow.log_metrics(metrics)
            else:
                mlflow.log_metric("parsed_metric_count", 0.0)
                mlflow.set_tag("eval:parse_warning", "no_numeric_metrics_found")

            mlflow.log_text(raw_output, "output.txt")
            base_tags: dict[str, Any] = {
                "eval:provider": "openai_evals",
                "eval:spec": eval_spec,
                "eval:model_ref": model_ref,
                "eval:status": "failed" if failed else "success",
            }
            if error_message:
                base_tags["eval:error"] = error_message
            if tags:
                base_tags.update(tags)
            for key, value in base_tags.items():
                mlflow.set_tag(str(key), str(value))
            return run.info.run_id
