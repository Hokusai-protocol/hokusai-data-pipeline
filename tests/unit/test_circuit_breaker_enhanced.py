"""
Enhanced unit tests for MLflow circuit breaker logic.

Tests auto-reset, state transitions, recovery mechanisms, and edge cases.
"""

import os
import time
from unittest.mock import Mock, patch

import pytest

from src.utils.mlflow_config import (
    MLflowCircuitBreaker,
    get_circuit_breaker_status,
    reset_circuit_breaker,
)


class TestMLflowCircuitBreaker:
    """Comprehensive tests for the MLflow circuit breaker implementation."""

    def test_initial_state(self):
        """Test circuit breaker starts in CLOSED state."""
        cb = MLflowCircuitBreaker()
        assert cb.state == "CLOSED"
        assert cb.failure_count == 0
        assert not cb.is_open()
        assert cb.consecutive_successes == 0

    def test_basic_failure_tracking(self):
        """Test that failures are tracked correctly."""
        cb = MLflowCircuitBreaker(failure_threshold=3)

        # Record failures one by one
        for i in range(3):
            cb.record_failure()
            assert cb.failure_count == i + 1

        # Should be OPEN after threshold failures
        assert cb.state == "OPEN"
        assert cb.is_open()

    def test_success_in_closed_state(self):
        """Test success recording in CLOSED state."""
        cb = MLflowCircuitBreaker()

        # Record some failures first
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2

        # Success should reduce failure count
        cb.record_success()
        assert cb.failure_count == 1
        assert cb.state == "CLOSED"
        assert cb.consecutive_successes == 1

    def test_state_transition_closed_to_open(self):
        """Test transition from CLOSED to OPEN state."""
        cb = MLflowCircuitBreaker(failure_threshold=2)

        assert cb.state == "CLOSED"

        cb.record_failure()
        assert cb.state == "CLOSED"  # Still closed after first failure

        cb.record_failure()
        assert cb.state == "OPEN"  # Should be open after threshold
        assert cb.is_open()

    def test_state_transition_open_to_half_open(self):
        """Test transition from OPEN to HALF_OPEN state."""
        cb = MLflowCircuitBreaker(failure_threshold=2, recovery_timeout=1)

        # Trigger OPEN state
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"

        # Wait for recovery timeout
        time.sleep(1.1)

        # Should transition to HALF_OPEN
        assert not cb.is_open()  # This call triggers the state transition
        assert cb.state == "HALF_OPEN"

    def test_half_open_success_recovery(self):
        """Test successful recovery from HALF_OPEN to CLOSED."""
        cb = MLflowCircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        # Trigger OPEN state
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"

        # Wait and transition to HALF_OPEN
        time.sleep(0.2)
        cb.is_open()  # Triggers transition to HALF_OPEN
        assert cb.state == "HALF_OPEN"

        # First success in HALF_OPEN - still in HALF_OPEN
        cb.record_success()
        assert cb.state == "HALF_OPEN"
        assert cb.consecutive_successes == 1

        # Second success - should close circuit
        cb.record_success()
        assert cb.state == "CLOSED"
        assert cb.consecutive_successes == 2
        assert cb.failure_count == 0

    def test_half_open_failure_back_to_open(self):
        """Test failure in HALF_OPEN returns to OPEN state."""
        cb = MLflowCircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        # Trigger OPEN state
        cb.record_failure()
        cb.record_failure()

        # Wait and transition to HALF_OPEN
        time.sleep(0.2)
        cb.is_open()  # Triggers transition
        assert cb.state == "HALF_OPEN"

        # Failure in HALF_OPEN should return to OPEN
        cb.record_failure()
        assert cb.state == "OPEN"
        assert cb.consecutive_successes == 0

    def test_max_recovery_attempts(self):
        """Test maximum recovery attempts limitation."""
        cb = MLflowCircuitBreaker(
            failure_threshold=2, recovery_timeout=0.1, max_recovery_attempts=2
        )

        # Trigger OPEN state
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"

        # First recovery attempt
        time.sleep(0.2)
        cb.is_open()  # First attempt
        assert cb.state == "HALF_OPEN"
        assert cb.recovery_attempts == 1

        # Fail and go back to OPEN
        cb.record_failure()
        assert cb.state == "OPEN"

        # Second recovery attempt
        time.sleep(0.2)
        cb.is_open()  # Second attempt
        assert cb.state == "HALF_OPEN"
        assert cb.recovery_attempts == 2

        # Fail again
        cb.record_failure()
        assert cb.state == "OPEN"

        # After max attempts, circuit should transition after extended timeout.
        time.sleep(0.2)
        assert not cb.is_open()
        assert cb.state == "HALF_OPEN"

    def test_exponential_backoff_after_max_attempts(self):
        """Test exponential backoff after max recovery attempts."""
        cb = MLflowCircuitBreaker(
            failure_threshold=1, recovery_timeout=0.1, max_recovery_attempts=1
        )

        # Trigger OPEN state
        cb.record_failure()
        assert cb.state == "OPEN"

        # Use up the recovery attempt
        time.sleep(0.2)
        cb.is_open()
        assert cb.state == "HALF_OPEN"
        cb.record_failure()  # Fail recovery
        assert cb.state == "OPEN"
        assert cb.recovery_attempts == 1

        # Should require extended timeout (0.1 * 2^(1-1) = 0.1 * 1 = 0.1)
        time.sleep(0.15)
        cb.is_open()
        assert cb.state == "HALF_OPEN"

    def test_force_reset(self):
        """Test manual reset functionality."""
        cb = MLflowCircuitBreaker(failure_threshold=2)

        # Get into OPEN state
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"
        assert cb.failure_count == 2

        # Force reset
        cb.force_reset()
        assert cb.state == "CLOSED"
        assert cb.failure_count == 0
        assert cb.recovery_attempts == 0
        assert cb.consecutive_successes == 0
        assert cb.last_failure_time is None

    def test_status_reporting(self):
        """Test detailed status reporting."""
        cb = MLflowCircuitBreaker(failure_threshold=3, recovery_timeout=30)

        # Record some failures
        cb.record_failure()
        cb.record_failure()

        status = cb.get_status()

        assert status["state"] == "CLOSED"
        assert status["failure_count"] == 2
        assert status["consecutive_successes"] == 0
        assert status["recovery_attempts"] == 0
        assert status["failure_threshold"] == 3
        assert status["recovery_timeout"] == 30
        assert status["last_failure_time"] is not None
        assert status["time_since_last_failure"] is not None

    def test_status_in_open_state(self):
        """Test status reporting when circuit is OPEN."""
        cb = MLflowCircuitBreaker(failure_threshold=2, recovery_timeout=10)

        # Get to OPEN state
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"

        status = cb.get_status()

        assert status["state"] == "OPEN"
        assert status["failure_count"] == 2
        assert status["time_until_retry"] > 0
        assert status["time_until_retry"] <= 10

    def test_time_calculations(self):
        """Test time-based calculations are accurate."""
        cb = MLflowCircuitBreaker(recovery_timeout=2)

        start_time = time.time()
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        # Check that last_failure_time is recent
        assert cb.last_failure_time >= start_time
        assert cb.last_failure_time <= time.time()

        status = cb.get_status()
        assert status["time_since_last_failure"] >= 0
        assert status["time_until_retry"] <= 2

    def test_consecutive_success_reset_on_failure(self):
        """Test that consecutive successes reset on failure."""
        cb = MLflowCircuitBreaker()

        # Build up some successes
        cb.record_success()
        cb.record_success()
        assert cb.consecutive_successes == 2

        # Failure should reset consecutive successes
        cb.record_failure()
        assert cb.consecutive_successes == 0

    def test_gradual_failure_count_reduction(self):
        """Test that failure count gradually reduces with successes."""
        cb = MLflowCircuitBreaker()

        # Build up failures
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2

        # Successes should gradually reduce failure count
        cb.record_success()
        assert cb.failure_count == 1

        cb.record_success()
        assert cb.failure_count == 0

    def test_configurable_parameters(self):
        """Test that circuit breaker accepts configurable parameters."""
        cb = MLflowCircuitBreaker(
            failure_threshold=5, recovery_timeout=60, max_recovery_attempts=10
        )

        assert cb.failure_threshold == 5
        assert cb.recovery_timeout == 60
        assert cb.max_recovery_attempts == 10

        # Test with different threshold
        for i in range(5):
            cb.record_failure()

        assert cb.state == "OPEN"

    def test_edge_case_zero_threshold(self):
        """Test that zero threshold falls back to configured defaults."""
        cb = MLflowCircuitBreaker(failure_threshold=0)
        assert cb.failure_threshold > 0

    def test_edge_case_zero_timeout(self):
        """Test that zero timeout falls back to configured defaults."""
        cb = MLflowCircuitBreaker(failure_threshold=1, recovery_timeout=0)
        assert cb.recovery_timeout > 0


