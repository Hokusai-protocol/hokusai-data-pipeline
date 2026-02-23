"""Module for model evaluation."""

from __future__ import annotations

from contextlib import nullcontext
from numbers import Real
from typing import Any, Callable

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from sklearn.metrics import (  # type: ignore[import-untyped]
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


class ModelEvaluator:
    """Handles model evaluation on benchmark datasets."""

    def __init__(self: ModelEvaluator, metrics: list[str] | None = None) -> None:
        self.metrics = metrics or ["accuracy", "precision", "recall", "f1", "auroc"]

    @staticmethod
    def _load_mlflow_evaluation() -> tuple[Any, Callable[..., Any]]:
        """Load MLflow evaluation dependencies lazily."""
        # MLflow SDK reads Authorization via MLFLOW_TRACKING_TOKEN/environment configuration.
        try:
            import mlflow  # type: ignore
            from mlflow.metrics import make_metric  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "mlflow is required for model evaluation. Install the mlflow extra/dependency."
            ) from exc
        return mlflow, make_metric

    @staticmethod
    def _compute_accuracy(predictions: pd.Series, targets: pd.Series, **_: Any) -> float:
        return float(accuracy_score(targets, predictions))

    @staticmethod
    def _compute_precision(predictions: pd.Series, targets: pd.Series, **_: Any) -> float:
        return float(precision_score(targets, predictions, average="weighted", zero_division=0))

    @staticmethod
    def _compute_recall(predictions: pd.Series, targets: pd.Series, **_: Any) -> float:
        return float(recall_score(targets, predictions, average="weighted", zero_division=0))

    @staticmethod
    def _compute_f1(predictions: pd.Series, targets: pd.Series, **_: Any) -> float:
        return float(f1_score(targets, predictions, average="weighted", zero_division=0))

    @staticmethod
    def _compute_auroc(predictions: pd.Series, targets: pd.Series, **kwargs: Any) -> float:
        # MLflow passes probabilities in evaluator-specific kwargs when available.
        predicted_probabilities = kwargs.get("predicted_probabilities")
        if predicted_probabilities is None:
            return float("nan")

        proba_array = np.asarray(predicted_probabilities)
        if proba_array.ndim == 2 and proba_array.shape[1] == 2:
            proba_values: Any = proba_array[:, 1]
        else:
            proba_values = proba_array

        try:
            return float(
                roc_auc_score(targets, proba_values, average="weighted", multi_class="ovr")
            )
        except ValueError:
            return float("nan")

    def _create_extra_metrics(self: ModelEvaluator, make_metric: Callable[..., Any]) -> list[Any]:
        metric_definitions: dict[str, Callable[..., float]] = {
            "accuracy": self._compute_accuracy,
            "precision": self._compute_precision,
            "recall": self._compute_recall,
            "f1": self._compute_f1,
            "auroc": self._compute_auroc,
        }

        extra_metrics: list[Any] = []
        for metric_name in self.metrics:
            metric_fn = metric_definitions.get(metric_name)
            if metric_fn is None:
                continue

            extra_metrics.append(
                make_metric(eval_fn=metric_fn, greater_is_better=True, name=metric_name)
            )

        return extra_metrics

    @staticmethod
    def _normalize_metric_value(metric_value: Any) -> float | None:
        if isinstance(metric_value, Real):
            value = float(metric_value)
            if np.isnan(value):
                return None
            return value

        if hasattr(metric_value, "aggregate_results") and isinstance(
            metric_value.aggregate_results, dict
        ):
            score = metric_value.aggregate_results.get("score")
            if isinstance(score, Real):
                value = float(score)
                if np.isnan(value):
                    return None
                return value

        return None

    def evaluate_mock_model(
        self: ModelEvaluator, model: dict[str, Any], X_test: pd.DataFrame, y_test: pd.Series
    ) -> dict[str, float]:
        """Evaluate a mock model."""
        _ = (X_test, y_test)

        # For mock models, return the stored metrics with slight variation
        base_metrics = model.get("metrics", {})

        # Add slight random variation to simulate test set performance
        evaluated_metrics = {}
        for metric in self.metrics:
            if metric in base_metrics:
                # Add small random variation (-2% to +2%)
                variation = np.random.uniform(-0.02, 0.02)
                evaluated_metrics[metric] = max(0, min(1, base_metrics[metric] + variation))
            else:
                evaluated_metrics[metric] = np.random.uniform(0.7, 0.9)

        return evaluated_metrics

    def evaluate_sklearn_model(
        self: ModelEvaluator,
        model: Any,
        X_test: pd.DataFrame,
        y_test: pd.Series,
        threshold: float = 0.5,
    ) -> dict[str, float | None]:
        """Evaluate a scikit-learn model through `mlflow.evaluate()`."""
        _ = threshold

        mlflow, make_metric = self._load_mlflow_evaluation()
        extra_metrics = self._create_extra_metrics(make_metric)

        run_context = nullcontext()
        if mlflow.active_run() is None:
            run_context = mlflow.start_run()

        with run_context:
            results = mlflow.evaluate(
                model=model,
                data=X_test,
                targets=y_test,
                model_type="classifier",
                extra_metrics=extra_metrics,
            )

        raw_metrics = getattr(results, "metrics", {}) or {}
        metrics: dict[str, float | None] = {}

        for metric_name in self.metrics:
            value = self._normalize_metric_value(raw_metrics.get(metric_name))
            if value is None and metric_name == "auroc":
                metrics[metric_name] = None
                continue
            if value is not None:
                metrics[metric_name] = value

        return metrics

    def evaluate_model(
        self: ModelEvaluator, model: Any, X_test: pd.DataFrame, y_test: pd.Series
    ) -> dict[str, Any]:
        """Evaluate any supported model type."""
        metrics: dict[str, Any]
        # Check if mock model
        if isinstance(model, dict) and model.get("type", "").startswith("mock"):
            metrics = self.evaluate_mock_model(model, X_test, y_test)
        else:
            metrics = self.evaluate_sklearn_model(model, X_test, y_test)

        return {
            "metrics": metrics,
            "test_samples": len(X_test),
            "model_type": type(model).__name__
            if not isinstance(model, dict)
            else model.get("type"),
        }

    def compare_models(
        self: ModelEvaluator, baseline_metrics: dict[str, float], new_metrics: dict[str, float]
    ) -> dict[str, dict[str, float]]:
        """Compare two models' metric dictionaries."""
        comparison = {}

        for metric in self.metrics:
            if metric in baseline_metrics and metric in new_metrics:
                baseline_val = baseline_metrics[metric]
                new_val = new_metrics[metric]

                comparison[metric] = {
                    "baseline": baseline_val,
                    "new": new_val,
                    "absolute_delta": new_val - baseline_val,
                    "relative_delta": ((new_val - baseline_val) / baseline_val * 100)
                    if baseline_val > 0
                    else 0,
                    "improved": new_val > baseline_val,
                }

        return comparison

    def calculate_delta_score(
        self: ModelEvaluator,
        comparison: dict[str, dict[str, float]],
        weights: dict[str, float] | None = None,
    ) -> float:
        """Calculate the weighted overall delta score."""
        if not weights:
            # Default equal weights
            weights = dict.fromkeys(comparison.keys(), 1.0)

        # Normalize weights
        total_weight = sum(weights.values())
        weights = {k: v / total_weight for k, v in weights.items()}

        # Calculate weighted delta
        delta_score = 0.0
        for metric, values in comparison.items():
            if metric in weights and values.get("absolute_delta") is not None:
                delta_score += weights[metric] * values["absolute_delta"]

        return delta_score

    def create_evaluation_report(
        self: ModelEvaluator,
        baseline_results: dict[str, Any],
        new_results: dict[str, Any],
        comparison: dict[str, dict[str, float]],
        delta_score: float,
    ) -> dict[str, Any]:
        """Create a comprehensive evaluation report."""
        return {
            "baseline_model": {
                "metrics": baseline_results["metrics"],
                "model_type": baseline_results["model_type"],
                "test_samples": baseline_results["test_samples"],
            },
            "new_model": {
                "metrics": new_results["metrics"],
                "model_type": new_results["model_type"],
                "test_samples": new_results["test_samples"],
            },
            "comparison": comparison,
            "delta_score": delta_score,
            "summary": {
                "improved_metrics": [m for m, v in comparison.items() if v.get("improved", False)],
                "degraded_metrics": [
                    m for m, v in comparison.items() if not v.get("improved", True)
                ],
                "overall_improvement": delta_score > 0,
            },
        }
