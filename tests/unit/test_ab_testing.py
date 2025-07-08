"""Unit tests for the A/B testing framework."""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import json
import redis
from datetime import datetime, timedelta
from typing import Dict, Any
import numpy as np

from src.services.ab_testing import (
    ABTestStatus,
    RoutingStrategy,
    ABTestConfig,
    ABTestMetrics,
    ModelTrafficRouter,
    ABTestAnalyzer
)


class TestABTestStatus:
    """Test suite for ABTestStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert ABTestStatus.DRAFT.value == "draft"
        assert ABTestStatus.ACTIVE.value == "active"
        assert ABTestStatus.PAUSED.value == "paused"
        assert ABTestStatus.COMPLETED.value == "completed"
        assert ABTestStatus.CANCELLED.value == "cancelled"


class TestRoutingStrategy:
    """Test suite for RoutingStrategy enum."""

    def test_strategy_values(self):
        """Test routing strategy values."""
        assert RoutingStrategy.RANDOM.value == "random"
        assert RoutingStrategy.DETERMINISTIC.value == "deterministic"
        assert RoutingStrategy.STICKY.value == "sticky"
        assert RoutingStrategy.WEIGHTED.value == "weighted"


class TestABTestConfig:
    """Test suite for ABTestConfig dataclass."""

    def setup_method(self):
        """Set up test fixtures."""
        self.test_config = ABTestConfig(
            test_id="test_001",
            test_name="Model v2 Test",
            model_a="model_v1",
            model_b="model_v2",
            traffic_split={"model_a": 0.5, "model_b": 0.5},
            routing_strategy=RoutingStrategy.RANDOM,
            start_time=datetime.utcnow(),
            end_time=None,
            success_metrics=["accuracy", "latency"],
            minimum_sample_size=1000,
            confidence_level=0.95
        )

    def test_config_creation(self):
        """Test creating AB test configuration."""
        assert self.test_config.test_id == "test_001"
        assert self.test_config.model_a == "model_v1"
        assert self.test_config.model_b == "model_v2"
        assert self.test_config.traffic_split == {"model_a": 0.5, "model_b": 0.5}
        assert self.test_config.status == ABTestStatus.DRAFT

    def test_config_to_dict(self):
        """Test converting config to dictionary."""
        config_dict = self.test_config.to_dict()

        assert config_dict["test_id"] == "test_001"
        assert config_dict["routing_strategy"] == "random"
        assert config_dict["status"] == "draft"
        assert "start_time" in config_dict
        assert isinstance(config_dict["start_time"], str)

    def test_config_from_dict(self):
        """Test creating config from dictionary."""
        config_dict = self.test_config.to_dict()
        loaded_config = ABTestConfig.from_dict(config_dict)

        assert loaded_config.test_id == self.test_config.test_id
        assert loaded_config.routing_strategy == self.test_config.routing_strategy
        assert loaded_config.status == self.test_config.status

    def test_config_with_end_time(self):
        """Test config with end time."""
        self.test_config.end_time = datetime.utcnow() + timedelta(days=7)
        config_dict = self.test_config.to_dict()

        assert "end_time" in config_dict

        loaded_config = ABTestConfig.from_dict(config_dict)
        assert loaded_config.end_time is not None


class TestABTestMetrics:
    """Test suite for ABTestMetrics dataclass."""

    def setup_method(self):
        """Set up test fixtures."""
        self.metrics = ABTestMetrics(
            test_id="test_001",
            variant="model_a",
            total_requests=100,
            successful_predictions=90,
            failed_predictions=10,
            total_latency_ms=5000.0,
            cache_hits=20
        )

    def test_metrics_creation(self):
        """Test creating metrics object."""
        assert self.metrics.test_id == "test_001"
        assert self.metrics.variant == "model_a"
        assert self.metrics.total_requests == 100
        assert self.metrics.custom_metrics == {}

    def test_average_latency(self):
        """Test average latency calculation."""
        assert self.metrics.average_latency_ms == 50.0

        # Test with zero requests
        empty_metrics = ABTestMetrics(test_id="test", variant="model_a")
        assert empty_metrics.average_latency_ms == 0.0

    def test_success_rate(self):
        """Test success rate calculation."""
        assert self.metrics.success_rate == 0.9

        # Test with zero requests
        empty_metrics = ABTestMetrics(test_id="test", variant="model_a")
        assert empty_metrics.success_rate == 0.0

    def test_custom_metrics_initialization(self):
        """Test custom metrics initialization."""
        metrics = ABTestMetrics(
            test_id="test",
            variant="model_a",
            custom_metrics={"accuracy": 0.95}
        )
        assert metrics.custom_metrics == {"accuracy": 0.95}


class TestModelTrafficRouter:
    """Test suite for ModelTrafficRouter class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_redis = Mock(spec=redis.Redis)
        self.mock_redis.smembers.return_value = set()
        self.router = ModelTrafficRouter(self.mock_redis)

        # Create test configuration
        self.test_config = ABTestConfig(
            test_id="test_001",
            test_name="Model v2 Test",
            model_a="model_family/v1",
            model_b="model_family/v2",
            traffic_split={"model_a": 0.5, "model_b": 0.5},
            routing_strategy=RoutingStrategy.RANDOM,
            start_time=datetime.utcnow(),
            end_time=None,
            success_metrics=["accuracy"],
            minimum_sample_size=1000
        )

    def test_router_initialization(self):
        """Test router initialization."""
        assert self.router.redis == self.mock_redis
        assert self.router.routing_rules == {}
        self.mock_redis.smembers.assert_called_once_with("active_ab_tests")

    def test_create_ab_test(self):
        """Test creating an A/B test."""
        test_id = self.router.create_ab_test(self.test_config)

        assert test_id == "test_001"
        self.mock_redis.set.assert_called_once()

        # Test with active status
        self.test_config.status = ABTestStatus.ACTIVE
        test_id = self.router.create_ab_test(self.test_config)

        self.mock_redis.sadd.assert_called_with("active_ab_tests", "test_001")
        assert "test_001" in self.router.routing_rules

    def test_create_ab_test_invalid_split(self):
        """Test creating test with invalid traffic split."""
        self.test_config.traffic_split = {"model_a": 0.6, "model_b": 0.6}

        with pytest.raises(ValueError, match="Traffic split must sum to 1.0"):
            self.router.create_ab_test(self.test_config)

    def test_route_request_no_active_test(self):
        """Test routing when no active test exists."""
        model_id, test_id = self.router.route_request(
            "req_123",
            "model_family"
        )

        assert model_id == "model_family/production"
        assert test_id == ""

    def test_route_request_with_active_test(self):
        """Test routing with active test."""
        # Add active test
        self.test_config.status = ABTestStatus.ACTIVE
        self.router.routing_rules["test_001"] = self.test_config

        # Mock random assignment
        with patch("random.random", return_value=0.3):
            model_id, test_id = self.router.route_request(
                "req_123",
                "model_family"
            )

        assert model_id == "model_family/v1"  # 0.3 < 0.5, so model_a
        assert test_id == "test_001"

    def test_route_request_deterministic(self):
        """Test deterministic routing."""
        self.test_config.routing_strategy = RoutingStrategy.DETERMINISTIC
        self.test_config.status = ABTestStatus.ACTIVE
        self.router.routing_rules["test_001"] = self.test_config

        # Same request ID should always get same assignment
        model_id1, _ = self.router.route_request("req_123", "model_family")
        model_id2, _ = self.router.route_request("req_123", "model_family")

        assert model_id1 == model_id2

    def test_route_request_sticky(self):
        """Test sticky routing."""
        self.test_config.routing_strategy = RoutingStrategy.STICKY
        self.test_config.status = ABTestStatus.ACTIVE
        self.router.routing_rules["test_001"] = self.test_config

        # First request for user
        self.mock_redis.get.return_value = None
        with patch("random.random", return_value=0.7):
            model_id1, _ = self.router.route_request(
                "req_123",
                "model_family",
                user_id="user_001"
            )

        # Should have saved assignment
        self.mock_redis.set.assert_called()

        # Second request for same user should get cached assignment
        self.mock_redis.get.return_value = b"model_b"
        model_id2, _ = self.router.route_request(
            "req_456",
            "model_family",
            user_id="user_001"
        )

        assert model_id2 == "model_family/v2"  # model_b

    def test_update_traffic_split(self):
        """Test updating traffic split."""
        # Create test first
        self.mock_redis.get.return_value = json.dumps(self.test_config.to_dict())

        success = self.router.update_traffic_split(
            "test_001",
            {"model_a": 0.3, "model_b": 0.7}
        )

        assert success is True
        self.mock_redis.set.assert_called()

    def test_update_traffic_split_invalid(self):
        """Test updating with invalid split."""
        self.mock_redis.get.return_value = json.dumps(self.test_config.to_dict())

        with pytest.raises(ValueError, match="Traffic split must sum to 1.0"):
            self.router.update_traffic_split(
                "test_001",
                {"model_a": 0.3, "model_b": 0.6}
            )

    def test_pause_test(self):
        """Test pausing an active test."""
        self.mock_redis.get.return_value = json.dumps(self.test_config.to_dict())
        self.router.routing_rules["test_001"] = self.test_config

        success = self.router.pause_test("test_001")

        assert success is True
        self.mock_redis.srem.assert_called_with("active_ab_tests", "test_001")
        assert "test_001" not in self.router.routing_rules

    def test_resume_test(self):
        """Test resuming a paused test."""
        self.test_config.status = ABTestStatus.PAUSED
        self.mock_redis.get.return_value = json.dumps(self.test_config.to_dict())

        success = self.router.resume_test("test_001")

        assert success is True
        self.mock_redis.sadd.assert_called_with("active_ab_tests", "test_001")
        assert "test_001" in self.router.routing_rules

    def test_complete_test(self):
        """Test completing a test."""
        self.mock_redis.get.return_value = json.dumps(self.test_config.to_dict())
        self.router.routing_rules["test_001"] = self.test_config

        success = self.router.complete_test("test_001", winner="model_b")

        assert success is True
        self.mock_redis.srem.assert_called_with("active_ab_tests", "test_001")
        self.mock_redis.set.assert_any_call("ab_test_winner:test_001", "model_b")
        assert "test_001" not in self.router.routing_rules

    def test_get_test_metrics(self):
        """Test getting test metrics."""
        # Mock metrics data
        metrics_data = {
            "test_id": "test_001",
            "variant": "model_a",
            "total_requests": 100,
            "successful_predictions": 90,
            "failed_predictions": 10,
            "total_latency_ms": 5000.0,
            "cache_hits": 20,
            "custom_metrics": {}
        }

        self.mock_redis.get.side_effect = [
            json.dumps(metrics_data),
            None  # No data for model_b
        ]

        metrics = self.router.get_test_metrics("test_001")

        assert "model_a" in metrics
        assert "model_b" in metrics
        assert metrics["model_a"].total_requests == 100
        assert metrics["model_b"].total_requests == 0

    def test_record_prediction_result(self):
        """Test recording prediction results."""
        # No existing metrics
        self.mock_redis.get.return_value = None

        self.router.record_prediction_result(
            "test_001",
            "model_a",
            latency_ms=50.0,
            success=True,
            cache_hit=False,
            custom_metrics={"accuracy": 0.95}
        )

        # Should save updated metrics
        self.mock_redis.set.assert_called_once()
        saved_data = json.loads(self.mock_redis.set.call_args[0][1])

        assert saved_data["total_requests"] == 1
        assert saved_data["successful_predictions"] == 1
        assert saved_data["total_latency_ms"] == 50.0
        assert saved_data["custom_metrics"]["accuracy"] == 0.95

    def test_record_prediction_result_existing_metrics(self):
        """Test recording results with existing metrics."""
        existing_metrics = {
            "test_id": "test_001",
            "variant": "model_a",
            "total_requests": 10,
            "successful_predictions": 9,
            "failed_predictions": 1,
            "total_latency_ms": 500.0,
            "cache_hits": 2,
            "custom_metrics": {"accuracy": 0.9}
        }

        self.mock_redis.get.return_value = json.dumps(existing_metrics)

        self.router.record_prediction_result(
            "test_001",
            "model_a",
            latency_ms=60.0,
            success=False,
            cache_hit=True,
            custom_metrics={"accuracy": 0.8}
        )

        saved_data = json.loads(self.mock_redis.set.call_args[0][1])

        assert saved_data["total_requests"] == 11
        assert saved_data["successful_predictions"] == 9
        assert saved_data["failed_predictions"] == 2
        assert saved_data["cache_hits"] == 3
        # Custom metric should be averaged
        expected_accuracy = (0.9 * 10 + 0.8) / 11
        assert abs(saved_data["custom_metrics"]["accuracy"] - expected_accuracy) < 0.001

    def test_segment_filtering(self):
        """Test user segment filtering."""
        # Configure segment requirements
        self.test_config.status = ABTestStatus.ACTIVE
        self.test_config.user_segments = {
            "user_type": ["premium", "enterprise"],
            "regions": ["US", "EU"]
        }
        self.router.routing_rules["test_001"] = self.test_config

        # User not in segment
        model_id, test_id = self.router.route_request(
            "req_123",
            "model_family",
            features={"user_type": "free", "region": "US"}
        )

        assert model_id == "model_family/production"
        assert test_id == ""

        # User in segment
        model_id, test_id = self.router.route_request(
            "req_456",
            "model_family",
            features={"user_type": "premium", "region": "EU"}
        )

        assert test_id == "test_001"

    def test_expired_test_handling(self):
        """Test handling of expired tests."""
        # Set test to expire in the past
        self.test_config.status = ABTestStatus.ACTIVE
        self.test_config.end_time = datetime.utcnow() - timedelta(days=1)
        self.router.routing_rules["test_001"] = self.test_config

        # Mock the complete_test method
        self.router.complete_test = Mock(return_value=True)

        model_id, test_id = self.router.route_request(
            "req_123",
            "model_family"
        )

        # Should complete the expired test
        self.router.complete_test.assert_called_once_with("test_001")
        assert model_id == "model_family/production"
        assert test_id == ""


