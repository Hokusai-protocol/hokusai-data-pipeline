"""MLFlow configuration and utilities for the Hokusai pipeline."""

import logging
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

import mlflow

logger = logging.getLogger(__name__)


class MLFlowConfig:
    """Configuration manager for MLFlow tracking."""

    def __init__(self) -> None:
        self.tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "file:./mlruns")
        self.experiment_name = os.getenv("MLFLOW_EXPERIMENT_NAME", "hokusai-pipeline")
        self.artifact_root = os.getenv("MLFLOW_ARTIFACT_ROOT", None)

    def setup_tracking(self) -> None:
        """Initialize MLFlow tracking configuration."""
        try:
            mlflow.set_tracking_uri(self.tracking_uri)
            logger.info(f"MLFlow tracking URI set to: {self.tracking_uri}")

            # Create or get experiment
            experiment = mlflow.get_experiment_by_name(self.experiment_name)
            if experiment is None:
                experiment_id = mlflow.create_experiment(
                    name=self.experiment_name, artifact_location=self.artifact_root
                )
                logger.info(
                    f"Created MLFlow experiment: {self.experiment_name} (ID: {experiment_id})"
                )
            else:
                experiment_id = experiment.experiment_id
                logger.info(
                    f"Using existing MLFlow experiment: {self.experiment_name} (ID: {experiment_id})"
                )

            mlflow.set_experiment(self.experiment_name)

        except Exception as e:
            logger.error(f"Failed to setup MLFlow tracking: {e}")
            raise

    def validate_connection(self) -> bool:
        """Validate MLFlow tracking server connection."""
        try:
            # Try to get the current experiment
            experiment = mlflow.get_experiment_by_name(self.experiment_name)
            if experiment is not None:
                logger.info("MLFlow connection validated successfully")
                return True
            else:
                logger.warning("MLFlow experiment not found, but connection successful")
                return True
        except Exception as e:
            logger.error(f"MLFlow connection validation failed: {e}")
            return False


def generate_run_name(step_name: str, timestamp: Optional[str] = None) -> str:
    """Generate a consistent run name for pipeline steps."""
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"hokusai_{step_name}_{timestamp}"


def log_pipeline_metadata(run_id: str, step_name: str, metaflow_run_id: str) -> None:
    """Log standard pipeline metadata for tracking."""
    mlflow.set_tag("pipeline.step", step_name)
    mlflow.set_tag("pipeline.run_id", run_id)
    mlflow.set_tag("metaflow.run_id", metaflow_run_id)
    mlflow.set_tag("pipeline.timestamp", datetime.now().isoformat())


@contextmanager
def mlflow_run_context(
    run_name: str = None, experiment_name: str = None, tags: dict[str, str] = None, **kwargs
):
    """Context manager for MLFlow runs with automatic cleanup."""
    try:
        # Set up experiment if provided
        if experiment_name:
            try:
                mlflow.set_experiment(experiment_name)
            except Exception as e:
                logger.warning(f"Could not set experiment {experiment_name}: {e}")

        with mlflow.start_run(run_name=run_name) as run:
            try:
                # Log tags if provided
                if tags:
                    for key, value in tags.items():
                        mlflow.set_tag(key, value)

                logger.info(f"Started MLFlow run: {run_name or 'unnamed'} (ID: {run.info.run_id})")
                yield run
            except Exception as e:
                mlflow.set_tag("error", str(e))
                logger.error(f"Error in MLFlow run {run_name or 'unnamed'}: {e}")
                raise
            finally:
                logger.info(f"Completed MLFlow run: {run_name or 'unnamed'}")
    except Exception as e:
        logger.error(f"Failed to start MLFlow run: {e}")
        # Yield a dummy context to allow pipeline to continue
        yield None


def log_step_parameters(params: dict[str, Any]) -> None:
    """Log parameters for a pipeline step."""
    for key, value in params.items():
        try:
            mlflow.log_param(key, value)
        except Exception as e:
            logger.warning(f"Failed to log parameter {key}: {e}")


def log_step_metrics(metrics: dict[str, float]) -> None:
    """Log metrics for a pipeline step."""
    for key, value in metrics.items():
        try:
            mlflow.log_metric(key, value)
        except Exception as e:
            logger.warning(f"Failed to log metric {key}: {e}")


def log_model_artifact(model_path: str, artifact_name: str) -> None:
    """Log a model artifact to MLFlow."""
    try:
        mlflow.log_artifact(model_path, artifact_name)
        logger.info(f"Logged model artifact: {artifact_name}")
    except Exception as e:
        logger.error(f"Failed to log model artifact {artifact_name}: {e}")


def log_dataset_info(
    dataset_path: str, dataset_hash: str, row_count: int, feature_count: int
) -> None:
    """Log dataset information and metadata."""
    try:
        mlflow.log_param("dataset.path", dataset_path)
        mlflow.log_param("dataset.hash", dataset_hash)
        mlflow.log_metric("dataset.rows", row_count)
        mlflow.log_metric("dataset.features", feature_count)
        logger.info(f"Logged dataset info: {row_count} rows, {feature_count} features")
    except Exception as e:
        logger.error(f"Failed to log dataset info: {e}")
