"""Prometheus metrics for MLflow monitoring."""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Try to import prometheus_client, but make it optional for now
try:
    from prometheus_client import Counter, Gauge, Histogram, Info, generate_latest
    PROMETHEUS_AVAILABLE = True
except ImportError:
    logger.warning("prometheus_client not available, metrics will be disabled")
    PROMETHEUS_AVAILABLE = False


class MLflowMetrics:
    """Prometheus metrics for MLflow monitoring."""
    
    def __init__(self):
        if not PROMETHEUS_AVAILABLE:
            return
            
        self._initialized = False
        self._init_metrics()
        
    def _init_metrics(self):
        """Initialize metrics only once."""
        if self._initialized:
            return
            
        # Circuit breaker metrics
        self.circuit_breaker_state = Gauge(
            'mlflow_circuit_breaker_state',
            'MLflow circuit breaker state (0=CLOSED, 1=HALF_OPEN, 2=OPEN)'
        )
        
        self.circuit_breaker_failures = Gauge(
            'mlflow_circuit_breaker_failures_total',
            'Total number of MLflow circuit breaker failures'
        )
        
        # Connection metrics  
        self.connection_status = Gauge(
            'mlflow_connection_status',
            'MLflow connection status (1=connected, 0=disconnected)'
        )
        
        self.connection_attempts = Counter(
            'mlflow_connection_attempts_total',
            'Total number of MLflow connection attempts'
        )
        
        self.connection_failures = Counter(
            'mlflow_connection_failures_total',
            'Total number of MLflow connection failures'
        )
        
        # Response time metrics
        self.response_time = Histogram(
            'mlflow_response_time_seconds',
            'MLflow response time in seconds'
        )
        
        # Info metrics
        self.info = Info(
            'mlflow_info',
            'MLflow connection information'
        )
        
        self._initialized = True
        
    def update_from_status(self, status: Dict[str, Any]):
        """Update metrics from MLflow status dict."""
        if not PROMETHEUS_AVAILABLE or not self._initialized:
            return
            
        try:
            # Update circuit breaker state
            state_mapping = {"CLOSED": 0, "HALF_OPEN": 1, "OPEN": 2}
            state = status.get("circuit_breaker_state", "CLOSED")
            self.circuit_breaker_state.set(state_mapping.get(state, 0))
            
            # Update failure count
            failure_count = status.get("failure_count", 0)
            self.circuit_breaker_failures.set(failure_count)
            
            # Update connection status
            connected = status.get("connected", False)
            self.connection_status.set(1 if connected else 0)
            
            # Update connection attempts
            self.connection_attempts.inc()
            
            # Update failures if not connected
            if not connected:
                self.connection_failures.inc()
                
            # Update info
            self.info.info({
                'tracking_uri': status.get("tracking_uri", "unknown"),
                'error': status.get("error", "none") or "none",
                'last_failure_time': str(status.get("last_failure_time", "none"))
            })
            
        except Exception as e:
            logger.error(f"Error updating MLflow metrics: {e}")
    
    def get_metrics(self) -> str:
        """Get metrics in Prometheus format."""
        if not PROMETHEUS_AVAILABLE or not self._initialized:
            return "# prometheus_client not available\n"
        
        try:
            return generate_latest().decode('utf-8')
        except Exception as e:
            logger.error(f"Error generating metrics: {e}")
            return f"# Error generating metrics: {e}\n"


# Global metrics instance
mlflow_metrics = MLflowMetrics()


def update_mlflow_metrics(status: Dict[str, Any]):
    """Update MLflow metrics from status dict."""
    mlflow_metrics.update_from_status(status)


def get_prometheus_metrics() -> str:
    """Get all metrics in Prometheus format."""
    return mlflow_metrics.get_metrics()