"""Experiment orchestration service for model improvement experiments."""

import logging
import os
from typing import Any, Dict, List, Optional

import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score

logger = logging.getLogger(__name__)


class ExperimentManager:
    """Manage experiments for testing model improvements.

    This service provides:
    - Experiment creation for improvement testing
    - Standardized model comparison
    - Experiment tracking and history
    - Recommendation generation
    """

    VALID_METRICS = ["accuracy", "auroc", "f1_score", "precision", "recall"]

    def __init__(self, experiment_name: str = "hokusai_model_improvements",
                 mlflow_tracking_uri: Optional[str] = None,
                 registry: Optional[Any] = None) -> None:
        """Initialize the experiment manager.

        Args:
            experiment_name: Name of the MLFlow experiment OR ModelRegistry instance (for backward compatibility)
            mlflow_tracking_uri: Optional MLflow tracking URI (defaults to env var or registry.hokus.ai/mlflow)
            registry: Optional ModelRegistry instance (for backward compatibility)

        Note:
            For backward compatibility, you can pass a registry as the first parameter:
            - ExperimentManager(registry) - registry as first parameter
            - ExperimentManager(experiment_name='my_exp', registry=registry) - named parameters
            - ExperimentManager('my_exp', registry=registry) - mixed parameters

        """
        # Handle backward compatibility: if first parameter is not a string, assume it's a registry
        if not isinstance(experiment_name, str):
            # Check if it's a registry-like object (has methods/attributes that suggest it's a registry)
            if (hasattr(experiment_name, "__class__") and
                experiment_name is not None and
                not isinstance(experiment_name, (int, float, bool, list, dict, tuple)) and
                hasattr(experiment_name, "__dict__")):
                # First parameter is likely a registry object
                registry = experiment_name
                experiment_name = "hokusai_model_improvements"  # Use default experiment name
            else:
                raise ValueError(
                    "First parameter must be either a string (experiment_name) or a registry object. "
                    f"Got: {type(experiment_name)}"
                )

        # Configure MLflow tracking URI
        if mlflow_tracking_uri:
            self.tracking_uri = mlflow_tracking_uri
        elif registry and hasattr(registry, "tracking_uri"):
            self.tracking_uri = registry.tracking_uri
        else:
            # Use environment variable or default to registry.hokus.ai
            self.tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://registry.hokus.ai/mlflow")

        # Set tracking URI before any MLflow operations
        mlflow.set_tracking_uri(self.tracking_uri)
        logger.info(f"MLflow tracking URI set to: {self.tracking_uri}")

        # Note: MLflow access requires a valid Hokusai API key
        # Set via HOKUSAI_API_KEY environment variable or API key configuration

        self.experiment_name = experiment_name
        self.registry = registry

        # Check if mock mode is enabled
        self.mock_mode = os.getenv("HOKUSAI_MOCK_MODE", "false").lower() == "true"
        
        # Optional MLflow mode - automatically enable mock mode if MLflow is unavailable
        self.optional_mlflow = os.getenv("HOKUSAI_OPTIONAL_MLFLOW", "true").lower() == "true"

        if not self.mock_mode:
            try:
                # Try to configure MLflow authentication if available
                try:
                    from ..config import setup_mlflow_auth
                    setup_mlflow_auth(tracking_uri=self.tracking_uri, validate=False)
                except ImportError:
                    pass  # Config module not available
                
                self._ensure_experiment_exists()
                mlflow.set_experiment(experiment_name)
                logger.info(f"Initialized ExperimentManager with experiment: {experiment_name}")
            except Exception as e:
                if self.optional_mlflow:
                    logger.warning(f"Failed to connect to MLflow server: {str(e)}")
                    logger.warning("Switching to mock mode - MLflow operations will be simulated")
                    self.mock_mode = True
                else:
                    logger.error(f"Failed to connect to MLflow server: {str(e)}")
                    logger.info("Consider setting HOKUSAI_MOCK_MODE=true or HOKUSAI_OPTIONAL_MLFLOW=true")
                    raise
        
        if self.mock_mode:
            logger.info("Running in mock mode - MLflow operations will be simulated")

    def start_experiment(self, experiment_name: str) -> Any:
        """Start an experiment context (for backward compatibility).
        
        Args:
            experiment_name: Name of the experiment
            
        Returns:
            Context manager for the experiment

        """
        if self.mock_mode:
            # Return a mock context manager
            class MockExperiment:
                def __enter__(self):
                    logger.info(f"Mock: Starting experiment {experiment_name}")
                    return self
                def __exit__(self, *args):
                    logger.info(f"Mock: Ending experiment {experiment_name}")
                    # args contains (exc_type, exc_value, traceback) but we don't need them for mocking
            return MockExperiment()
        else:
            # Set the experiment and return MLflow run context
            mlflow.set_experiment(experiment_name)
            return mlflow.start_run()

    def create_improvement_experiment(self, baseline_model_id: str, contributed_data: Any) -> str:
        """Create a new experiment for testing improvements.

        Args:
            baseline_model_id: ID of the baseline model
            contributed_data: Data contributed for improvement

        Returns:
            Experiment run ID

        """
        if self.mock_mode:
            import uuid
            mock_run_id = str(uuid.uuid4())
            logger.info(f"Mock: Created improvement experiment with ID: {mock_run_id}")
            return mock_run_id

        try:
            with mlflow.start_run() as run:
                # Log experiment metadata
                mlflow.log_params(
                    {
                        "baseline_model_id": baseline_model_id,
                        "contributed_data_hash": contributed_data.get("metadata", {}).get(
                            "dataset_hash", "unknown"
                        ),
                        "contributed_data_size": str(len(contributed_data.get("features", []))),
                        "experiment_type": "model_improvement",
                        "created_at": pd.Timestamp.now().isoformat(),
                    }
                )

                # Set experiment tags
                mlflow.set_tag("experiment_type", "model_improvement")
                mlflow.set_tag("baseline_model", baseline_model_id)

                if "metadata" in contributed_data:
                    mlflow.set_tag(
                        "contributor_id",
                        contributed_data["metadata"].get("contributor_id", "unknown"),
                    )

                experiment_id = run.info.run_id
                logger.info(f"Created improvement experiment: {experiment_id}")

                return experiment_id

        except Exception as e:
            logger.error(f"Failed to create improvement experiment: {str(e)}")
            raise

    def compare_models(
        self, baseline_id: str, candidate_id: str, test_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Perform standardized comparison between baseline and candidate models.

        Args:
            baseline_id: Baseline model ID
            candidate_id: Candidate model ID
            test_data: Test dataset for comparison

        Returns:
            Comparison results with metrics and recommendation

        """
        if self.mock_mode:
            # Return mock comparison results
            mock_baseline_metrics = {
                "accuracy": 0.85,
                "auroc": 0.88,
                "f1_score": 0.84,
                "precision": 0.86,
                "recall": 0.83
            }
            mock_candidate_metrics = {
                "accuracy": 0.87,
                "auroc": 0.90,
                "f1_score": 0.86,
                "precision": 0.88,
                "recall": 0.85
            }
            improvements = {k: mock_candidate_metrics[k] - mock_baseline_metrics[k]
                          for k in mock_baseline_metrics}

            logger.info("Mock: Performed model comparison")
            return {
                "baseline_metrics": mock_baseline_metrics,
                "candidate_metrics": mock_candidate_metrics,
                "improvements": improvements,
                "recommendation": "ACCEPT",
                "test_dataset": test_data.get("dataset_name", "mock_dataset")
            }

        try:
            with mlflow.start_run():
                # Load models
                baseline_model = mlflow.pyfunc.load_model(f"models:/{baseline_id}")
                candidate_model = mlflow.pyfunc.load_model(f"models:/{candidate_id}")

                # Get test features and labels
                X_test = test_data["features"]
                y_test = test_data["labels"]

                # Get predictions
                baseline_preds = baseline_model.predict(X_test)
                candidate_preds = candidate_model.predict(X_test)

                # Calculate metrics for both models
                baseline_metrics = self._calculate_metrics(y_test, baseline_preds)
                candidate_metrics = self._calculate_metrics(y_test, candidate_preds)

                # Calculate improvements
                improvements = {}
                for metric in baseline_metrics:
                    improvements[metric] = candidate_metrics[metric] - baseline_metrics[metric]

                # Log comparison results
                self._log_comparison_results(baseline_metrics, candidate_metrics, improvements)

                # Generate recommendation
                recommendation = self._determine_recommendation(improvements)

                comparison_result = {
                    "baseline_metrics": baseline_metrics,
                    "candidate_metrics": candidate_metrics,
                    "improvements": improvements,
                    "recommendation": recommendation,
                    "test_dataset": test_data.get("dataset_name", "unknown"),
                }

                logger.info(f"Model comparison complete. Recommendation: {recommendation}")

                return comparison_result

        except Exception as e:
            logger.error(f"Failed to compare models: {str(e)}")
            raise

    def get_experiment_history(
        self, baseline_model_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get history of experiments for a baseline model.

        Args:
            baseline_model_id: Optional filter by baseline model

        Returns:
            List of experiment summaries

        """
        try:
            # Search for runs in the experiment
            filter_string = ""
            if baseline_model_id:
                filter_string = f"params.baseline_model_id = '{baseline_model_id}'"

            runs = mlflow.search_runs(
                experiment_names=[self.experiment_name],
                filter_string=filter_string,
                order_by=["start_time DESC"],
            )

            history = []
            for _, run in runs.iterrows():
                summary = {
                    "run_id": run["run_id"],
                    "baseline_model": run.get("params.baseline_model_id"),
                    "improvement": run.get("metrics.accuracy_improvement", 0),
                    "recommendation": run.get("tags.recommendation", "unknown"),
                    "timestamp": run["start_time"],
                }
                history.append(summary)

            return history

        except Exception as e:
            logger.error(f"Failed to get experiment history: {str(e)}")
            raise

    def _calculate_metrics(
        self, y_true: np.ndarray, y_pred: np.ndarray, threshold: float = 0.5
    ) -> Dict[str, float]:
        """Calculate standard metrics for model evaluation.

        Args:
            y_true: True labels
            y_pred: Predicted probabilities or labels
            threshold: Threshold for binary classification

        Returns:
            Dictionary of calculated metrics

        """
        # Convert probabilities to binary predictions if needed
        if y_pred.dtype == float and y_pred.max() <= 1.0:
            y_pred_binary = (y_pred >= threshold).astype(int)
        else:
            y_pred_binary = y_pred

        metrics = {}

        # Calculate metrics safely
        try:
            metrics["accuracy"] = accuracy_score(y_true, y_pred_binary)
        except:
            metrics["accuracy"] = 0.0

        try:
            # AUROC requires probability scores
            if y_pred.dtype == float:
                metrics["auroc"] = roc_auc_score(y_true, y_pred)
            else:
                metrics["auroc"] = 0.0
        except:
            metrics["auroc"] = 0.0

        try:
            metrics["f1_score"] = f1_score(y_true, y_pred_binary, average="weighted")
        except:
            metrics["f1_score"] = 0.0

        try:
            metrics["precision"] = precision_score(y_true, y_pred_binary, average="weighted")
        except:
            metrics["precision"] = 0.0

        try:
            metrics["recall"] = recall_score(y_true, y_pred_binary, average="weighted")
        except:
            metrics["recall"] = 0.0

        return metrics

    def _determine_recommendation(
        self, improvements: Dict[str, float], threshold: float = 0.01
    ) -> str:
        """Determine recommendation based on improvements.

        Args:
            improvements: Metric improvements
            threshold: Minimum improvement threshold

        Returns:
            Recommendation: ACCEPT, REJECT, or REVIEW

        """
        # Count significant improvements
        significant_improvements = sum(1 for v in improvements.values() if v > threshold)

        # Count regressions
        regressions = sum(1 for v in improvements.values() if v < -threshold)

        if regressions > 0:
            return "REJECT"
        elif significant_improvements >= 2:
            return "ACCEPT"
        elif significant_improvements >= 1:
            return "REVIEW"
        else:
            return "REJECT"

    def _log_comparison_results(
        self,
        baseline_metrics: Dict[str, float],
        candidate_metrics: Dict[str, float],
        improvements: Dict[str, float],
    ) -> None:
        """Log model comparison results to MLFlow.

        Args:
            baseline_metrics: Baseline model metrics
            candidate_metrics: Candidate model metrics
            improvements: Calculated improvements

        """
        # Log baseline metrics
        for metric, value in baseline_metrics.items():
            mlflow.log_metric(f"baseline_{metric}", value)

        # Log candidate metrics
        for metric, value in candidate_metrics.items():
            mlflow.log_metric(f"candidate_{metric}", value)

        # Log improvements
        for metric, value in improvements.items():
            mlflow.log_metric(f"{metric}_improvement", value)

    def _validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate experiment configuration.

        Args:
            config: Experiment configuration

        Returns:
            True if valid

        Raises:
            ValueError: If configuration is invalid

        """
        if "test_size" in config:
            if not 0 < config["test_size"] < 1:
                raise ValueError("test_size must be between 0 and 1")

        if "metrics" in config:
            for metric in config["metrics"]:
                if metric not in self.VALID_METRICS:
                    raise ValueError(f"Invalid metric: {metric}")

        return True

    def _log_artifacts(self, artifacts: Dict[str, str]) -> None:
        """Log experiment artifacts.

        Args:
            artifacts: Dictionary of artifact name to file path

        """
        for name, path in artifacts.items():
            try:
                mlflow.log_artifact(path)
                logger.info(f"Logged artifact: {name}")
            except Exception as e:
                logger.error(f"Failed to log artifact {name}: {str(e)}")

    def _format_report(self, comparison_result: Dict[str, Any]) -> str:
        """Format comparison results as a readable report.

        Args:
            comparison_result: Model comparison results

        Returns:
            Formatted report string

        """
        report = ["Model Comparison Report", "=" * 50, ""]

        # Baseline metrics
        report.append("Baseline Model Metrics:")
        for metric, value in comparison_result["baseline_metrics"].items():
            report.append(f"  {metric}: {value:.4f}")

        report.append("")

        # Candidate metrics
        report.append("Candidate Model Metrics:")
        for metric, value in comparison_result["candidate_metrics"].items():
            report.append(f"  {metric}: {value:.4f}")

        report.append("")

        # Improvements
        report.append("Improvements:")
        for metric, value in comparison_result["improvements"].items():
            sign = "+" if value > 0 else ""
            report.append(f"  {metric}: {sign}{value:.4f}")

        report.append("")
        report.append(f"Recommendation: {comparison_result['recommendation']}")

        return "\n".join(report)

    def _ensure_experiment_exists(self) -> None:
        """Ensure the MLFlow experiment exists."""
        import time
        max_retries = 3
        retry_delay = 1.0

        for attempt in range(max_retries):
            try:
                experiment = mlflow.get_experiment_by_name(self.experiment_name)
                if experiment is None:
                    mlflow.create_experiment(self.experiment_name)
                    logger.info(f"Created new experiment: {self.experiment_name}")
                return
            except Exception as e:
                if "403" in str(e):
                    logger.error(f"MLflow authentication error (HTTP 403): {str(e)}")
                    logger.error(f"MLflow tracking URI: {self.tracking_uri}")
                    logger.error("\nPossible solutions:")
                    logger.error("1. Set HOKUSAI_MOCK_MODE=true for local development without MLflow")
                    logger.error("2. Configure MLflow authentication:")
                    logger.error("   - Basic auth: MLFLOW_TRACKING_USERNAME and MLFLOW_TRACKING_PASSWORD")
                    logger.error("   - Token auth: MLFLOW_TRACKING_TOKEN")
                    logger.error("   - AWS auth: MLFLOW_TRACKING_AWS_SIGV4=true")
                    logger.error("3. Check if MLflow server requires authentication")
                    raise
                elif "401" in str(e):
                    logger.error(f"MLflow authentication error (HTTP 401): {str(e)}")
                    logger.error("Invalid or missing credentials for MLflow server")
                    logger.error("Please check your authentication configuration")
                    raise
                elif attempt < max_retries - 1:
                    logger.warning(f"Failed to connect to MLflow (attempt {attempt + 1}/{max_retries}): {str(e)}")
                    time.sleep(retry_delay * (attempt + 1))
                else:
                    logger.error(f"Failed to ensure experiment exists after {max_retries} attempts: {str(e)}")
                    raise
