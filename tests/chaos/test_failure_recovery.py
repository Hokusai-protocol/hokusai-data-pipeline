"""
Chaos engineering tests for failure scenarios and recovery.

Tests system resilience under various failure conditions and validates recovery mechanisms.
"""

import pytest
import time
import random
import asyncio
from unittest.mock import Mock, patch, MagicMock, side_effect
from contextlib import contextmanager
from typing import List, Dict, Any
from dataclasses import dataclass

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routes.health import router
from src.utils.mlflow_config import reset_circuit_breaker, MLflowCircuitBreaker


@dataclass
class ChaosExperiment:
    """Configuration for a chaos engineering experiment."""
    name: str
    description: str
    failure_scenarios: List[str]
    expected_recovery_time: float
    success_criteria: Dict[str, Any]


@dataclass
class ChaosResult:
    """Result of a chaos engineering experiment."""
    experiment_name: str
    failure_injected: bool
    recovery_achieved: bool
    recovery_time: float
    service_availability_during_failure: float
    errors_observed: List[str]
    metrics: Dict[str, float]


class ChaosTestFramework:
    """Framework for running chaos engineering experiments."""
    
    def __init__(self, client: TestClient):
        self.client = client
        self.experiment_results = []
    
    def run_experiment(self, experiment: ChaosExperiment) -> ChaosResult:
        """Run a single chaos experiment."""
        print(f"\n🔥 Running Chaos Experiment: {experiment.name}")
        print(f"Description: {experiment.description}")
        
        # Baseline check
        baseline_response = self.client.get("/health")
        baseline_healthy = baseline_response.status_code == 200
        
        if not baseline_healthy:
            pytest.fail(f"System not healthy at baseline: {baseline_response.status_code}")
        
        result = ChaosResult(
            experiment_name=experiment.name,
            failure_injected=False,
            recovery_achieved=False,
            recovery_time=0.0,
            service_availability_during_failure=0.0,
            errors_observed=[],
            metrics={}
        )
        
        return result
    
    def inject_failures(self, scenarios: List[str]) -> None:
        """Inject various failure scenarios."""
        for scenario in scenarios:
            print(f"💥 Injecting failure: {scenario}")
    
    def measure_availability(self, duration: float, interval: float = 1.0) -> float:
        """Measure service availability over a time period."""
        successful_checks = 0
        total_checks = 0
        
        end_time = time.time() + duration
        while time.time() < end_time:
            try:
                response = self.client.get("/health")
                if response.status_code == 200:
                    successful_checks += 1
                total_checks += 1
                time.sleep(interval)
            except Exception as e:
                total_checks += 1
        
        return (successful_checks / total_checks * 100) if total_checks > 0 else 0.0
    
    def wait_for_recovery(self, max_wait_time: float, check_interval: float = 5.0) -> tuple[bool, float]:
        """Wait for system recovery and measure recovery time."""
        start_time = time.time()
        recovery_achieved = False
        
        while time.time() - start_time < max_wait_time:
            try:
                response = self.client.get("/health")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "healthy":
                        recovery_achieved = True
                        break
                time.sleep(check_interval)
            except Exception:
                time.sleep(check_interval)
        
        recovery_time = time.time() - start_time
        return recovery_achieved, recovery_time


@pytest.fixture
def app():
    """Create FastAPI test app for chaos testing."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client for chaos testing."""
    return TestClient(app)


@pytest.fixture
def chaos_framework(client):
    """Create chaos testing framework."""
    return ChaosTestFramework(client)


