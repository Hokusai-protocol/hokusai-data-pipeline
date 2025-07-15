#!/usr/bin/env python3
"""Test script for MLflow improvements."""

import sys
import os
import time
import logging

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils.mlflow_config import (
    get_mlflow_status,
    mlflow_run_context,
    MLflowUnavailableError,
    _circuit_breaker
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_mlflow_status():
    """Test MLflow status function."""
    print("=== Testing MLflow Status ===")
    
    status = get_mlflow_status()
    print(f"Circuit breaker state: {status['circuit_breaker_state']}")
    print(f"Connected: {status['connected']}")
    print(f"Tracking URI: {status['tracking_uri']}")
    print(f"Error: {status['error']}")
    print(f"Failure count: {status['failure_count']}")
    
    return status

def test_circuit_breaker():
    """Test circuit breaker functionality."""
    print("\n=== Testing Circuit Breaker ===")
    
    # Reset circuit breaker
    _circuit_breaker.failure_count = 0
    _circuit_breaker.state = "CLOSED"
    
    print(f"Initial state: {_circuit_breaker.state}")
    
    # Simulate failures
    for i in range(6):  # Should trigger circuit breaker at 5 failures
        _circuit_breaker.record_failure()
        print(f"Failure {i+1}: state={_circuit_breaker.state}, count={_circuit_breaker.failure_count}")
    
    # Test if circuit breaker is open
    print(f"Circuit breaker open: {_circuit_breaker.is_open()}")
    
    # Test recovery
    print("Waiting for recovery timeout...")
    time.sleep(2)  # Wait longer than recovery timeout for testing
    
    # Reset to simulate recovery
    _circuit_breaker.last_failure_time = time.time() - 70  # Simulate time passing
    print(f"After timeout - Circuit breaker open: {_circuit_breaker.is_open()}")
    
    # Test success
    _circuit_breaker.record_success()
    print(f"After success: state={_circuit_breaker.state}, count={_circuit_breaker.failure_count}")

def test_run_context():
    """Test MLflow run context with circuit breaker."""
    print("\n=== Testing MLflow Run Context ===")
    
    # Reset circuit breaker to closed state
    _circuit_breaker.failure_count = 0
    _circuit_breaker.state = "CLOSED"
    
    try:
        with mlflow_run_context(run_name="test_run", tags={"test": "true"}) as run:
            print(f"Run started successfully: {run.info.run_id if run else 'None'}")
            
    except MLflowUnavailableError as e:
        print(f"MLflow unavailable: {e}")
    except Exception as e:
        print(f"Other error: {e}")

def test_prometheus_metrics():
    """Test Prometheus metrics."""
    print("\n=== Testing Prometheus Metrics ===")
    
    try:
        from utils.prometheus_metrics import get_prometheus_metrics
        
        # Get status to update metrics
        status = get_mlflow_status()
        
        # Get metrics
        metrics = get_prometheus_metrics()
        
        print("Prometheus metrics:")
        print(metrics[:500] + "..." if len(metrics) > 500 else metrics)
        
    except ImportError:
        print("Prometheus client not available - metrics disabled")
    except Exception as e:
        print(f"Error getting metrics: {e}")

def main():
    """Run all tests."""
    print("Testing MLflow Improvements")
    print("=" * 40)
    
    try:
        test_mlflow_status()
        test_circuit_breaker()
        test_run_context()
        test_prometheus_metrics()
        
        print("\n=== Test Summary ===")
        print("All tests completed. Check output above for any errors.")
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()