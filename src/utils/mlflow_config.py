"""MLFlow configuration and utilities for the Hokusai pipeline.

AUTHENTICATION: This module provides mTLS certificate-based authentication via
configure_internal_mtls() which sets MLFLOW_TRACKING_CLIENT_CERT_PATH environment variables.
"""

import asyncio
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

import mlflow

from src.utils.dns_resolver import DNSResolutionError, get_dns_resolver

logger = logging.getLogger(__name__)


async def resolve_tracking_uri(tracking_uri: str) -> str:
    """Resolve tracking URI using DNS resolver with fallback capabilities.

    Args:
    ----
        tracking_uri: MLFlow tracking URI (may contain hostname)

    Returns:
    -------
        Resolved tracking URI with IP address

    Raises:
    ------
        DNSResolutionError: If DNS resolution fails and no fallback available

    """
    try:
        dns_resolver = get_dns_resolver()
        resolved_uri = await dns_resolver.resolve(tracking_uri)

        if resolved_uri != tracking_uri:
            logger.info(f"DNS resolved tracking URI: {tracking_uri} -> {resolved_uri}")
        else:
            logger.debug(
                f"Tracking URI unchanged (already IP or resolution not needed): {tracking_uri}"
            )

        return resolved_uri

    except DNSResolutionError as e:
        logger.error(f"DNS resolution failed for tracking URI {tracking_uri}: {e}")
        if e.fallback_used:
            logger.warning(f"Using fallback IP for tracking URI: {tracking_uri}")
            # If fallback was used, we should have a resolved URI
            return tracking_uri
        else:
            # No fallback available, re-raise the error
            raise
    except Exception as e:
        logger.error(f"Unexpected error resolving tracking URI {tracking_uri}: {e}")
        # Return original URI as fallback
        return tracking_uri


def resolve_tracking_uri_sync(tracking_uri: str) -> str:
    """Wrap DNS resolution of tracking URI in synchronous function.

    Args:
    ----
        tracking_uri: MLFlow tracking URI (may contain hostname)

    Returns:
    -------
        Resolved tracking URI with IP address

    """
    try:
        # Try to get or create event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is already running, we need to use a different approach
                # This can happen in Jupyter notebooks or async contexts
                logger.warning(
                    "Event loop already running, using synchronous DNS resolution fallback"
                )
                return tracking_uri
        except RuntimeError:
            # No event loop, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Run the async DNS resolution
        return loop.run_until_complete(resolve_tracking_uri(tracking_uri))

    except Exception as e:
        logger.warning(f"Failed to resolve tracking URI {tracking_uri} synchronously: {e}")
        return tracking_uri


class MLflowCircuitBreaker:
    """Enhanced circuit breaker for MLflow operations with auto-reset and monitoring."""

    def __init__(  # noqa: ANN204
        self,  # noqa: ANN101
        failure_threshold: int = None,
        recovery_timeout: int = None,
        max_recovery_attempts: int = None,
    ) -> None:
        # Use environment variables or improved defaults
        self.failure_threshold = failure_threshold or int(
            os.getenv("MLFLOW_CB_FAILURE_THRESHOLD", "5")
        )
        self.recovery_timeout = recovery_timeout or int(
            os.getenv("MLFLOW_CB_RECOVERY_TIMEOUT", "60")
        )
        self.max_recovery_attempts = max_recovery_attempts or int(
            os.getenv("MLFLOW_CB_MAX_RECOVERY_ATTEMPTS", "5")
        )
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.recovery_attempts = 0
        self.last_success_time = time.time()
        self.consecutive_successes = 0

    def is_open(self) -> bool:  # noqa: ANN101
        """Check if circuit breaker is open (blocking requests)."""
        if self.state == "OPEN":
            if (
                self.last_failure_time
                and (time.time() - self.last_failure_time) > self.recovery_timeout
            ):
                if self.recovery_attempts < self.max_recovery_attempts:
                    self.state = "HALF_OPEN"
                    self.recovery_attempts += 1
                    logger.info(
                        "Circuit breaker moving to HALF_OPEN state "
                        f"(attempt {self.recovery_attempts}/{self.max_recovery_attempts})"
                    )
                    return False
                else:
                    # Extend timeout exponentially after max attempts
                    extended_timeout = self.recovery_timeout * (
                        2 ** (self.recovery_attempts - self.max_recovery_attempts)
                    )
                    if (time.time() - self.last_failure_time) > extended_timeout:
                        self.state = "HALF_OPEN"
                        logger.info(
                            "Circuit breaker moving to HALF_OPEN state after "
                            f"extended timeout ({extended_timeout}s)"
                        )
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
                logger.info(
                    f"Circuit breaker HALF_OPEN: {self.consecutive_successes}/2 "
                    "successes for full recovery"
                )
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
            logger.warning(
                "Circuit breaker back to OPEN: Failure during recovery "
                f"(attempt {self.recovery_attempts})"
            )
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
            "time_since_last_failure": time.time() - self.last_failure_time
            if self.last_failure_time
            else None,
            "time_until_retry": max(
                0, self.recovery_timeout - (time.time() - self.last_failure_time)
            )
            if self.last_failure_time and self.state == "OPEN"
            else 0,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
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
    recovery_timeout=int(
        os.getenv("MLFLOW_CB_RECOVERY_TIMEOUT", "60")
    ),  # Increased from 30 to 60 seconds
    max_recovery_attempts=int(
        os.getenv("MLFLOW_CB_MAX_RECOVERY_ATTEMPTS", "5")
    ),  # Increased from 3 to 5
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

            delay = base_delay * (2**attempt)
            logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)