class TestServiceFailureScenarios:
    """Test various service failure scenarios and recovery."""
    
    def test_mlflow_complete_failure_recovery(self, client, chaos_framework):
        """Test complete MLflow failure and recovery."""
        with patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status, \
             patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher:
            
            # Setup other services as healthy
            mock_db.return_value = (True, None)
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.return_value = True
            mock_redis_module.return_value = mock_redis
            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg
            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}
            
            # Phase 1: System healthy
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED",
                "error": None
            }
            
            response1 = client.get("/health")
            assert response1.status_code == 200
            assert response1.json()["status"] == "healthy"
            print("✅ Phase 1: System healthy")
            
            # Phase 2: MLflow fails completely
            mock_mlflow_status.return_value = {
                "connected": False,
                "circuit_breaker_state": "OPEN",
                "error": "MLflow server completely unreachable",
                "can_retry_in_seconds": 30
            }
            
            response2 = client.get("/health")
            assert response2.status_code == 200  # Should still respond
            assert response2.json()["status"] == "degraded"
            print("💥 Phase 2: MLflow failed, system degraded")
            
            # Phase 3: System continues to operate in degraded mode
            availability = chaos_framework.measure_availability(duration=10.0, interval=2.0)
            assert availability >= 80.0, f"Availability too low during failure: {availability}%"
            print(f"📊 Phase 3: Availability during failure: {availability:.1f}%")
            
            # Phase 4: MLflow recovers
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED",
                "error": None
            }
            
            response3 = client.get("/health")
            assert response3.status_code == 200
            assert response3.json()["status"] == "healthy"
            print("🔄 Phase 4: MLflow recovered, system healthy")
    
    def test_database_connection_failure(self, client):
        """Test database connection failure impact."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            # Setup other services as healthy
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.return_value = True
            mock_redis_module.return_value = mock_redis
            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED"
            }
            
            # Phase 1: Database connection fails
            mock_db.return_value = (False, "Database connection timeout")
            
            # PostgreSQL direct connection also fails
            mock_pg = Mock()
            mock_pg.connect.side_effect = Exception("PostgreSQL connection refused")
            mock_pg_module.return_value = mock_pg
            
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "unhealthy"  # Should be unhealthy
            assert data["services"]["postgres"] == "unhealthy"
            print("💥 Database failure detected and reported correctly")
            
            # Phase 2: Readiness check should fail for critical service
            response_ready = client.get("/ready")
            assert response_ready.status_code == 503  # Service unavailable
            data_ready = response_ready.json()
            assert data_ready["can_serve_traffic"] is False
            print("🚫 Readiness check correctly failed due to critical database failure")
            
            # Phase 3: Database recovers
            mock_db.return_value = (True, None)
            mock_pg.connect.side_effect = None
            mock_pg.connect.return_value.close.return_value = None
            
            response_recovered = client.get("/health")
            assert response_recovered.status_code == 200
            assert response_recovered.json()["status"] == "healthy"
            print("🔄 Database recovered, system healthy")
    
    def test_redis_connection_chaos(self, client):
        """Test Redis connection instability."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            # Setup other services
            mock_db.return_value = (True, None)
            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg
            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED"
            }
            
            # Create unstable Redis connection
            mock_redis = Mock()
            
            # Simulate intermittent failures
            call_count = 0
            def unstable_redis_ping():
                nonlocal call_count
                call_count += 1
                if call_count % 3 == 0:  # Fail every 3rd call
                    raise Exception("Redis connection lost")
                return True
            
            mock_redis.Redis.return_value.ping.side_effect = unstable_redis_ping
            mock_redis_module.return_value = mock_redis
            
            # Test multiple requests to see intermittent failures
            healthy_responses = 0
            unhealthy_responses = 0
            
            for i in range(10):
                response = client.get("/health")
                assert response.status_code == 200  # Should always respond
                
                status = response.json()["status"]
                if status == "healthy":
                    healthy_responses += 1
                else:
                    unhealthy_responses += 1
                
                time.sleep(0.1)
            
            # Should have seen both healthy and unhealthy states
            assert healthy_responses > 0, "Should have some healthy responses"
            assert unhealthy_responses > 0, "Should have some unhealthy responses due to Redis failures"
            
            print(f"📊 Redis chaos: {healthy_responses} healthy, {unhealthy_responses} unhealthy responses")
    
    def test_circuit_breaker_cascading_failures(self, client):
        """Test circuit breaker behavior with cascading failures."""
        with patch('src.utils.mlflow_config._circuit_breaker') as mock_circuit_breaker, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status, \
             patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher:
            
            # Setup other services as healthy
            mock_db.return_value = (True, None)
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.return_value = True
            mock_redis_module.return_value = mock_redis
            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg
            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}
            
            # Create real circuit breaker for testing
            real_cb = MLflowCircuitBreaker(failure_threshold=3, recovery_timeout=2)
            mock_circuit_breaker.get_status = real_cb.get_status
            mock_circuit_breaker.is_open = real_cb.is_open
            mock_circuit_breaker.record_failure = real_cb.record_failure
            mock_circuit_breaker.record_success = real_cb.record_success
            mock_circuit_breaker.force_reset = real_cb.force_reset
            
            # Phase 1: Simulate MLflow failures to trigger circuit breaker
            def failing_mlflow_status():
                real_cb.record_failure()
                return {
                    "connected": False,
                    "circuit_breaker_state": real_cb.state,
                    "error": "MLflow connection failed"
                }
            
            mock_mlflow_status.side_effect = failing_mlflow_status
            
            # Make requests to trigger failures
            for i in range(3):
                response = client.get("/health")
                assert response.status_code == 200
                print(f"Request {i+1}: Circuit breaker state = {real_cb.state}")
            
            # Circuit breaker should now be OPEN
            assert real_cb.state == "OPEN"
            print("💥 Circuit breaker opened after failures")
            
            # Phase 2: Subsequent requests should get degraded service
            mock_mlflow_status.side_effect = None
            mock_mlflow_status.return_value = {
                "connected": False,
                "circuit_breaker_state": "OPEN",
                "error": "Circuit breaker is OPEN"
            }
            
            response_degraded = client.get("/health")
            assert response_degraded.status_code == 200
            assert response_degraded.json()["status"] == "degraded"
            print("🔄 Service degraded while circuit breaker is open")
            
            # Phase 3: Wait for recovery timeout and test recovery
            time.sleep(2.5)  # Wait for recovery timeout
            
            def recovering_mlflow_status():
                real_cb.record_success()
                return {
                    "connected": True,
                    "circuit_breaker_state": real_cb.state,
                    "error": None
                }
            
            mock_mlflow_status.side_effect = recovering_mlflow_status
            
            # Make a few successful requests to fully close circuit breaker
            for i in range(3):
                response = client.get("/health")
                assert response.status_code == 200
                print(f"Recovery request {i+1}: Circuit breaker state = {real_cb.state}")
            
            # Should eventually return to CLOSED state
            assert real_cb.state == "CLOSED"
            print("✅ Circuit breaker closed after recovery")
    
    def test_message_queue_failure_isolation(self, client):
        """Test that message queue failures don't bring down the system."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            # Setup core services as healthy
            mock_db.return_value = (True, None)
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.return_value = True
            mock_redis_module.return_value = mock_redis
            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED"
            }
            
            # Message queue fails
            mock_publisher.return_value.health_check.side_effect = Exception("Message queue unavailable")
            
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            
            # System should still be operational
            assert data["status"] in ["healthy", "degraded"]  # May be degraded but still operational
            assert data["services"]["message_queue"] == "unhealthy"
            
            print("✅ Message queue failure properly isolated")
    
    def test_network_partition_simulation(self, client):
        """Test behavior under simulated network partition."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            # Simulate network partition - all external services timeout
            mock_db.return_value = (False, "Connection timeout")
            
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.side_effect = Exception("Connection timeout")
            mock_redis_module.return_value = mock_redis
            
            mock_pg = Mock()
            mock_pg.connect.side_effect = Exception("Connection timeout")
            mock_pg_module.return_value = mock_pg
            
            mock_publisher.return_value.health_check.side_effect = Exception("Connection timeout")
            
            mock_mlflow_status.return_value = {
                "connected": False,
                "circuit_breaker_state": "OPEN",
                "error": "Connection timeout"
            }
            
            response = client.get("/health")
            assert response.status_code == 200  # Should still respond
            data = response.json()
            
            # All services should be unhealthy
            assert data["status"] == "unhealthy"
            assert all(
                service_status in ["unhealthy", "degraded"] 
                for key, service_status in data["services"].items() 
                if not key.endswith("_error") and not key.endswith("_details")
            )
            
            print("💥 Network partition detected and handled gracefully")
            
            # Service should still respond to liveness checks
            liveness_response = client.get("/live")
            assert liveness_response.status_code == 200
            assert liveness_response.json()["alive"] is True
            print("✅ Liveness probe still works during network partition")


