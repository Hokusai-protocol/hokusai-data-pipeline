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
    """Enhanced circuit breaker for MLflow operations with auto-reset and monitoring."""
    
    def __init__(self, failure_threshold: int = None, recovery_timeout: int = None, max_recovery_attempts: int = None):
        # Use environment variables or improved defaults
        self.failure_threshold = failure_threshold or int(os.getenv("MLFLOW_CB_FAILURE_THRESHOLD", "5"))
        self.recovery_timeout = recovery_timeout or int(os.getenv("MLFLOW_CB_RECOVERY_TIMEOUT", "60"))
        self.max_recovery_attempts = max_recovery_attempts or int(os.getenv("MLFLOW_CB_MAX_RECOVERY_ATTEMPTS", "5"))
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.recovery_attempts = 0
        self.last_success_time = time.time()
        self.consecutive_successes = 0
        
    def is_open(self) -> bool:
        """Check if circuit breaker is open (blocking requests)."""
        if self.state == "OPEN":
            if self.last_failure_time and \
               (time.time() - self.last_failure_time) > self.recovery_timeout:
                if self.recovery_attempts < self.max_recovery_attempts:
                    self.state = "HALF_OPEN"
                    self.recovery_attempts += 1
                    logger.info(f"Circuit breaker moving to HALF_OPEN state (attempt {self.recovery_attempts}/{self.max_recovery_attempts})")
                    return False
                else:
                    # Extend timeout exponentially after max attempts
                    extended_timeout = self.recovery_timeout * (2 ** (self.recovery_attempts - self.max_recovery_attempts))
                    if (time.time() - self.last_failure_time) > extended_timeout:
                        self.state = "HALF_OPEN"
                        logger.info(f"Circuit breaker moving to HALF_OPEN state after extended timeout ({extended_timeout}s)")
                        return False
            return True
        return False
        
    def record_success(self):
        """Record successful operation with recovery logic."""
        previous_state = self.state
        self.consecutive_successes += 1
        self.last_success_time = time.time()
        
        if self.state == "HALF_OPEN":
            # Require multiple successes to fully close circuit breaker
            if self.consecutive_successes >= 2:
                self.failure_count = 0
                self.state = "CLOSED"
                self.recovery_attempts = 0
                logger.info("Circuit breaker CLOSED: Service fully recovered")
            else:
                logger.info(f"Circuit breaker HALF_OPEN: {self.consecutive_successes}/2 successes for full recovery")
        elif self.state == "CLOSED":
            # Gradually reduce failure count on sustained success
            if self.failure_count > 0:
                self.failure_count = max(0, self.failure_count - 1)
        
        if previous_state != "CLOSED" and self.state == "CLOSED":
            logger.info("MLflow service fully recovered and circuit breaker closed")
        
    def record_failure(self):
        """Record failed operation with enhanced tracking."""
        previous_state = self.state
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.consecutive_successes = 0
        
        if self.state == "HALF_OPEN":
            # Immediate return to OPEN state on any failure during recovery
            self.state = "OPEN"
            logger.warning(f"Circuit breaker back to OPEN: Failure during recovery (attempt {self.recovery_attempts})")
        elif self.state == "CLOSED" and self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker OPEN: {self.failure_count} consecutive failures")
            
    def get_status(self) -> dict:
        """Get detailed circuit breaker status for monitoring."""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "consecutive_successes": self.consecutive_successes,
            "recovery_attempts": self.recovery_attempts,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "time_since_last_failure": time.time() - self.last_failure_time if self.last_failure_time else None,
            "time_until_retry": max(0, self.recovery_timeout - (time.time() - self.last_failure_time)) if self.last_failure_time and self.state == "OPEN" else 0,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout
        }
        
    def force_reset(self):
        """Force reset circuit breaker to closed state (for manual recovery)."""
        logger.info("Circuit breaker manually reset to CLOSED state")
        self.state = "CLOSED"
        self.failure_count = 0
        self.recovery_attempts = 0
        self.consecutive_successes = 0
        self.last_failure_time = None