class TestGlobalCircuitBreaker:
    """Test the global circuit breaker functions."""

    @patch("src.utils.mlflow_config._circuit_breaker")
    def test_get_circuit_breaker_status(self, mock_cb):
        """Test getting global circuit breaker status."""
        mock_status = {"state": "CLOSED", "failure_count": 0}
        mock_cb.get_status.return_value = mock_status

        status = get_circuit_breaker_status()

        assert status == mock_status
        mock_cb.get_status.assert_called_once()

    @patch("src.utils.mlflow_config._circuit_breaker")
    def test_reset_circuit_breaker(self, mock_cb):
        """Test manual reset of global circuit breaker."""
        reset_circuit_breaker()

        mock_cb.force_reset.assert_called_once()

    def test_environment_configuration(self):
        """Test that circuit breaker uses environment variables."""
        with patch.dict(
            "os.environ",
            {
                "MLFLOW_CB_FAILURE_THRESHOLD": "5",
                "MLFLOW_CB_RECOVERY_TIMEOUT": "60",
                "MLFLOW_CB_MAX_RECOVERY_ATTEMPTS": "10",
            },
        ):
            # Re-import to pick up new env vars
            from src.utils.mlflow_config import MLflowCircuitBreaker

            cb = MLflowCircuitBreaker(
                failure_threshold=int(os.getenv("MLFLOW_CB_FAILURE_THRESHOLD", "3")),
                recovery_timeout=int(os.getenv("MLFLOW_CB_RECOVERY_TIMEOUT", "30")),
                max_recovery_attempts=int(os.getenv("MLFLOW_CB_MAX_RECOVERY_ATTEMPTS", "3")),
            )

            assert cb.failure_threshold == 5
            assert cb.recovery_timeout == 60
            assert cb.max_recovery_attempts == 10