class MLFlowConfig:
    """Configuration manager for MLFlow tracking with DNS resolution."""

    def __init__(self) -> None:
        self.tracking_uri_raw = os.getenv(
            "MLFLOW_TRACKING_URI", "https://mlflow.hokusai-development.local:5000"
        )
        self.experiment_name = os.getenv("MLFLOW_EXPERIMENT_NAME", "hokusai-pipeline")
        self.artifact_root = os.getenv("MLFLOW_ARTIFACT_ROOT", None)
        self._resolved_tracking_uri = None

        # Resolve tracking URI with DNS fallback
        self.tracking_uri = self._resolve_tracking_uri_with_retry()

    def _resolve_tracking_uri_with_retry(self) -> str:
        """Resolve tracking URI with retry logic and fallback.

        Returns
        -------
            Resolved tracking URI or original URI if resolution fails

        """
        try:
            resolved_uri = resolve_tracking_uri_sync(self.tracking_uri_raw)
            self._resolved_tracking_uri = resolved_uri
            return resolved_uri
        except Exception as e:
            logger.warning(f"Failed to resolve tracking URI {self.tracking_uri_raw}: {e}")
            # Fall back to original URI
            return self.tracking_uri_raw

    def refresh_dns_resolution(self) -> bool:
        """Refresh DNS resolution for tracking URI.

        Returns
        -------
            True if resolution succeeded, False otherwise

        """
        try:
            new_resolved_uri = resolve_tracking_uri_sync(self.tracking_uri_raw)
            if new_resolved_uri != self.tracking_uri:
                logger.info(f"DNS resolution updated: {self.tracking_uri} -> {new_resolved_uri}")
                self.tracking_uri = new_resolved_uri
                self._resolved_tracking_uri = new_resolved_uri
                return True
            return True
        except Exception as e:
            logger.warning(f"Failed to refresh DNS resolution for {self.tracking_uri_raw}: {e}")
            return False

    def get_dns_info(self) -> dict:
        """Get DNS resolution information for tracking URI.

        Returns
        -------
            Dictionary with DNS resolution details

        """
        from src.utils.dns_resolver import get_dns_resolver

        dns_resolver = get_dns_resolver()
        dns_metrics = dns_resolver.get_metrics()
        dns_health = dns_resolver.health_check()

        return {
            "raw_tracking_uri": self.tracking_uri_raw,
            "resolved_tracking_uri": self._resolved_tracking_uri,
            "current_tracking_uri": self.tracking_uri,
            "dns_metrics": dns_metrics,
            "dns_health": dns_health,
        }

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
    """Get current MLflow connection status with DNS resolution details and circuit breaker state."""
    # Import settings to get configurable timeout
    try:
        from src.api.utils.config import get_settings

        settings = get_settings()
        connection_timeout = settings.health_check_timeout
    except ImportError:
        # Fallback if settings not available
        connection_timeout = 10.0

    cb_status = _circuit_breaker.get_status()

    # Get DNS resolution information
    from src.utils.dns_resolver import get_dns_resolver

    dns_resolver = get_dns_resolver()
    dns_metrics = dns_resolver.get_metrics()
    dns_health = dns_resolver.health_check()

    # Get raw and resolved tracking URIs
    raw_tracking_uri = os.getenv(
        "MLFLOW_TRACKING_URI", "https://mlflow.hokusai-development.local:5000"
    )

    status = {
        "circuit_breaker_state": cb_status["state"],
        "circuit_breaker_details": cb_status,
        "connected": False,
        "tracking_uri": raw_tracking_uri,
        "connection_timeout": connection_timeout,
        "error": None,
        "last_check_time": datetime.now().isoformat(),
        "dns_resolution": {
            "raw_uri": raw_tracking_uri,
            "metrics": dns_metrics,
            "health": dns_health,
        },
    }

    if _circuit_breaker.is_open():
        status["error"] = (
            "Circuit breaker is OPEN - MLflow unavailable "
            f"(retry in {cb_status['time_until_retry']:.0f}s)"
        )
        status["can_retry_in_seconds"] = cb_status["time_until_retry"]
        _update_metrics(status)
        return status

    try:
        # Try to resolve the tracking URI before testing connection
        try:
            resolved_uri = resolve_tracking_uri_sync(raw_tracking_uri)
            status["dns_resolution"]["resolved_uri"] = resolved_uri
            if resolved_uri != raw_tracking_uri:
                logger.debug(f"Using resolved URI for connection test: {resolved_uri}")
            test_uri = resolved_uri
        except Exception as e:
            logger.warning(f"DNS resolution failed, using raw URI: {e}")
            test_uri = raw_tracking_uri
            status["dns_resolution"]["resolution_error"] = str(e)

        # Connection test with configurable timeout and enhanced error handling
        start_time = time.time()

        # Set MLflow tracking URI with timeout consideration
        mlflow.set_tracking_uri(test_uri)

        # Test basic connectivity with timeout wrapper
        def _test_connection() -> None:
            # Test basic connectivity
            mlflow.get_experiment_by_name("default")

            # Test if we can create/access an experiment (more comprehensive check)
            test_experiment = "health-check-test"
            try:
                mlflow.get_experiment_by_name(test_experiment)
            except Exception:  # noqa: S110
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
            status["warning"] = (
                f"Slow response time: {response_time:.0f}ms (threshold: {warning_threshold:.0f}ms)"
            )
            logger.warning(
                f"MLflow slow response: {response_time:.0f}ms "
                f"(threshold: {warning_threshold:.0f}ms)"
            )

        _circuit_breaker.record_success()

    except Exception as e:
        status["error"] = str(e)
        status["error_type"] = type(e).__name__
        status["connection_attempts"] = 2  # Number of retry attempts made
        _circuit_breaker.record_failure()
        logger.error(
            f"MLflow connection failed after retries: {e}",
            extra={
                "tracking_uri": status["tracking_uri"],
                "timeout": connection_timeout,
                "circuit_breaker_state": cb_status["state"],
            },
        )

    _update_metrics(status)
    return status