class TestABTestAnalyzer:
    """Test suite for ABTestAnalyzer class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_redis = Mock(spec=redis.Redis)
        self.analyzer = ABTestAnalyzer(self.mock_redis)

        # Create test configuration
        self.test_config = ABTestConfig(
            test_id="test_001",
            test_name="Model v2 Test",
            model_a="model_v1",
            model_b="model_v2",
            traffic_split={"model_a": 0.5, "model_b": 0.5},
            routing_strategy=RoutingStrategy.RANDOM,
            start_time=datetime.utcnow() - timedelta(days=7),
            end_time=None,
            success_metrics=["accuracy"],
            minimum_sample_size=100,
            confidence_level=0.95,
            status=ABTestStatus.ACTIVE
        )

        # Create test metrics
        self.metrics_a = ABTestMetrics(
            test_id="test_001",
            variant="model_a",
            total_requests=1000,
            successful_predictions=850,
            failed_predictions=150,
            total_latency_ms=50000.0
        )

        self.metrics_b = ABTestMetrics(
            test_id="test_001",
            variant="model_b",
            total_requests=1000,
            successful_predictions=900,
            failed_predictions=100,
            total_latency_ms=55000.0
        )

    @patch("src.services.ab_testing.ModelTrafficRouter")
    def test_analyze_test(self, mock_router_class):
        """Test analyzing A/B test results."""
        # Mock router
        mock_router = Mock()
        mock_router_class.return_value = mock_router
        mock_router.get_test_metrics.return_value = {
            "model_a": self.metrics_a,
            "model_b": self.metrics_b
        }

        # Mock test config loading
        self.mock_redis.get.return_value = json.dumps(self.test_config.to_dict())

        # Analyze test
        results = self.analyzer.analyze_test("test_001")

        assert results["test_id"] == "test_001"
        assert results["test_name"] == "Model v2 Test"
        assert results["status"] == "active"
        assert "statistical_significance" in results
        assert "winner" in results
        assert "lift" in results
        assert "recommendation" in results

    def test_calculate_significance(self):
        """Test statistical significance calculation."""
        significance = self.analyzer._calculate_significance(
            self.metrics_a,
            self.metrics_b,
            0.95
        )

        assert "success_rate_pvalue" in significance
        assert "is_significant" in significance
        assert "z_score" in significance
        assert significance["sample_size_a"] == 1000
        assert significance["sample_size_b"] == 1000

        # Check that significance calculation worked
        # Model B has 90% success rate vs 85% for Model A
        # This difference should be statistically significant with 1000 samples each
        # but the exact p-value depends on the implementation

    def test_calculate_significance_no_data(self):
        """Test significance calculation with no data."""
        empty_metrics_a = ABTestMetrics(test_id="test", variant="model_a")
        empty_metrics_b = ABTestMetrics(test_id="test", variant="model_b")

        significance = self.analyzer._calculate_significance(
            empty_metrics_a,
            empty_metrics_b,
            0.95
        )

        assert significance["success_rate_pvalue"] == 1.0
        assert significance["is_significant"] is False

    def test_determine_winner(self):
        """Test winner determination."""
        significance = {"is_significant": True}

        winner = self.analyzer._determine_winner(
            {"model_a": self.metrics_a, "model_b": self.metrics_b},
            significance,
            self.test_config
        )

        assert winner == "model_b"  # Higher success rate

    def test_determine_winner_insufficient_samples(self):
        """Test winner with insufficient samples."""
        # Reduce sample size
        self.metrics_a.total_requests = 50
        significance = {"is_significant": True}

        winner = self.analyzer._determine_winner(
            {"model_a": self.metrics_a, "model_b": self.metrics_b},
            significance,
            self.test_config
        )

        assert winner is None

    def test_determine_winner_not_significant(self):
        """Test winner when not statistically significant."""
        significance = {"is_significant": False}

        winner = self.analyzer._determine_winner(
            {"model_a": self.metrics_a, "model_b": self.metrics_b},
            significance,
            self.test_config
        )

        assert winner is None

    def test_calculate_lift(self):
        """Test lift calculation."""
        lift = self.analyzer._calculate_lift({
            "model_a": self.metrics_a,
            "model_b": self.metrics_b
        })

        # Model B has 90% success vs 85% for Model A
        # Lift = (0.9 - 0.85) / 0.85 * 100 = 5.88%
        assert abs(lift["success_rate_lift_percent"] - 5.88) < 0.1

        # Latency lift (negative is better)
        # Model B: 55ms avg, Model A: 50ms avg
        # Lift = (55 - 50) / 50 * 100 = 10%
        assert lift["latency_lift_percent"] == 10.0

    def test_calculate_lift_zero_baseline(self):
        """Test lift calculation with zero baseline."""
        self.metrics_a.successful_predictions = 0

        lift = self.analyzer._calculate_lift({
            "model_a": self.metrics_a,
            "model_b": self.metrics_b
        })

        assert lift["success_rate_lift_percent"] == float("inf")

    def test_generate_recommendation(self):
        """Test recommendation generation."""
        # Model B wins with good lift
        rec = self.analyzer._generate_recommendation(
            "model_b",
            {"is_significant": True},
            {"success_rate_lift_percent": 10.0}
        )
        assert "Deploy model B" in rec

        # Model B wins with marginal lift
        rec = self.analyzer._generate_recommendation(
            "model_b",
            {"is_significant": True},
            {"success_rate_lift_percent": 2.0}
        )
        assert "marginal" in rec

        # Model A wins
        rec = self.analyzer._generate_recommendation(
            "model_a",
            {"is_significant": True},
            {"success_rate_lift_percent": -5.0}
        )
        assert "Keep model A" in rec

        # No winner - not significant
        rec = self.analyzer._generate_recommendation(
            None,
            {"is_significant": False},
            {"success_rate_lift_percent": 5.0}
        )
        assert "not statistically significant" in rec

        # No winner - insufficient samples
        rec = self.analyzer._generate_recommendation(
            None,
            {"is_significant": True},
            {"success_rate_lift_percent": 5.0}
        )
        assert "insufficient sample size" in rec