class TestRecoveryMechanisms:
    """Test various recovery mechanisms and self-healing capabilities."""
    
    def test_circuit_breaker_auto_reset(self, client):
        """Test automatic circuit breaker reset functionality."""
        with patch('src.utils.mlflow_config._circuit_breaker') as mock_circuit_breaker:
            # Create real circuit breaker for testing
            real_cb = MLflowCircuitBreaker(failure_threshold=2, recovery_timeout=1)
            mock_circuit_breaker.get_status = real_cb.get_status
            mock_circuit_breaker.is_open = real_cb.is_open
            mock_circuit_breaker.record_failure = real_cb.record_failure
            mock_circuit_breaker.record_success = real_cb.record_success
            mock_circuit_breaker.force_reset = real_cb.force_reset
            
            # Trigger circuit breaker to open
            real_cb.record_failure()
            real_cb.record_failure()
            assert real_cb.state == "OPEN"
            print("💥 Circuit breaker opened")
            
            # Wait for auto-reset timeout
            time.sleep(1.5)
            
            # Check if circuit breaker attempts recovery
            is_open_before = real_cb.is_open()
            assert not is_open_before  # Should transition to HALF_OPEN
            assert real_cb.state == "HALF_OPEN"
            print("🔄 Circuit breaker auto-transitioned to HALF_OPEN")
            
            # Successful operation should close it
            real_cb.record_success()
            real_cb.record_success()  # Need two successes for full recovery
            assert real_cb.state == "CLOSED"
            print("✅ Circuit breaker auto-closed after successful operations")
    
    def test_manual_circuit_breaker_reset(self, client):
        """Test manual circuit breaker reset via API."""
        with patch('src.utils.mlflow_config.reset_circuit_breaker') as mock_reset:
            response = client.post("/health/mlflow/reset")
            
            assert response.status_code == 200
            data = response.json()
            
            assert "Circuit breaker reset successfully" in data["message"]
            assert data["reset_by"] == "manual_api_call"
            mock_reset.assert_called_once()
            
            print("✅ Manual circuit breaker reset successful")
    
    def test_gradual_service_recovery(self, client):
        """Test gradual recovery of services."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            # Start with all services failed
            mock_db.return_value = (False, "Database down")
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.side_effect = Exception("Redis down")
            mock_redis_module.return_value = mock_redis
            mock_pg = Mock()
            mock_pg.connect.side_effect = Exception("PostgreSQL down")
            mock_pg_module.return_value = mock_pg
            mock_publisher.return_value.health_check.side_effect = Exception("Queue down")
            mock_mlflow_status.return_value = {
                "connected": False,
                "circuit_breaker_state": "OPEN",
                "error": "MLflow down"
            }
            
            response1 = client.get("/health")
            assert response1.json()["status"] == "unhealthy"
            print("Phase 1: All services down")
            
            # Recover database
            mock_db.return_value = (True, None)
            response2 = client.get("/health")
            assert response2.json()["status"] == "unhealthy"  # Still unhealthy
            print("Phase 2: Database recovered")
            
            # Recover PostgreSQL
            mock_pg.connect.side_effect = None
            mock_pg.connect.return_value.close.return_value = None
            response3 = client.get("/health")
            print("Phase 3: PostgreSQL recovered")
            
            # Recover Redis
            mock_redis.Redis.return_value.ping.side_effect = None
            mock_redis.Redis.return_value.ping.return_value = True
            response4 = client.get("/health")
            print("Phase 4: Redis recovered")
            
            # Recover message queue
            mock_publisher.return_value.health_check.side_effect = None
            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}
            response5 = client.get("/health")
            print("Phase 5: Message queue recovered")
            
            # Finally recover MLflow
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED",
                "error": None
            }
            response6 = client.get("/health")
            assert response6.json()["status"] == "healthy"
            print("Phase 6: MLflow recovered - system fully healthy")
    
    def test_service_health_persistence(self, client):
        """Test that health state is properly maintained across multiple checks."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            # Setup stable healthy services
            mock_db.return_value = (True, None)
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.return_value = True
            mock_redis_module.return_value = mock_redis
            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg
            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}
            mock_mlflow_status.return_value = {
                "connected": True,
                "circuit_breaker_state": "CLOSED"
            }
            
            # Perform multiple health checks
            statuses = []
            for i in range(10):
                response = client.get("/health")
                assert response.status_code == 200
                statuses.append(response.json()["status"])
                time.sleep(0.1)
            
            # All should be consistently healthy
            assert all(status == "healthy" for status in statuses)
            print(f"✅ Health status consistent across {len(statuses)} checks")