def _update_metrics(status: dict) -> None:  # noqa: ANN401
    """Update Prometheus metrics with MLflow status."""
    try:
        from src.utils.prometheus_metrics import update_mlflow_metrics

        update_mlflow_metrics(status)
    except ImportError:
        # Prometheus metrics not available, skip
        pass
    except Exception as e:
        logger.debug(f"Error updating MLflow metrics: {e}")


def configure_internal_mtls() -> None:
    """Configure mTLS for internal MLflow communication.

    Only enabled in staging/production environments.
    Uses AWS Secrets Manager for certificate management.

    This function provides AUTHENTICATION setup for MLflow via mTLS certificates.
    In development, this function does nothing and logs that mTLS is not configured.
    In staging/production, it:
    1. Retrieves certificates from AWS Secrets Manager (authentication credentials)
    2. Writes certificates to /tmp/mlflow-certs
    3. Sets environment variables for MLflow client (MLFLOW_TRACKING_CLIENT_CERT_PATH, etc.)

    Note: This uses certificate-based authentication (mTLS) instead of token-based auth.
    """
    environment = os.getenv("ENVIRONMENT", "development")

    if environment in ["staging", "production"]:
        try:
            # Import boto3 for AWS Secrets Manager access
            import boto3

            logger.info(f"Configuring mTLS for {environment} environment")

            # Create Secrets Manager client
            secrets_client = boto3.client("secretsmanager", region_name="us-east-1")

            # Retrieve certificates from Secrets Manager
            logger.debug("Retrieving client certificate from Secrets Manager")
            client_cert_response = secrets_client.get_secret_value(
                SecretId=f"hokusai/{environment}/mlflow/client-cert"
            )
            client_cert = client_cert_response["SecretString"]

            logger.debug("Retrieving client key from Secrets Manager")
            client_key_response = secrets_client.get_secret_value(
                SecretId=f"hokusai/{environment}/mlflow/client-key"
            )
            client_key = client_key_response["SecretString"]

            logger.debug("Retrieving CA certificate from Secrets Manager")
            ca_cert_response = secrets_client.get_secret_value(
                SecretId=f"hokusai/{environment}/mlflow/ca-cert"
            )
            ca_cert = ca_cert_response["SecretString"]

            # Create certificate directory
            cert_dir = "/tmp/mlflow-certs"  # noqa: S108
            os.makedirs(cert_dir, exist_ok=True)
            logger.debug(f"Created certificate directory: {cert_dir}")

            # Write certificates to files
            client_cert_path = f"{cert_dir}/client.crt"
            with open(client_cert_path, "w") as f:
                f.write(client_cert)
            logger.debug(f"Wrote client certificate to {client_cert_path}")

            client_key_path = f"{cert_dir}/client.key"
            with open(client_key_path, "w") as f:
                f.write(client_key)
            # Set restrictive permissions on private key
            os.chmod(client_key_path, 0o600)
            logger.debug(f"Wrote client key to {client_key_path}")

            ca_cert_path = f"{cert_dir}/ca.crt"
            with open(ca_cert_path, "w") as f:
                f.write(ca_cert)
            logger.debug(f"Wrote CA certificate to {ca_cert_path}")

            # Set environment variables for MLflow client
            os.environ["MLFLOW_TRACKING_CLIENT_CERT_PATH"] = client_cert_path
            os.environ["MLFLOW_TRACKING_CLIENT_KEY_PATH"] = client_key_path
            os.environ["MLFLOW_TRACKING_SERVER_CERT_PATH"] = ca_cert_path

            logger.info("Configured mTLS for internal MLflow communication")

        except Exception as e:
            logger.error(f"Failed to configure mTLS: {e}")
            raise
    else:
        logger.info("mTLS not configured for development environment")
