"""Trace Loader for retrieving DSPy execution traces from MLflow.

This service loads execution traces from MLflow that have been logged
by the MLflow DSPy integration, filters them by quality and date range,
and prepares them for teleprompt optimization.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

import mlflow
import pandas as pd
from mlflow.tracking import MlflowClient

logger = logging.getLogger(__name__)


class TraceLoader:
    """Service for loading DSPy execution traces from MLflow."""

    def __init__(self, tracking_uri: Optional[str] = None) -> None:
        """Initialize trace loader.

        Args:
            tracking_uri: Optional MLflow tracking URI

        """
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        self.client = MlflowClient()

    def load_traces(
        self,
        program_name: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_score: float = 0.0,
        outcome_metric: str = "outcome_score",
        limit: int = 100000,
        experiment_name: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Load traces from MLflow with filtering.

        Args:
            program_name: Optional filter by DSPy program name
            start_date: Start date for trace collection
            end_date: End date for trace collection
            min_score: Minimum outcome score to include
            outcome_metric: Name of the outcome metric to filter by
            limit: Maximum number of traces to return
            experiment_name: Optional experiment name to search in

        Returns:
            List of trace dictionaries with inputs, outputs, and metadata

        """
        logger.info(f"Loading traces for {program_name or 'all programs'}")

        try:
            # Build search filter
            filter_string = self._build_filter_string(
                program_name, start_date, end_date, min_score, outcome_metric
            )

            # Get experiment IDs
            experiment_ids = self._get_experiment_ids(experiment_name)

            # Search for runs
            runs = self.client.search_runs(
                experiment_ids=experiment_ids,
                filter_string=filter_string,
                max_results=limit,
                order_by=["metrics.outcome_score DESC"],
            )

            # Extract traces from runs
            traces = []
            for run in runs:
                trace = self._extract_trace_from_run(run)
                if trace:
                    traces.append(trace)

            logger.info(f"Loaded {len(traces)} traces")
            return traces

        except Exception as e:
            logger.error(f"Error loading traces: {e}")
            return []

    def load_traces_by_contributor(
        self,
        contributor_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        """Load traces for a specific contributor.

        Args:
            contributor_id: Contributor ID to filter by
            start_date: Optional start date
            end_date: Optional end date
            limit: Maximum number of traces

        Returns:
            List of traces from the contributor

        """
        filter_parts = [f"tags.contributor_id = '{contributor_id}'"]

        if start_date:
            filter_parts.append(f"attributes.start_time >= {int(start_date.timestamp() * 1000)}")
        if end_date:
            filter_parts.append(f"attributes.end_time <= {int(end_date.timestamp() * 1000)}")

        filter_string = " and ".join(filter_parts)

        runs = self.client.search_runs(
            experiment_ids=self._get_experiment_ids(),
            filter_string=filter_string,
            max_results=limit,
        )

        traces = []
        for run in runs:
            trace = self._extract_trace_from_run(run)
            if trace:
                traces.append(trace)

        return traces

    def aggregate_traces_by_quality(
        self, traces: list[dict[str, Any]], buckets: int = 10
    ) -> dict[str, list[dict[str, Any]]]:
        """Aggregate traces into quality buckets.

        Args:
            traces: List of traces
            buckets: Number of quality buckets

        Returns:
            Dictionary mapping quality ranges to traces

        """
        if not traces:
            return {}

        # Calculate bucket size
        scores = [t.get("outcome_score", 0) for t in traces]
        min_score = min(scores)
        max_score = max(scores)
        bucket_size = (max_score - min_score) / buckets

        # Create buckets
        bucketed_traces = {}
        for i in range(buckets):
            bucket_min = min_score + i * bucket_size
            bucket_max = min_score + (i + 1) * bucket_size
            bucket_key = f"{bucket_min:.2f}-{bucket_max:.2f}"
            bucketed_traces[bucket_key] = []

        # Assign traces to buckets
        for trace in traces:
            score = trace.get("outcome_score", 0)
            bucket_idx = min(int((score - min_score) / bucket_size), buckets - 1)
            bucket_min = min_score + bucket_idx * bucket_size
            bucket_max = min_score + (bucket_idx + 1) * bucket_size
            bucket_key = f"{bucket_min:.2f}-{bucket_max:.2f}"
            bucketed_traces[bucket_key].append(trace)

        return bucketed_traces

    def sample_traces(
        self, traces: list[dict[str, Any]], sample_size: int, strategy: str = "stratified"
    ) -> list[dict[str, Any]]:
        """Sample traces using specified strategy.

        Args:
            traces: List of traces to sample from
            sample_size: Number of traces to sample
            strategy: Sampling strategy ('random', 'stratified', 'top')

        Returns:
            Sampled list of traces

        """
        if len(traces) <= sample_size:
            return traces

        if strategy == "random":
            import random

            return random.sample(traces, sample_size)

        elif strategy == "stratified":
            # Stratified sampling by outcome score
            df = pd.DataFrame(traces)
            df["score_bucket"] = pd.qcut(df["outcome_score"], q=10, duplicates="drop")

            # Sample proportionally from each bucket
            sampled = df.groupby("score_bucket", group_keys=False).apply(
                lambda x: x.sample(n=max(1, int(len(x) * sample_size / len(df))), random_state=42)
            )

            return sampled.to_dict("records")

        elif strategy == "top":
            # Take top scoring traces
            sorted_traces = sorted(traces, key=lambda x: x.get("outcome_score", 0), reverse=True)
            return sorted_traces[:sample_size]

        else:
            raise ValueError(f"Unknown sampling strategy: {strategy}")

    def _build_filter_string(
        self,
        program_name: Optional[str],
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        min_score: float,
        outcome_metric: str,
    ) -> str:
        """Build MLflow search filter string.

        Args:
            program_name: Program name filter
            start_date: Start date filter
            end_date: End date filter
            min_score: Minimum score filter
            outcome_metric: Outcome metric name

        Returns:
            MLflow filter string

        """
        filter_parts = []

        if program_name:
            filter_parts.append(f"tags.dspy_program_name = '{program_name}'")

        if start_date:
            timestamp_ms = int(start_date.timestamp() * 1000)
            filter_parts.append(f"attributes.start_time >= {timestamp_ms}")

        if end_date:
            timestamp_ms = int(end_date.timestamp() * 1000)
            filter_parts.append(f"attributes.start_time <= {timestamp_ms}")

        if min_score > 0:
            filter_parts.append(f"metrics.{outcome_metric} >= {min_score}")

        # Ensure we only get runs with traces
        filter_parts.append("tags.has_dspy_traces = 'true'")

        return " and ".join(filter_parts) if filter_parts else ""

    def _get_experiment_ids(self, experiment_name: Optional[str] = None) -> list[str]:
        """Get experiment IDs to search.

        Args:
            experiment_name: Optional specific experiment name

        Returns:
            List of experiment IDs

        """
        if experiment_name:
            experiment = self.client.get_experiment_by_name(experiment_name)
            if experiment:
                return [experiment.experiment_id]
            else:
                logger.warning(f"Experiment '{experiment_name}' not found")
                return []

        # Get all DSPy-related experiments
        experiments = self.client.search_experiments(filter_string="tags.dspy_enabled = 'true'")

        exp_ids = [exp.experiment_id for exp in experiments]

        # If no DSPy experiments found, search all
        if not exp_ids:
            experiments = self.client.search_experiments()
            exp_ids = [exp.experiment_id for exp in experiments]

        return exp_ids

    def _extract_trace_from_run(self, run) -> Optional[dict[str, Any]]:
        """Extract trace information from MLflow run.

        Args:
            run: MLflow run object

        Returns:
            Trace dictionary or None if no valid trace

        """
        try:
            # Check if run has DSPy traces
            if run.data.tags.get("has_dspy_traces") != "true":
                return None

            # Build trace dictionary
            trace = {
                "trace_id": run.info.run_id,
                "run_id": run.info.run_id,
                "program_name": run.data.tags.get("dspy_program_name", "unknown"),
                "timestamp": datetime.fromtimestamp(run.info.start_time / 1000),
                "contributor_id": run.data.tags.get("contributor_id"),
                "contributor_address": run.data.tags.get("contributor_address"),
                "outcome_score": run.data.metrics.get("outcome_score", 0.0),
            }

            # Try to load trace artifacts
            try:
                # Download trace data
                trace_path = self.client.download_artifacts(run.info.run_id, "dspy_trace.json")

                with open(trace_path) as f:
                    trace_data = json.load(f)

                trace["inputs"] = trace_data.get("inputs", {})
                trace["outputs"] = trace_data.get("outputs", {})
                trace["metadata"] = trace_data.get("metadata", {})

            except Exception as e:
                logger.debug(f"Could not load trace artifacts for {run.info.run_id}: {e}")

                # Fall back to tags/params
                trace["inputs"] = {
                    k.replace("input.", ""): v
                    for k, v in run.data.params.items()
                    if k.startswith("input.")
                }
                trace["outputs"] = {
                    k.replace("output.", ""): v
                    for k, v in run.data.params.items()
                    if k.startswith("output.")
                }

            # Add additional metrics
            for metric_name, metric_value in run.data.metrics.items():
                if metric_name != "outcome_score":
                    trace[f"metric_{metric_name}"] = metric_value

            return trace

        except Exception as e:
            logger.error(f"Error extracting trace from run {run.info.run_id}: {e}")
            return None

    def _parse_inputs_outputs(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Parse inputs and outputs from MLflow params.

        Args:
            params: MLflow run params

        Returns:
            Tuple of (inputs, outputs) dictionaries

        """
        inputs = {}
        outputs = {}

        for key, value in params.items():
            if key.startswith("input."):
                inputs[key.replace("input.", "")] = value
            elif key.startswith("output."):
                outputs[key.replace("output.", "")] = value

        return inputs, outputs