class TestFailureIsolation:
    """Test that failures are properly isolated and don't cascade."""
    
    def test_non_critical_service_failure_isolation(self, client):
        """Test that non-critical service failures don't affect critical operations."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            # Critical services healthy
            mock_db.return_value = (True, None)
            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg
            
            # Non-critical services failing
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.side_effect = Exception("Redis failed")
            mock_redis_module.return_value = mock_redis
            mock_publisher.return_value.health_check.side_effect = Exception("Queue failed")
            mock_mlflow_status.return_value = {
                "connected": False,
                "circuit_breaker_state": "OPEN"
            }
            
            # Health endpoint should still work
            response_health = client.get("/health")
            assert response_health.status_code == 200
            
            # Readiness should indicate degraded but still able to serve traffic
            response_ready = client.get("/ready")
            assert response_ready.status_code == 200  # Can still serve traffic
            data = response_ready.json()
            assert data["can_serve_traffic"] is True
            assert data["degraded_mode"] is True
            
            # Liveness should be unaffected
            response_live = client.get("/live")
            assert response_live.status_code == 200
            assert response_live.json()["alive"] is True
            
            print("✅ Non-critical service failures properly isolated")
    
    def test_timeout_handling_isolation(self, client):
        """Test that service timeouts don't cause cascading failures."""
        with patch('src.api.routes.health.check_database_connection') as mock_db, \
             patch('src.api.routes.health._get_redis') as mock_redis_module, \
             patch('src.api.routes.health._get_psycopg2') as mock_pg_module, \
             patch('src.events.publishers.factory.get_publisher') as mock_publisher, \
             patch('src.utils.mlflow_config.get_mlflow_status') as mock_mlflow_status:
            
            # Setup services with timeouts
            mock_db.return_value = (True, None)  # Database works
            
            def slow_redis_ping():
                time.sleep(0.1)  # Simulate slow response
                return True
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.side_effect = slow_redis_ping
            mock_redis_module.return_value = mock_redis
            
            def slow_pg_connect():
                time.sleep(0.1)  # Simulate slow connection
                return Mock(close=Mock())
            mock_pg = Mock()
            mock_pg.connect.side_effect = slow_pg_connect
            mock_pg_module.return_value = mock_pg
            
            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}
            
            def slow_mlflow_status():
                time.sleep(0.1)  # Simulate slow MLflow
                return {
                    "connected": True,
                    "circuit_breaker_state": "CLOSED"
                }
            mock_mlflow_status.side_effect = slow_mlflow_status
            
            start_time = time.time()
            response = client.get("/health")
            end_time = time.time()
            
            # Should complete reasonably quickly despite slow services
            assert response.status_code == 200
            assert end_time - start_time < 5.0  # Should complete within 5 seconds
            assert response.json()["status"] == "healthy"
            
            print(f"✅ Health check completed in {end_time - start_time:.2f}s despite slow services")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])