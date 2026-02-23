"""
Load test script for service capacity and behavior under stress.

Tests service performance, rate limiting, and graceful degradation under load.
"""

import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.health import router

pytestmark = pytest.mark.integration


@dataclass
class LoadTestResult:
    """Result of a load test execution."""

    total_requests: int
    successful_requests: int
    failed_requests: int
    average_response_time: float
    min_response_time: float
    max_response_time: float
    p95_response_time: float
    p99_response_time: float
    requests_per_second: float
    error_rate: float
    errors_by_type: Dict[str, int]
    duration_seconds: float


@dataclass
class ConcurrentTestConfig:
    """Configuration for concurrent load tests."""

    num_threads: int
    requests_per_thread: int
    endpoint: str
    timeout: float = 30.0
    think_time: float = 0.0  # Delay between requests


class LoadTestRunner:
    """Run load tests against service endpoints."""

    def __init__(self, client: TestClient):
        self.client = client

    def run_sequential_load_test(
        self, endpoint: str, num_requests: int, timeout: float = 10.0
    ) -> LoadTestResult:
        """Run sequential load test against an endpoint."""
        response_times = []
        successful_requests = 0
        failed_requests = 0
        errors_by_type = {}

        start_time = time.time()

        for i in range(num_requests):
            try:
                request_start = time.time()
                response = self.client.get(endpoint, timeout=timeout)
                request_end = time.time()

                response_time = (request_end - request_start) * 1000  # Convert to ms
                response_times.append(response_time)

                if response.status_code < 400:
                    successful_requests += 1
                else:
                    failed_requests += 1
                    error_type = f"HTTP_{response.status_code}"
                    errors_by_type[error_type] = errors_by_type.get(error_type, 0) + 1

            except Exception as e:
                failed_requests += 1
                error_type = type(e).__name__
                errors_by_type[error_type] = errors_by_type.get(error_type, 0) + 1

        end_time = time.time()
        duration = end_time - start_time

        return LoadTestResult(
            total_requests=num_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            average_response_time=statistics.mean(response_times) if response_times else 0,
            min_response_time=min(response_times) if response_times else 0,
            max_response_time=max(response_times) if response_times else 0,
            p95_response_time=self._percentile(response_times, 95) if response_times else 0,
            p99_response_time=self._percentile(response_times, 99) if response_times else 0,
            requests_per_second=num_requests / duration if duration > 0 else 0,
            error_rate=(failed_requests / num_requests) * 100 if num_requests > 0 else 0,
            errors_by_type=errors_by_type,
            duration_seconds=duration,
        )

    def run_concurrent_load_test(self, config: ConcurrentTestConfig) -> LoadTestResult:
        """Run concurrent load test with multiple threads."""
        all_response_times = []
        total_successful = 0
        total_failed = 0
        all_errors = {}

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=config.num_threads) as executor:
            # Submit all thread tasks
            futures = []
            for i in range(config.num_threads):
                future = executor.submit(
                    self._thread_worker,
                    config.endpoint,
                    config.requests_per_thread,
                    config.timeout,
                    config.think_time,
                )
                futures.append(future)

            # Collect results
            for future in as_completed(futures):
                try:
                    thread_result = future.result()
                    all_response_times.extend(thread_result["response_times"])
                    total_successful += thread_result["successful"]
                    total_failed += thread_result["failed"]

                    # Merge error counts
                    for error_type, count in thread_result["errors"].items():
                        all_errors[error_type] = all_errors.get(error_type, 0) + count

                except Exception as e:
                    total_failed += config.requests_per_thread
                    error_type = type(e).__name__
                    all_errors[error_type] = (
                        all_errors.get(error_type, 0) + config.requests_per_thread
                    )

        end_time = time.time()
        duration = end_time - start_time
        total_requests = config.num_threads * config.requests_per_thread

        return LoadTestResult(
            total_requests=total_requests,
            successful_requests=total_successful,
            failed_requests=total_failed,
            average_response_time=statistics.mean(all_response_times) if all_response_times else 0,
            min_response_time=min(all_response_times) if all_response_times else 0,
            max_response_time=max(all_response_times) if all_response_times else 0,
            p95_response_time=self._percentile(all_response_times, 95) if all_response_times else 0,
            p99_response_time=self._percentile(all_response_times, 99) if all_response_times else 0,
            requests_per_second=total_requests / duration if duration > 0 else 0,
            error_rate=(total_failed / total_requests) * 100 if total_requests > 0 else 0,
            errors_by_type=all_errors,
            duration_seconds=duration,
        )

    def _thread_worker(
        self, endpoint: str, num_requests: int, timeout: float, think_time: float
    ) -> Dict[str, Any]:
        """Worker function for concurrent load testing."""
        response_times = []
        successful = 0
        failed = 0
        errors = {}

        for i in range(num_requests):
            try:
                request_start = time.time()
                response = self.client.get(endpoint, timeout=timeout)
                request_end = time.time()

                response_time = (request_end - request_start) * 1000
                response_times.append(response_time)

                if response.status_code < 400:
                    successful += 1
                else:
                    failed += 1
                    error_type = f"HTTP_{response.status_code}"
                    errors[error_type] = errors.get(error_type, 0) + 1

                if think_time > 0:
                    time.sleep(think_time)

            except Exception as e:
                failed += 1
                error_type = type(e).__name__
                errors[error_type] = errors.get(error_type, 0) + 1

        return {
            "response_times": response_times,
            "successful": successful,
            "failed": failed,
            "errors": errors,
        }

    def _percentile(self, data: List[float], percentile: float) -> float:
        """Calculate percentile of response times."""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int((percentile / 100.0) * len(sorted_data))
        index = min(index, len(sorted_data) - 1)
        return sorted_data[index]