# Global circuit breaker instance with configurable parameters (increased defaults for stability)
_circuit_breaker = MLflowCircuitBreaker(
    failure_threshold=int(os.getenv("MLFLOW_CB_FAILURE_THRESHOLD", "5")),  # Increased from 3 to 5
    recovery_timeout=int(os.getenv("MLFLOW_CB_RECOVERY_TIMEOUT", "60")),    # Increased from 30 to 60 seconds
    max_recovery_attempts=int(os.getenv("MLFLOW_CB_MAX_RECOVERY_ATTEMPTS", "5"))  # Increased from 3 to 5
)


def exponential_backoff_retry(func, max_retries: int = None, base_delay: float = None):
    """Retry function with exponential backoff."""
    max_retries = max_retries or int(os.getenv("MLFLOW_MAX_RETRIES", "3"))
    base_delay = base_delay or float(os.getenv("MLFLOW_BASE_DELAY", "2.0"))
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
        self.tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow.hokusai-development.local:5000")
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
    
    def __init__(self, message: str, retry_after: float = None):
        super().__init__(message)
        self.retry_after = retry_after
        
        
def reset_circuit_breaker():
    """Manually reset the circuit breaker (for recovery scripts)."""
    global _circuit_breaker
    _circuit_breaker.force_reset()
    logger.info("MLflow circuit breaker has been manually reset")
    
    
def get_circuit_breaker_status() -> dict:
    """Get detailed circuit breaker status for diagnostics."""
    return _circuit_breaker.get_status()


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
    """Get current MLflow connection status and enhanced circuit breaker state with configurable timeout."""
    # Import settings to get configurable timeout
    try:
        from src.api.utils.config import get_settings
        settings = get_settings()
        connection_timeout = settings.health_check_timeout
    except ImportError:
        # Fallback if settings not available
        connection_timeout = 10.0
    
    cb_status = _circuit_breaker.get_status()
    
    status = {
        "circuit_breaker_state": cb_status["state"],
        "circuit_breaker_details": cb_status,
        "connected": False,
        "tracking_uri": os.getenv("MLFLOW_TRACKING_URI", "http://mlflow.hokusai-development.local:5000"),
        "connection_timeout": connection_timeout,
        "error": None,
        "last_check_time": datetime.now().isoformat()
    }
    
    if _circuit_breaker.is_open():
        status["error"] = f"Circuit breaker is OPEN - MLflow unavailable (retry in {cb_status['time_until_retry']:.0f}s)"
        status["can_retry_in_seconds"] = cb_status["time_until_retry"]
        _update_metrics(status)
        return status
    
    try:
        # Connection test with configurable timeout and enhanced error handling
        start_time = time.time()
        
        # Set MLflow tracking URI with timeout consideration
        mlflow.set_tracking_uri(status["tracking_uri"])
        
        # Test basic connectivity with timeout wrapper
        def _test_connection():
            # Test basic connectivity
            mlflow.get_experiment_by_name("default")
            
            # Test if we can create/access an experiment (more comprehensive check)
            test_experiment = "health-check-test"
            try:
                mlflow.get_experiment_by_name(test_experiment)
            except:
                # Experiment doesn't exist, that's fine
                pass
        
        # Use retry logic with timeout (increased retries for better stability)
        exponential_backoff_retry(_test_connection, max_retries=3, base_delay=1.0)
            
        response_time = (time.time() - start_time) * 1000
        status["connected"] = True
        status["response_time_ms"] = response_time
        
        # Use configurable timeout for warning threshold
        warning_threshold = connection_timeout * 1000  # Convert to milliseconds
        if response_time > warning_threshold:
            status["warning"] = f"Slow response time: {response_time:.0f}ms (threshold: {warning_threshold:.0f}ms)"
            logger.warning(f"MLflow slow response: {response_time:.0f}ms (threshold: {warning_threshold:.0f}ms)")
        
        _circuit_breaker.record_success()
        
    except Exception as e:
        status["error"] = str(e)
        status["error_type"] = type(e).__name__
        status["connection_attempts"] = 2  # Number of retry attempts made
        _circuit_breaker.record_failure()
        logger.error(f"MLflow connection failed after retries: {e}", extra={
            "tracking_uri": status["tracking_uri"],
            "timeout": connection_timeout,
            "circuit_breaker_state": cb_status["state"]
        })
    
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
