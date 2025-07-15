"""MLFlow configuration and utilities for the Hokusai pipeline."""

import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

import mlflow
from mlflow.exceptions import MlflowException

logger = logging.getLogger(__name__)


class MLflowCircuitBreaker:
    """Circuit breaker for MLflow operations to prevent cascading failures."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        
    def is_open(self) -> bool:
        """Check if circuit breaker is open (blocking requests)."""
        if self.state == "OPEN":
            if self.last_failure_time and \
               (time.time() - self.last_failure_time) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker moving to HALF_OPEN state")
                return False
            return True
        return False
        
    def record_success(self):
        """Record successful operation."""
        self.failure_count = 0
        self.state = "CLOSED"
        
    def record_failure(self):
        """Record failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker OPEN: {self.failure_count} failures")


# Global circuit breaker instance
_circuit_breaker = MLflowCircuitBreaker()


def exponential_backoff_retry(func, max_retries: int = 3, base_delay: float = 1.0):
    """Retry function with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            
            delay = base_delay * (2 ** attempt)
            logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)


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
        """Validate MLFlow tracking server connection with circuit breaker."""
        if _circuit_breaker.is_open():
            logger.warning("MLFlow circuit breaker is OPEN, skipping connection validation")
            return False
            
        def _validate():
            # Try to get the current experiment
            experiment = mlflow.get_experiment_by_name(self.experiment_name)
            if experiment is not None:
                logger.info("MLFlow connection validated successfully")
                return True
            else:
                logger.warning("MLFlow experiment not found, but connection successful")
                return True
                
        try:
            result = exponential_backoff_retry(_validate, max_retries=3, base_delay=1.0)
            _circuit_breaker.record_success()
            return result
        except Exception as e:
            _circuit_breaker.record_failure()
            logger.error(f"MLFlow connection validation failed after retries: {e}")
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


class MLflowUnavailableError(Exception):
    """Raised when MLflow is unavailable and circuit breaker is open."""
    pass


@contextmanager
def mlflow_run_context(
    run_name: str = None, experiment_name: str = None, tags: dict[str, str] = None
):
    """Context manager for MLFlow runs with circuit breaker protection."""
    
    # Check circuit breaker first
    if _circuit_breaker.is_open():
        error_msg = f"MLFlow circuit breaker is OPEN - run {run_name or 'unnamed'} cannot proceed"
        logger.error(error_msg)
        raise MLflowUnavailableError(error_msg)
    
    def _start_run():
        # Set up experiment if provided
        if experiment_name:
            mlflow.set_experiment(experiment_name)
        
        return mlflow.start_run(run_name=run_name)
    
    try:
        # Use retry logic for starting the run
        run = exponential_backoff_retry(_start_run, max_retries=3, base_delay=1.0)
        
        try:
            # Log tags if provided
            if tags:
                for key, value in tags.items():
                    mlflow.set_tag(key, value)

            logger.info(f"Started MLFlow run: {run_name or 'unnamed'} (ID: {run.info.run_id})")
            _circuit_breaker.record_success()
            yield run
            
        except Exception as e:
            # Error within the run context
            try:
                mlflow.set_tag("error", str(e))
            except:
                pass  # Don't fail if we can't set error tag
            logger.error(f"Error in MLFlow run {run_name or 'unnamed'}: {e}")
            raise
        finally:
            logger.info(f"Completed MLFlow run: {run_name or 'unnamed'}")
            
    except Exception as e:
        _circuit_breaker.record_failure()
        error_msg = f"Failed to start MLFlow run {run_name or 'unnamed'}: {e}"
        logger.error(error_msg)
        raise MLflowUnavailableError(error_msg) from e


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


def get_mlflow_status() -> dict:
    """Get current MLflow connection status and circuit breaker state."""
    status = {
        "circuit_breaker_state": _circuit_breaker.state,
        "failure_count": _circuit_breaker.failure_count,
        "last_failure_time": _circuit_breaker.last_failure_time,
        "connected": False,
        "tracking_uri": os.getenv("MLFLOW_TRACKING_URI", "file:./mlruns"),
        "error": None
    }
    
    if _circuit_breaker.is_open():
        status["error"] = "Circuit breaker is OPEN - MLflow unavailable"
        _update_metrics(status)
        return status
    
    try:
        # Quick connection test
        mlflow.get_experiment_by_name("default")
        status["connected"] = True
        _circuit_breaker.record_success()
    except Exception as e:
        status["error"] = str(e)
        _circuit_breaker.record_failure()
    
    _update_metrics(status)
    return status


def _update_metrics(status: dict):
    """Update Prometheus metrics with MLflow status."""
    try:
        from src.utils.prometheus_metrics import update_mlflow_metrics
        update_mlflow_metrics(status)
    except ImportError:
        # Prometheus metrics not available, skip
        pass
    except Exception as e:
        logger.debug(f"Error updating MLflow metrics: {e}")
