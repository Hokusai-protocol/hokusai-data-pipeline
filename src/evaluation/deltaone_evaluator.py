"""DeltaOne evaluation with statistical rigor and MLflow-backed auditability."""

from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import requests

from src.evaluation.hem import HEM

logger = logging.getLogger(__name__)

SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
DATASET_HASH_KEYS = (
    "hokusai.dataset.hash",
    "dataset_hash",
    "dataset.hash",
)
SAMPLE_SIZE_KEYS = (
    "hokusai.dataset.num_samples",
    "dataset:n_examples",
    "n_examples",
    "num_examples",
)
PRIMARY_METRIC_KEYS = (
    "hokusai.primary_metric",
    "primary_metric",
    "benchmark_metric",
)
MODEL_ID_KEYS = ("hokusai.model_id", "model_id", "mlflow.runName")


class RunInfoProtocol(Protocol):
    """Subset of MLflow run info fields consumed by this module."""

    run_id: str
    experiment_id: str
    start_time: int | None


class RunDataProtocol(Protocol):
    """Subset of MLflow run data payload consumed by this module."""

    metrics: dict[str, float]
    tags: dict[str, str]
    params: dict[str, str]


class RunProtocol(Protocol):
    """Subset of MLflow run entity consumed by this module."""

    info: RunInfoProtocol
    data: RunDataProtocol


class MlflowClientProtocol(Protocol):
    """Subset of MLflow client operations required by DeltaOne logic."""

    def get_run(self: MlflowClientProtocol, run_id: str) -> RunProtocol: ...

    def search_model_versions(self: MlflowClientProtocol, filter_string: str) -> list[Any]: ...

    def search_runs(
        self: MlflowClientProtocol,
        experiment_ids: list[str],
        filter_string: str,
        max_results: int,
        order_by: list[str],
    ) -> list[Any]: ...

    def set_tag(self: MlflowClientProtocol, run_id: str, key: str, value: str) -> None: ...


def _load_mlflow() -> Any:
    """Load mlflow lazily so module import works without optional dependencies."""
    try:
        import mlflow  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "mlflow is required for DeltaOne evaluation. Install the mlflow dependency."
        ) from exc
    return mlflow


def _load_mlflow_client_class() -> type[Any]:
    """Load MlflowClient lazily."""
    try:
        from mlflow.tracking import MlflowClient as _MlflowClient  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "mlflow is required for DeltaOne evaluation. Install the mlflow dependency."
        ) from exc
    return _MlflowClient


try:
    MlflowClient = _load_mlflow_client_class()
except ImportError:  # pragma: no cover - exercised in dedicated missing-mlflow tests
    MlflowClient = None  # type: ignore[assignment]


@dataclass(slots=True)
class DeltaOneDecision:
    """Structured decision payload for DeltaOne evaluation attempts."""

    accepted: bool
    reason: str
    run_id: str
    baseline_run_id: str
    model_id: str
    dataset_hash: str
    metric_name: str
    delta_percentage_points: float
    ci95_low_percentage_points: float
    ci95_high_percentage_points: float
    n_current: int
    n_baseline: int
    evaluated_at: datetime