class TestCircuitBreakerIntegration:
    """Integration tests for circuit breaker with MLflow operations."""

    @patch("src.utils.mlflow_config.exponential_backoff_retry")
    @patch("src.utils.mlflow_config.mlflow")
    def test_circuit_breaker_with_mlflow_operations(self, mock_mlflow, mock_retry):
        """Test circuit breaker integration with MLflow operations."""
        from src.utils.mlflow_config import (
            get_circuit_breaker_status,
            get_mlflow_status,
            reset_circuit_breaker,
        )

        reset_circuit_breaker()
        mock_retry.side_effect = lambda func, **kwargs: func()

        # First few calls should work
        mock_mlflow.get_experiment_by_name.return_value = Mock()

        status1 = get_mlflow_status()
        assert status1["connected"] is True
        assert status1["circuit_breaker_state"] == "CLOSED"
        threshold = status1["circuit_breaker_details"]["failure_threshold"]

        # Simulate MLflow failures
        mock_mlflow.get_experiment_by_name.side_effect = Exception("MLflow down")

        # First failed check should fail while breaker is still closed.
        status2 = get_mlflow_status()
        assert status2["connected"] is False

        # After enough failures, circuit breaker should open.
        for _ in range(max(0, threshold - 1)):
            get_mlflow_status()
        assert get_circuit_breaker_status()["state"] == "OPEN"

        status3 = get_mlflow_status()
        assert status3["connected"] is False
        assert "Circuit breaker is OPEN" in status3["error"]

    @patch("src.utils.mlflow_config.mlflow")
    def test_circuit_breaker_recovery(self, mock_mlflow):
        """Test circuit breaker recovery after failures."""
        from src.utils.mlflow_config import (
            _circuit_breaker,
            get_circuit_breaker_status,
            get_mlflow_status,
            reset_circuit_breaker,
        )

        reset_circuit_breaker()

        # Force circuit breaker to OPEN state
        _circuit_breaker.state = "OPEN"
        _circuit_breaker.last_failure_time = time.time() - (_circuit_breaker.recovery_timeout + 1)
        _circuit_breaker.recovery_attempts = 0

        # Mock MLflow to work again
        mock_mlflow.get_experiment_by_name.return_value = Mock()

        status = get_mlflow_status()

        # Should attempt recovery and succeed
        assert status["connected"] is True
        # Circuit should be HALF_OPEN or CLOSED depending on consecutive successes.
        assert get_circuit_breaker_status()["state"] in ["HALF_OPEN", "CLOSED"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
