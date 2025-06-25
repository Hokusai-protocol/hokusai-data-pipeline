"""Tests for A/B Testing Framework"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import random
from typing import Dict, List, Optional

from hokusai.core.ab_testing import (
    ModelTrafficRouter,
    ABTestConfig,
    ABTestResult,
    TrafficSplit,
    ABTestException
)
from hokusai.core.registry import ModelRegistry, ModelRegistryEntry


class TestABTestConfig:
    """Test cases for ABTestConfig"""
    
    def test_config_validation(self):
        """Test ABTestConfig validation"""
        # Valid config
        config = ABTestConfig(
            test_id="test-001",
            model_a="model-v1",
            model_b="model-v2",
            traffic_split={"model_a": 0.5, "model_b": 0.5},
            duration_hours=24
        )
        
        assert config.test_id == "test-001"
        assert config.traffic_split["model_a"] == 0.5
        assert config.traffic_split["model_b"] == 0.5
        assert config.duration_hours == 24
    
    def test_invalid_traffic_split(self):
        """Test that invalid traffic splits raise errors"""
        # Splits don't sum to 1.0
        with pytest.raises(ABTestException, match="Traffic split must sum to 1.0"):
            ABTestConfig(
                test_id="test-001",
                model_a="model-v1",
                model_b="model-v2",
                traffic_split={"model_a": 0.6, "model_b": 0.6}
            )
        
        # Negative split values
        with pytest.raises(ABTestException, match="Traffic split values must be between 0 and 1"):
            ABTestConfig(
                test_id="test-001",
                model_a="model-v1",
                model_b="model-v2",
                traffic_split={"model_a": -0.5, "model_b": 1.5}
            )
    
    def test_multi_variant_test(self):
        """Test configuration for multi-variant A/B test"""
        config = ABTestConfig(
            test_id="multi-test-001",
            models=["model-v1", "model-v2", "model-v3"],
            traffic_split={"model-v1": 0.33, "model-v2": 0.33, "model-v3": 0.34},
            duration_hours=48
        )
        
        assert len(config.models) == 3
        assert sum(config.traffic_split.values()) == 1.0


class TestModelTrafficRouter:
    """Test cases for ModelTrafficRouter"""
    
    @pytest.fixture
    def router(self):
        """Create ModelTrafficRouter instance"""
        return ModelTrafficRouter()
    
    def test_create_ab_test(self, router):
        """Test creating a new A/B test"""
        config = ABTestConfig(
            test_id="test-001",
            model_a="model-v1",
            model_b="model-v2",
            traffic_split={"model_a": 0.7, "model_b": 0.3}
        )
        
        test_id = router.create_ab_test(config)
        
        assert test_id == "test-001"
        assert router.get_active_test("test-001") is not None
    
    def test_route_request_deterministic(self, router):
        """Test deterministic request routing based on user ID"""
        config = ABTestConfig(
            test_id="test-001",
            model_a="model-v1",
            model_b="model-v2",
            traffic_split={"model_a": 0.5, "model_b": 0.5}
        )
        
        router.create_ab_test(config)
        
        # Same user ID should always route to same model
        user_id = "user-12345"
        first_route = router.route_request("test-001", user_id)
        
        for _ in range(10):
            assert router.route_request("test-001", user_id) == first_route
    
    def test_traffic_distribution(self, router):
        """Test that traffic is distributed according to split ratios"""
        config = ABTestConfig(
            test_id="test-001",
            model_a="model-v1",
            model_b="model-v2",
            traffic_split={"model_a": 0.7, "model_b": 0.3}
        )
        
        router.create_ab_test(config)
        
        # Route many requests and check distribution
        routes = {"model-v1": 0, "model-v2": 0}
        num_requests = 10000
        
        for i in range(num_requests):
            user_id = f"user-{i}"
            model = router.route_request("test-001", user_id)
            routes[model] += 1
        
        # Check that distribution is within 2% of expected
        model_a_ratio = routes["model-v1"] / num_requests
        model_b_ratio = routes["model-v2"] / num_requests
        
        assert abs(model_a_ratio - 0.7) < 0.02
        assert abs(model_b_ratio - 0.3) < 0.02
    
    def test_stop_ab_test(self, router):
        """Test stopping an A/B test"""
        config = ABTestConfig(
            test_id="test-001",
            model_a="model-v1",
            model_b="model-v2",
            traffic_split={"model_a": 0.5, "model_b": 0.5}
        )
        
        router.create_ab_test(config)
        assert router.get_active_test("test-001") is not None
        
        router.stop_ab_test("test-001")
        assert router.get_active_test("test-001") is None
    
    def test_record_metric(self, router):
        """Test recording metrics during A/B test"""
        config = ABTestConfig(
            test_id="test-001",
            model_a="model-v1",
            model_b="model-v2",
            traffic_split={"model_a": 0.5, "model_b": 0.5}
        )
        
        router.create_ab_test(config)
        
        # Record some metrics
        router.record_metric("test-001", "model-v1", "latency", 125.5)
        router.record_metric("test-001", "model-v1", "accuracy", 0.92)
        router.record_metric("test-001", "model-v2", "latency", 130.2)
        router.record_metric("test-001", "model-v2", "accuracy", 0.94)
        
        metrics = router.get_test_metrics("test-001")
        
        assert "model-v1" in metrics
        assert "model-v2" in metrics
        assert metrics["model-v1"]["latency"] == [125.5]
        assert metrics["model-v1"]["accuracy"] == [0.92]
    
    def test_get_ab_test_results(self, router):
        """Test getting A/B test results with statistical analysis"""
        config = ABTestConfig(
            test_id="test-001",
            model_a="model-v1",
            model_b="model-v2",
            traffic_split={"model_a": 0.5, "model_b": 0.5}
        )
        
        router.create_ab_test(config)
        
        # Simulate recording many metrics
        random.seed(42)
        for _ in range(100):
            router.record_metric("test-001", "model-v1", "accuracy", random.uniform(0.88, 0.92))
            router.record_metric("test-001", "model-v2", "accuracy", random.uniform(0.90, 0.94))
            router.record_metric("test-001", "model-v1", "latency", random.uniform(120, 140))
            router.record_metric("test-001", "model-v2", "latency", random.uniform(125, 145))
        
        results = router.get_ab_test_results("test-001")
        
        assert results.test_id == "test-001"
        assert results.model_a == "model-v1"
        assert results.model_b == "model-v2"
        assert "accuracy" in results.metrics_comparison
        assert "latency" in results.metrics_comparison
        assert results.metrics_comparison["accuracy"]["mean_a"] < results.metrics_comparison["accuracy"]["mean_b"]
        assert results.winner is not None  # Should have a winner based on metrics
    
    def test_auto_stop_expired_test(self, router):
        """Test that tests are automatically stopped after duration"""
        config = ABTestConfig(
            test_id="test-001",
            model_a="model-v1",
            model_b="model-v2",
            traffic_split={"model_a": 0.5, "model_b": 0.5},
            duration_hours=0.001  # Very short duration for testing
        )
        
        router.create_ab_test(config)
        
        # Mock time passing
        with patch('time.time') as mock_time:
            # Start time
            mock_time.return_value = 0
            assert router.get_active_test("test-001") is not None
            
            # After duration
            mock_time.return_value = 3700  # More than 1 hour
            assert router.get_active_test("test-001") is None
    
    def test_concurrent_ab_tests(self, router):
        """Test running multiple A/B tests concurrently"""
        # Create multiple tests
        configs = [
            ABTestConfig(
                test_id=f"test-{i}",
                model_a=f"model-{i}-v1",
                model_b=f"model-{i}-v2",
                traffic_split={"model_a": 0.5, "model_b": 0.5}
            )
            for i in range(3)
        ]
        
        for config in configs:
            router.create_ab_test(config)
        
        # All tests should be active
        assert len(router.list_active_tests()) == 3
        
        # Each test should route independently
        user_id = "user-123"
        routes = [
            router.route_request(f"test-{i}", user_id)
            for i in range(3)
        ]
        
        # Routes should be deterministic but independent
        assert all(isinstance(route, str) for route in routes)
    
    def test_gradual_rollout(self, router):
        """Test gradual rollout by updating traffic split"""
        config = ABTestConfig(
            test_id="rollout-test",
            model_a="old-model",
            model_b="new-model",
            traffic_split={"model_a": 0.95, "model_b": 0.05}
        )
        
        router.create_ab_test(config)
        
        # Update traffic split to give more traffic to new model
        new_split = {"model_a": 0.50, "model_b": 0.50}
        router.update_traffic_split("rollout-test", new_split)
        
        # Verify new distribution
        routes = {"old-model": 0, "new-model": 0}
        for i in range(1000):
            model = router.route_request("rollout-test", f"user-{i}")
            routes[model] += 1
        
        new_model_ratio = routes["new-model"] / 1000
        assert abs(new_model_ratio - 0.50) < 0.05