class DeltaOneEvaluator:
    """Evaluate candidate MLflow runs against a baseline with anti-gaming controls."""

    def __init__(
        self: DeltaOneEvaluator,
        mlflow_client: MlflowClientProtocol | None = None,
        cooldown_hours: int = 24,
        min_examples: int = 800,
        delta_threshold_pp: float = 1.0,
    ) -> None:
        if cooldown_hours < 0:
            raise ValueError("cooldown_hours must be >= 0")
        if min_examples < 1:
            raise ValueError("min_examples must be >= 1")
        if delta_threshold_pp < 0:
            raise ValueError("delta_threshold_pp must be >= 0")

        self._client = mlflow_client or self._create_default_mlflow_client()
        self.cooldown_hours = cooldown_hours
        self.min_examples = min_examples
        self.delta_threshold_pp = delta_threshold_pp

    def evaluate(
        self: DeltaOneEvaluator, mlflow_run_id: str, baseline_mlflow_run_id: str
    ) -> DeltaOneDecision:
        """Evaluate whether candidate run qualifies as a statistically significant DeltaOne."""
        evaluated_at = datetime.now(timezone.utc)
        candidate = self._extract_metrics_from_run(mlflow_run_id)
        baseline = self._extract_metrics_from_run(
            baseline_mlflow_run_id,
            expected_metric_name=candidate.metric_name,
        )

        self._log_audit_event(
            "deltaone_evaluation_started",
            run_id=mlflow_run_id,
            baseline_run_id=baseline_mlflow_run_id,
            model_id=candidate.model_id,
            dataset_hash=candidate.dataset_hash,
            metric_name=candidate.metric_name,
            n_current=candidate.sample_size,
            n_baseline=baseline.sample_size,
        )

        if candidate.sample_size < self.min_examples or baseline.sample_size < self.min_examples:
            decision = self._build_decision(
                accepted=False,
                reason="insufficient_samples",
                candidate=candidate,
                baseline=baseline,
                ci_low=0.0,
                ci_high=0.0,
                evaluated_at=evaluated_at,
            )
            self._persist_decision(decision)
            return decision

        if candidate.dataset_hash != baseline.dataset_hash:
            decision = self._build_decision(
                accepted=False,
                reason="dataset_hash_mismatch",
                candidate=candidate,
                baseline=baseline,
                ci_low=0.0,
                ci_high=0.0,
                evaluated_at=evaluated_at,
            )
            self._persist_decision(decision)
            return decision

        cooldown_ok, blocked_until = self._check_cooldown(
            model_id=candidate.model_id,
            dataset_hash=candidate.dataset_hash,
            experiment_id=candidate.experiment_id,
            now=evaluated_at,
            current_run_id=candidate.source_mlflow_run_id,
        )
        if not cooldown_ok:
            reason = (
                f"cooldown_active_until_{blocked_until.isoformat()}"
                if blocked_until
                else "cooldown_active"
            )
            decision = self._build_decision(
                accepted=False,
                reason=reason,
                candidate=candidate,
                baseline=baseline,
                ci_low=0.0,
                ci_high=0.0,
                evaluated_at=evaluated_at,
            )
            self._persist_decision(decision)
            return decision

        delta_pp = _calculate_percentage_point_difference(
            baseline=baseline.metric_value,
            current=candidate.metric_value,
        )
        significant, ci_low, ci_high = self._is_statistically_significant(
            baseline_metric=baseline.metric_value,
            current_metric=candidate.metric_value,
            baseline_n=baseline.sample_size,
            current_n=candidate.sample_size,
        )

        if delta_pp < self.delta_threshold_pp:
            decision = self._build_decision(
                accepted=False,
                reason="delta_below_threshold",
                candidate=candidate,
                baseline=baseline,
                ci_low=ci_low,
                ci_high=ci_high,
                evaluated_at=evaluated_at,
            )
            self._persist_decision(decision)
            return decision

        if not significant:
            decision = self._build_decision(
                accepted=False,
                reason="not_statistically_significant",
                candidate=candidate,
                baseline=baseline,
                ci_low=ci_low,
                ci_high=ci_high,
                evaluated_at=evaluated_at,
            )
            self._persist_decision(decision)
            return decision

        decision = self._build_decision(
            accepted=True,
            reason="accepted",
            candidate=candidate,
            baseline=baseline,
            ci_low=ci_low,
            ci_high=ci_high,
            evaluated_at=evaluated_at,
        )
        self._persist_decision(decision)
        return decision

    def _extract_metrics_from_run(
        self: DeltaOneEvaluator,
        mlflow_run_id: str,
        expected_metric_name: str | None = None,
    ) -> HEM:
        """Extract HEM fields from a single MLflow run via one client call."""
        run = self._client.get_run(mlflow_run_id)
        tags = run.data.tags or {}
        params = run.data.params or {}
        metrics = run.data.metrics or {}

        metric_name = expected_metric_name or self._first_non_empty(tags, PRIMARY_METRIC_KEYS)
        if not metric_name:
            if len(metrics) == 1:
                metric_name = next(iter(metrics.keys()))
            else:
                raise ValueError(
                    "Unable to resolve primary metric. Set one of "
                    "'hokusai.primary_metric', 'primary_metric', or 'benchmark_metric'."
                )

        if metric_name not in metrics:
            raise ValueError(f"Primary metric '{metric_name}' missing from run metrics.")

        sample_size_raw = self._first_non_empty(tags, SAMPLE_SIZE_KEYS) or self._first_non_empty(
            params, SAMPLE_SIZE_KEYS
        )
        if sample_size_raw is None:
            raise ValueError("Missing sample size in run tags/params.")

        try:
            sample_size = int(sample_size_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid sample size '{sample_size_raw}'.") from exc

        dataset_hash = self._first_non_empty(tags, DATASET_HASH_KEYS) or self._first_non_empty(
            params, DATASET_HASH_KEYS
        )
        if not dataset_hash:
            raise ValueError("Missing dataset hash in run tags/params.")
        if not SHA256_PATTERN.match(dataset_hash):
            raise ValueError("Dataset hash must be exact 'sha256:<64 lowercase hex>' format.")

        model_id = self._first_non_empty(tags, MODEL_ID_KEYS) or "unknown-model"

        start_time_ms = run.info.start_time
        if start_time_ms is None:
            timestamp = datetime.now(timezone.utc)
        else:
            timestamp = datetime.fromtimestamp(start_time_ms / 1000, tz=timezone.utc)

        return HEM(
            metric_name=metric_name,
            metric_value=float(metrics[metric_name]),
            sample_size=sample_size,
            dataset_hash=dataset_hash,
            timestamp=timestamp,
            source_mlflow_run_id=run.info.run_id,
            model_id=model_id,
            experiment_id=run.info.experiment_id,
        )

    def _is_statistically_significant(
        self: DeltaOneEvaluator,
        baseline_metric: float,
        current_metric: float,
        baseline_n: int,
        current_n: int,
    ) -> tuple[bool, float, float]:
        """Return significance + 95% CI bounds (percentage points) for the delta."""
        if not (0.0 <= baseline_metric <= 1.0 and 0.0 <= current_metric <= 1.0):
            raise ValueError("Statistical test only supports proportion metrics in [0, 1].")

        baseline_se = math.sqrt((baseline_metric * (1.0 - baseline_metric)) / baseline_n)
        current_se = math.sqrt((current_metric * (1.0 - current_metric)) / current_n)
        combined_se = math.sqrt((baseline_se**2) + (current_se**2))

        delta_pp = (current_metric - baseline_metric) * 100.0
        margin_pp = 1.96 * combined_se * 100.0
        ci_low = delta_pp - margin_pp
        ci_high = delta_pp + margin_pp

        # Significance for positive improvement requires lower bound above zero.
        return ci_low > 0.0, ci_low, ci_high

    def _check_cooldown(
        self: DeltaOneEvaluator,
        model_id: str,
        dataset_hash: str,
        experiment_id: str,
        now: datetime,
        current_run_id: str,
    ) -> tuple[bool, datetime | None]:
        """Enforce minimum cooldown between evaluations for same model/dataset."""
        if self.cooldown_hours == 0:
            return True, None

        filter_string = (
            f"tags.`hokusai.deltaone.model_id` = '{model_id}' and "
            f"tags.`hokusai.deltaone.dataset_hash` = '{dataset_hash}'"
        )

        runs = self._client.search_runs(
            experiment_ids=[experiment_id],
            filter_string=filter_string,
            max_results=20,
            order_by=["attributes.start_time DESC"],
        )

        last_eval: datetime | None = None
        for run in runs:
            if run.info.run_id == current_run_id:
                continue
            timestamp_raw = (run.data.tags or {}).get("hokusai.deltaone.evaluated_at")
            if not timestamp_raw:
                continue
            parsed = self._parse_utc(timestamp_raw)
            if parsed is None:
                continue
            if last_eval is None or parsed > last_eval:
                last_eval = parsed

        if last_eval is None:
            return True, None

        blocked_until = last_eval + timedelta(hours=self.cooldown_hours)
        if now < blocked_until:
            return False, blocked_until
        return True, blocked_until

    def _build_decision(
        self: DeltaOneEvaluator,
        accepted: bool,
        reason: str,
        candidate: HEM,
        baseline: HEM,
        ci_low: float,
        ci_high: float,
        evaluated_at: datetime,
    ) -> DeltaOneDecision:
        return DeltaOneDecision(
            accepted=accepted,
            reason=reason,
            run_id=candidate.source_mlflow_run_id,
            baseline_run_id=baseline.source_mlflow_run_id,
            model_id=candidate.model_id,
            dataset_hash=candidate.dataset_hash,
            metric_name=candidate.metric_name,
            delta_percentage_points=_calculate_percentage_point_difference(
                baseline=baseline.metric_value,
                current=candidate.metric_value,
            ),
            ci95_low_percentage_points=ci_low,
            ci95_high_percentage_points=ci_high,
            n_current=candidate.sample_size,
            n_baseline=baseline.sample_size,
            evaluated_at=evaluated_at,
        )

    def _persist_decision(self: DeltaOneEvaluator, decision: DeltaOneDecision) -> None:
        tags = {
            "hokusai.deltaone.model_id": decision.model_id,
            "hokusai.deltaone.dataset_hash": decision.dataset_hash,
            "hokusai.deltaone.metric_name": decision.metric_name,
            "hokusai.deltaone.baseline_run_id": decision.baseline_run_id,
            "hokusai.deltaone.accepted": str(decision.accepted).lower(),
            "hokusai.deltaone.reason": decision.reason,
            "hokusai.deltaone.delta_pp": f"{decision.delta_percentage_points:.6f}",
            "hokusai.deltaone.ci95_low_pp": f"{decision.ci95_low_percentage_points:.6f}",
            "hokusai.deltaone.ci95_high_pp": f"{decision.ci95_high_percentage_points:.6f}",
            "hokusai.deltaone.n_current": str(decision.n_current),
            "hokusai.deltaone.n_baseline": str(decision.n_baseline),
            "hokusai.deltaone.evaluated_at": decision.evaluated_at.isoformat(),
        }
        for key, value in tags.items():
            self._client.set_tag(decision.run_id, key, value)

        event = (
            "deltaone_evaluation_accepted" if decision.accepted else "deltaone_evaluation_rejected"
        )
        self._log_audit_event(
            event,
            run_id=decision.run_id,
            baseline_run_id=decision.baseline_run_id,
            model_id=decision.model_id,
            dataset_hash=decision.dataset_hash,
            metric_name=decision.metric_name,
            reason=decision.reason,
            delta_pp=decision.delta_percentage_points,
            ci95_low_pp=decision.ci95_low_percentage_points,
            ci95_high_pp=decision.ci95_high_percentage_points,
            n_current=decision.n_current,
            n_baseline=decision.n_baseline,
            evaluated_at=decision.evaluated_at.isoformat(),
        )

    def _create_default_mlflow_client(self: DeltaOneEvaluator) -> MlflowClientProtocol:
        if MlflowClient is not None:
            return MlflowClient()
        return _load_mlflow_client_class()()

    @staticmethod
    def _first_non_empty(source: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = source.get(key)
            if value is not None and str(value).strip() != "":
                return str(value)
        return None

    @staticmethod
    def _parse_utc(value: str) -> datetime | None:
        candidate = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _log_audit_event(event: str, **fields: Any) -> None:
        logger.info("%s", event, extra={"audit_event": event, **fields})


def detect_delta_one(model_name: str, webhook_url: str | None = None) -> bool:
    """Backward-compatible DeltaOne check using latest and baseline model versions."""
    try:
        client = MlflowClient() if MlflowClient is not None else _load_mlflow_client_class()()

        versions = _get_sorted_model_versions(client, model_name)
        if len(versions) < 2:
            logger.info(
                "Not enough versions for model %s. Found %s versions.",
                model_name,
                len(versions),
            )
            return False

        latest_version = versions[0]
        baseline_version = _find_baseline_version(versions[1:])
        if not baseline_version:
            logger.warning("No baseline version found for model %s", model_name)
            return False

        metric_name = latest_version.tags.get("benchmark_metric") or baseline_version.tags.get(
            "benchmark_metric"
        )
        baseline_value_raw = baseline_version.tags.get("benchmark_value")

        if not metric_name or baseline_value_raw is None:
            logger.error("Missing benchmark_metric or benchmark_value in model version tags")
            return False

        baseline_value = float(baseline_value_raw)
        current_value = _get_metric_value(client, latest_version, metric_name)
        if current_value is None:
            logger.error("Metric %s not found in latest version", metric_name)
            return False

        delta_pp = _calculate_percentage_point_difference(baseline_value, current_value)

        if delta_pp >= 1.0:
            logger.info("DeltaOne achieved for %s: %.3fpp improvement", model_name, delta_pp)
            try:
                mlflow = _load_mlflow()
                if mlflow.active_run():
                    mlflow.log_metric("custom:deltaone_achieved", 1.0)
                    mlflow.log_metric("custom:delta_value", delta_pp)
                else:
                    mlflow.log_metric("custom:deltaone_achieved", 1.0)
                    mlflow.log_metric("custom:delta_value", delta_pp)
            except Exception as exc:  # pragma: no cover
                logger.debug("Could not log metrics to MLflow: %s", exc)

            if webhook_url:
                payload = {
                    "model_name": model_name,
                    "delta_value": delta_pp,
                    "baseline_version": baseline_version.version,
                    "new_version": latest_version.version,
                    "metric_name": metric_name,
                    "baseline_value": baseline_value,
                    "current_value": current_value,
                }
                send_deltaone_webhook(webhook_url, payload)
            return True

        logger.info("No DeltaOne improvement for %s: %.3fpp", model_name, delta_pp)
        return False
    except Exception as exc:
        logger.error("Error detecting DeltaOne for %s: %s", model_name, exc)
        return False


def _get_sorted_model_versions(client: MlflowClientProtocol, model_name: str) -> list[Any]:
    """Get model versions sorted by version number (descending)."""
    versions = client.search_model_versions(f"name='{model_name}'")
    return sorted(versions, key=lambda version: int(version.version), reverse=True)


def _find_baseline_version(versions: list[Any]) -> Any | None:
    """Find the latest version with benchmark_value and benchmark_metric tags."""
    for version in versions:
        tags = getattr(version, "tags", {}) or {}
        if "benchmark_value" in tags and "benchmark_metric" in tags:
            return version
    return None


def _get_metric_value(client: MlflowClientProtocol, version: Any, metric_name: str) -> float | None:
    """Get metric value from a model version's run."""
    try:
        run = client.get_run(version.run_id)
        return (run.data.metrics or {}).get(metric_name)
    except Exception as exc:
        logger.error("Error getting metric %s: %s", metric_name, exc)
        return None


def _calculate_percentage_point_difference(baseline: float, current: float) -> float:
    """Calculate percentage-point difference from ratio metrics."""
    return (current - baseline) * 100.0


def send_deltaone_webhook(webhook_url: str, payload: dict[str, Any], max_retries: int = 3) -> bool:
    """Send a DeltaOne webhook notification with retry and backoff."""
    headers = {"Content-Type": "application/json", "User-Agent": "Hokusai-DeltaOne/1.0"}

    for attempt in range(max_retries):
        try:
            response = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                logger.info("DeltaOne webhook notification sent successfully")
                return True
            logger.warning("Webhook returned status %s", response.status_code)
        except requests.exceptions.RequestException as exc:
            logger.error("Webhook request failed (attempt %s): %s", attempt + 1, exc)

        if attempt < max_retries - 1:
            time.sleep(2**attempt)

    logger.error("Failed to send webhook after %s attempts", max_retries)
    return False