@pytest.fixture
def app():
    """Create FastAPI test app for load testing."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client for load testing."""
    return TestClient(app)


@pytest.fixture
def load_test_runner(client):
    """Create load test runner."""
    return LoadTestRunner(client)


class TestServiceLoadCapacity:
    """Test service capacity under various load conditions."""

    def test_health_endpoint_sequential_load(self, load_test_runner):
        """Test health endpoint under sequential load."""
        with (
            patch("src.api.routes.health.check_database_connection") as mock_db,
            patch("src.api.routes.health._get_redis") as mock_redis_module,
            patch("src.api.routes.health._get_psycopg2") as mock_pg_module,
            patch("src.events.publishers.factory.get_publisher") as mock_publisher,
            patch("src.utils.mlflow_config.get_mlflow_status") as mock_mlflow_status,
        ):
            # Setup healthy services
            self._setup_healthy_services(
                mock_db, mock_redis_module, mock_pg_module, mock_publisher, mock_mlflow_status
            )

            result = load_test_runner.run_sequential_load_test(
                endpoint="/health", num_requests=100, timeout=5.0
            )

            # Assertions for performance
            assert result.successful_requests >= 95  # 95% success rate
            assert result.error_rate <= 5.0
            assert result.average_response_time < 1000  # Less than 1 second average
            assert result.p95_response_time < 2000  # 95th percentile under 2 seconds
            assert result.requests_per_second > 10  # At least 10 RPS

            print("Sequential Load Test Results:")
            print(f"  Successful requests: {result.successful_requests}/{result.total_requests}")
            print(f"  Average response time: {result.average_response_time:.2f}ms")
            print(f"  95th percentile: {result.p95_response_time:.2f}ms")
            print(f"  Requests per second: {result.requests_per_second:.2f}")
            print(f"  Error rate: {result.error_rate:.2f}%")

    def test_health_endpoint_concurrent_load(self, load_test_runner):
        """Test health endpoint under concurrent load."""
        with (
            patch("src.api.routes.health.check_database_connection") as mock_db,
            patch("src.api.routes.health._get_redis") as mock_redis_module,
            patch("src.api.routes.health._get_psycopg2") as mock_pg_module,
            patch("src.events.publishers.factory.get_publisher") as mock_publisher,
            patch("src.utils.mlflow_config.get_mlflow_status") as mock_mlflow_status,
        ):
            self._setup_healthy_services(
                mock_db, mock_redis_module, mock_pg_module, mock_publisher, mock_mlflow_status
            )

            config = ConcurrentTestConfig(
                num_threads=10, requests_per_thread=20, endpoint="/health", timeout=10.0
            )

            result = load_test_runner.run_concurrent_load_test(config)

            # Assertions for concurrent load
            assert result.successful_requests >= 180  # 90% success rate under load
            assert result.error_rate <= 10.0
            assert result.average_response_time < 2000  # Less than 2 seconds average
            assert result.p99_response_time < 5000  # 99th percentile under 5 seconds

            print("Concurrent Load Test Results:")
            print(
                f"  Threads: {config.num_threads}, Requests per thread: {config.requests_per_thread}"
            )
            print(f"  Successful requests: {result.successful_requests}/{result.total_requests}")
            print(f"  Average response time: {result.average_response_time:.2f}ms")
            print(f"  99th percentile: {result.p99_response_time:.2f}ms")
            print(f"  Requests per second: {result.requests_per_second:.2f}")
            print(f"  Error rate: {result.error_rate:.2f}%")

    def test_detailed_health_endpoint_load(self, load_test_runner):
        """Test detailed health endpoint under load (more expensive operation)."""
        with (
            patch("src.api.routes.health.check_database_connection") as mock_db,
            patch("src.api.routes.health._get_redis") as mock_redis_module,
            patch("src.api.routes.health._get_psycopg2") as mock_pg_module,
            patch("src.events.publishers.factory.get_publisher") as mock_publisher,
            patch("src.utils.mlflow_config.get_mlflow_status") as mock_mlflow_status,
            patch("psutil.cpu_percent") as mock_cpu,
            patch("psutil.virtual_memory") as mock_memory,
        ):
            self._setup_healthy_services(
                mock_db, mock_redis_module, mock_pg_module, mock_publisher, mock_mlflow_status
            )
            mock_cpu.return_value = 25.5
            mock_memory.return_value = Mock(percent=45.2)

            result = load_test_runner.run_sequential_load_test(
                endpoint="/health?detailed=true", num_requests=50, timeout=10.0
            )

            # More lenient assertions for detailed endpoint
            assert result.successful_requests >= 45  # 90% success rate
            assert result.error_rate <= 10.0
            assert result.average_response_time < 3000  # Less than 3 seconds average

            print("Detailed Health Endpoint Load Test:")
            print(f"  Successful requests: {result.successful_requests}/{result.total_requests}")
            print(f"  Average response time: {result.average_response_time:.2f}ms")
            print(f"  Error rate: {result.error_rate:.2f}%")

    def test_readiness_endpoint_load(self, load_test_runner):
        """Test readiness endpoint under load."""
        with (
            patch("src.api.routes.health.check_database_connection") as mock_db,
            patch("src.api.routes.health.check_mlflow_connection") as mock_mlflow,
            patch("src.utils.mlflow_config.get_mlflow_status") as mock_mlflow_status,
        ):
            mock_db.return_value = (True, None)
            mock_mlflow.return_value = (True, None)
            mock_mlflow_status.return_value = {"connected": True, "circuit_breaker_state": "CLOSED"}

            config = ConcurrentTestConfig(
                num_threads=5, requests_per_thread=30, endpoint="/ready", timeout=5.0
            )

            result = load_test_runner.run_concurrent_load_test(config)

            assert result.successful_requests >= 140  # 93% success rate
            assert result.error_rate <= 7.0
            assert result.average_response_time < 1500

            print("Readiness Endpoint Load Test:")
            print(f"  Successful requests: {result.successful_requests}/{result.total_requests}")
            print(f"  Average response time: {result.average_response_time:.2f}ms")

    def test_mixed_endpoint_load(self, load_test_runner):
        """Test mixed endpoint load to simulate real traffic patterns."""
        with (
            patch("src.api.routes.health.check_database_connection") as mock_db,
            patch("src.api.routes.health._get_redis") as mock_redis_module,
            patch("src.api.routes.health._get_psycopg2") as mock_pg_module,
            patch("src.events.publishers.factory.get_publisher") as mock_publisher,
            patch("src.utils.mlflow_config.get_mlflow_status") as mock_mlflow_status,
            patch("src.api.routes.health.check_mlflow_connection") as mock_mlflow_conn,
        ):
            self._setup_healthy_services(
                mock_db, mock_redis_module, mock_pg_module, mock_publisher, mock_mlflow_status
            )
            mock_mlflow_conn.return_value = (True, None)

            endpoints = ["/health", "/ready", "/live", "/version"]
            results = {}

            for endpoint in endpoints:
                result = load_test_runner.run_sequential_load_test(
                    endpoint=endpoint, num_requests=25, timeout=5.0
                )
                results[endpoint] = result

                # Basic assertions for each endpoint
                assert (
                    result.error_rate <= 10.0
                ), f"{endpoint} has high error rate: {result.error_rate}%"
                assert (
                    result.average_response_time < 2000
                ), f"{endpoint} too slow: {result.average_response_time}ms"

            print("Mixed Endpoint Load Test Results:")
            for endpoint, result in results.items():
                print(
                    f"  {endpoint}: {result.successful_requests}/{result.total_requests} "
                    f"({result.average_response_time:.1f}ms avg)"
                )

    def test_load_with_degraded_services(self, load_test_runner):
        """Test load behavior when services are degraded."""
        with (
            patch("src.api.routes.health.check_database_connection") as mock_db,
            patch("src.api.routes.health._get_redis") as mock_redis_module,
            patch("src.api.routes.health._get_psycopg2") as mock_pg_module,
            patch("src.events.publishers.factory.get_publisher") as mock_publisher,
            patch("src.utils.mlflow_config.get_mlflow_status") as mock_mlflow_status,
        ):
            # Setup degraded services
            mock_db.return_value = (True, None)  # DB still working

            # MLflow circuit breaker is OPEN
            mock_mlflow_status.return_value = {
                "connected": False,
                "circuit_breaker_state": "OPEN",
                "error": "Circuit breaker is OPEN",
            }

            # Redis is slow/timing out
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.side_effect = Exception("Redis timeout")
            mock_redis_module.return_value = mock_redis

            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg

            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}

            result = load_test_runner.run_sequential_load_test(
                endpoint="/health", num_requests=50, timeout=10.0
            )

            # Should still respond even with degraded services
            assert result.successful_requests >= 40  # 80% success rate
            assert result.error_rate <= 20.0
            # Response times may be higher due to timeouts
            assert result.average_response_time < 8000

            print("Degraded Services Load Test:")
            print(f"  Successful requests: {result.successful_requests}/{result.total_requests}")
            print(f"  Average response time: {result.average_response_time:.2f}ms")
            print(f"  Error rate: {result.error_rate:.2f}%")

    def test_spike_load_resilience(self, load_test_runner):
        """Test service resilience under sudden load spikes."""
        with (
            patch("src.api.routes.health.check_database_connection") as mock_db,
            patch("src.api.routes.health._get_redis") as mock_redis_module,
            patch("src.api.routes.health._get_psycopg2") as mock_pg_module,
            patch("src.events.publishers.factory.get_publisher") as mock_publisher,
            patch("src.utils.mlflow_config.get_mlflow_status") as mock_mlflow_status,
        ):
            self._setup_healthy_services(
                mock_db, mock_redis_module, mock_pg_module, mock_publisher, mock_mlflow_status
            )

            # Simulate spike with high concurrency
            config = ConcurrentTestConfig(
                num_threads=20,  # High concurrency
                requests_per_thread=10,
                endpoint="/health",
                timeout=15.0,
                think_time=0.0,  # No delay between requests
            )

            result = load_test_runner.run_concurrent_load_test(config)

            # Should handle spike gracefully
            assert result.successful_requests >= 160  # 80% success rate during spike
            assert result.error_rate <= 20.0
            # Higher response times expected during spike
            assert result.average_response_time < 5000

            print("Spike Load Test Results:")
            print(f"  Concurrent threads: {config.num_threads}")
            print(f"  Successful requests: {result.successful_requests}/{result.total_requests}")
            print(f"  Average response time: {result.average_response_time:.2f}ms")
            print(f"  Max response time: {result.max_response_time:.2f}ms")
            print(f"  Error rate: {result.error_rate:.2f}%")

    def _setup_healthy_services(
        self, mock_db, mock_redis_module, mock_pg_module, mock_publisher, mock_mlflow_status
    ):
        """Setup all services as healthy for load testing."""
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
            "circuit_breaker_state": "CLOSED",
            "response_time_ms": 50.0,
        }


class TestServiceCapacityLimits:
    """Test service behavior at capacity limits."""

    def test_response_time_under_sustained_load(self, load_test_runner):
        """Test that response times remain reasonable under sustained load."""
        with (
            patch("src.api.routes.health.check_database_connection") as mock_db,
            patch("src.api.routes.health._get_redis") as mock_redis_module,
            patch("src.api.routes.health._get_psycopg2") as mock_pg_module,
            patch("src.events.publishers.factory.get_publisher") as mock_publisher,
            patch("src.utils.mlflow_config.get_mlflow_status") as mock_mlflow_status,
        ):
            # Setup services with slight delays to simulate real conditions
            mock_db.return_value = (True, None)

            def slow_mlflow_status():
                time.sleep(0.01)  # 10ms delay
                return {
                    "connected": True,
                    "circuit_breaker_state": "CLOSED",
                    "response_time_ms": 100.0,
                }

            mock_mlflow_status.side_effect = slow_mlflow_status

            def slow_redis_ping():
                time.sleep(0.005)  # 5ms delay
                return True

            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.side_effect = slow_redis_ping
            mock_redis_module.return_value = mock_redis

            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg

            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}

            # Run sustained load
            config = ConcurrentTestConfig(
                num_threads=8,
                requests_per_thread=25,
                endpoint="/health",
                timeout=10.0,
                think_time=0.1,  # Small think time for sustained load
            )

            result = load_test_runner.run_concurrent_load_test(config)

            # Performance should degrade gracefully
            assert result.successful_requests >= 160  # 80% success rate
            assert result.average_response_time < 3000  # Average under 3 seconds
            assert result.p95_response_time < 6000  # 95th percentile under 6 seconds

            print("Sustained Load Test Results:")
            print(f"  Duration: {result.duration_seconds:.1f}s")
            print(f"  Average response time: {result.average_response_time:.2f}ms")
            print(f"  95th percentile: {result.p95_response_time:.2f}ms")
            print(f"  Throughput: {result.requests_per_second:.2f} RPS")

    def test_memory_pressure_simulation(self, load_test_runner):
        """Test service behavior under simulated memory pressure."""
        with (
            patch("src.api.routes.health.check_database_connection") as mock_db,
            patch("src.api.routes.health._get_redis") as mock_redis_module,
            patch("src.api.routes.health._get_psycopg2") as mock_pg_module,
            patch("src.events.publishers.factory.get_publisher") as mock_publisher,
            patch("src.utils.mlflow_config.get_mlflow_status") as mock_mlflow_status,
            patch("psutil.virtual_memory") as mock_memory,
        ):
            # Simulate high memory usage
            mock_memory.return_value = Mock(percent=85.0)  # 85% memory usage

            # Setup other services
            mock_db.return_value = (True, None)
            mock_redis = Mock()
            mock_redis.Redis.return_value.ping.return_value = True
            mock_redis_module.return_value = mock_redis
            mock_pg = Mock()
            mock_pg.connect.return_value.close.return_value = None
            mock_pg_module.return_value = mock_pg
            mock_publisher.return_value.health_check.return_value = {"status": "healthy"}
            mock_mlflow_status.return_value = {"connected": True, "circuit_breaker_state": "CLOSED"}

            result = load_test_runner.run_sequential_load_test(
                endpoint="/health?detailed=true", num_requests=30, timeout=15.0
            )

            # Should still function under memory pressure
            assert result.successful_requests >= 25  # 83% success rate
            assert result.error_rate <= 17.0

            print("Memory Pressure Test Results:")
            print(f"  Successful requests: {result.successful_requests}/{result.total_requests}")
            print(f"  Error rate: {result.error_rate:.2f}%")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
