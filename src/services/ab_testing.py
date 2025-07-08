"""A/B testing framework for model comparison and traffic routing."""

import json
import random
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import redis
import numpy as np

logger = logging.getLogger(__name__)


class ABTestStatus(Enum):
    """Status of an A/B test."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RoutingStrategy(Enum):
    """Traffic routing strategies for A/B tests."""

    RANDOM = "random"  # Random assignment
    DETERMINISTIC = "deterministic"  # Hash-based assignment
    STICKY = "sticky"  # User stays with same variant
    WEIGHTED = "weighted"  # Weighted random assignment


@dataclass
class ABTestConfig:
    """Configuration for an A/B test."""

    test_id: str
    test_name: str
    model_a: str  # Model ID/version (control)
    model_b: str  # Model ID/version (variant)
    traffic_split: Dict[str, float]  # {"model_a": 0.5, "model_b": 0.5}
    routing_strategy: RoutingStrategy
    start_time: datetime
    end_time: Optional[datetime]
    success_metrics: List[str]
    minimum_sample_size: int
    confidence_level: float = 0.95
    user_segments: Optional[Dict[str, Any]] = None
    status: ABTestStatus = ABTestStatus.DRAFT

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data["routing_strategy"] = self.routing_strategy.value
        data["status"] = self.status.value
        data["start_time"] = self.start_time.isoformat()
        if self.end_time:
            data["end_time"] = self.end_time.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ABTestConfig":
        """Create from dictionary."""
        data["routing_strategy"] = RoutingStrategy(data["routing_strategy"])
        data["status"] = ABTestStatus(data["status"])
        data["start_time"] = datetime.fromisoformat(data["start_time"])
        if data.get("end_time"):
            data["end_time"] = datetime.fromisoformat(data["end_time"])
        return cls(**data)


@dataclass
class ABTestMetrics:
    """Metrics collected during an A/B test."""

    test_id: str
    variant: str  # 'model_a' or 'model_b'
    total_requests: int = 0
    successful_predictions: int = 0
    failed_predictions: int = 0
    total_latency_ms: float = 0.0
    cache_hits: int = 0
    custom_metrics: Dict[str, float] = None

    def __post_init__(self):
        if self.custom_metrics is None:
            self.custom_metrics = {}

    @property
    def average_latency_ms(self) -> float:
        """Calculate average latency."""
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 0.0
        return self.successful_predictions / self.total_requests


class ModelTrafficRouter:
    """Routes traffic between models for A/B testing."""

    def __init__(self, redis_client: redis.Redis):
        """Initialize the traffic router.
        
        Args:
            redis_client: Redis client for storing routing rules and assignments

        """
        self.redis = redis_client
        self.routing_rules = {}
        self._load_active_tests()

    def create_ab_test(self, test_config: ABTestConfig) -> str:
        """Create a new A/B test configuration.
        
        Args:
            test_config: A/B test configuration
            
        Returns:
            Test ID

        """
        # Validate traffic split
        total_split = sum(test_config.traffic_split.values())
        if abs(total_split - 1.0) > 0.001:
            raise ValueError(f"Traffic split must sum to 1.0, got {total_split}")

        # Store test configuration
        test_key = f"ab_test:{test_config.test_id}"
        self.redis.set(test_key, json.dumps(test_config.to_dict()))

        # Add to active tests if status is ACTIVE
        if test_config.status == ABTestStatus.ACTIVE:
            self.redis.sadd("active_ab_tests", test_config.test_id)
            self.routing_rules[test_config.test_id] = test_config

        logger.info(f"Created A/B test: {test_config.test_id}")
        return test_config.test_id

    def route_request(self, request_id: str,
                     model_family: str,
                     user_id: Optional[str] = None,
                     features: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
        """Determine which model to use for a request.
        
        Args:
            request_id: Unique request identifier
            model_family: Model family to route for
            user_id: Optional user identifier for sticky routing
            features: Optional features for segment-based routing
            
        Returns:
            Tuple of (selected_model_id, test_id)

        """
        # Find active test for this model family
        active_test = self._find_active_test(model_family)
        if not active_test:
            # No active test, return default model
            return self._get_default_model(model_family), ""

        # Check if user is in target segment
        if not self._is_in_segment(user_id, features, active_test.user_segments):
            return self._get_default_model(model_family), ""

        # Route based on strategy
        if active_test.routing_strategy == RoutingStrategy.STICKY and user_id:
            model_variant = self._get_sticky_assignment(user_id, active_test)
        elif active_test.routing_strategy == RoutingStrategy.DETERMINISTIC:
            model_variant = self._get_deterministic_assignment(request_id, active_test)
        else:  # RANDOM or WEIGHTED
            model_variant = self._get_random_assignment(active_test)

        # Get actual model ID
        model_id = active_test.model_a if model_variant == "model_a" else active_test.model_b

        # Record assignment
        self._record_assignment(request_id, active_test.test_id, model_variant)

        return model_id, active_test.test_id

    def update_traffic_split(self, test_id: str,
                           splits: Dict[str, float]) -> bool:
        """Update traffic distribution between models.
        
        Args:
            test_id: Test identifier
            splits: New traffic splits
            
        Returns:
            True if successful

        """
        # Validate splits
        total_split = sum(splits.values())
        if abs(total_split - 1.0) > 0.001:
            raise ValueError(f"Traffic split must sum to 1.0, got {total_split}")

        # Load test config
        test_config = self._load_test_config(test_id)
        if not test_config:
            raise ValueError(f"Test {test_id} not found")

        # Update splits
        test_config.traffic_split = splits

        # Save updated config
        test_key = f"ab_test:{test_id}"
        self.redis.set(test_key, json.dumps(test_config.to_dict()))

        # Update in-memory rules if active
        if test_id in self.routing_rules:
            self.routing_rules[test_id] = test_config

        logger.info(f"Updated traffic split for test {test_id}: {splits}")
        return True

    def pause_test(self, test_id: str) -> bool:
        """Pause an active A/B test.
        
        Args:
            test_id: Test identifier
            
        Returns:
            True if successful

        """
        test_config = self._load_test_config(test_id)
        if not test_config:
            return False

        test_config.status = ABTestStatus.PAUSED
        self._save_test_config(test_config)

        # Remove from active tests
        self.redis.srem("active_ab_tests", test_id)
        if test_id in self.routing_rules:
            del self.routing_rules[test_id]

        logger.info(f"Paused A/B test: {test_id}")
        return True

    def resume_test(self, test_id: str) -> bool:
        """Resume a paused A/B test.
        
        Args:
            test_id: Test identifier
            
        Returns:
            True if successful

        """
        test_config = self._load_test_config(test_id)
        if not test_config:
            return False

        test_config.status = ABTestStatus.ACTIVE
        self._save_test_config(test_config)

        # Add to active tests
        self.redis.sadd("active_ab_tests", test_id)
        self.routing_rules[test_id] = test_config

        logger.info(f"Resumed A/B test: {test_id}")
        return True

    def complete_test(self, test_id: str, winner: Optional[str] = None) -> bool:
        """Mark a test as completed.
        
        Args:
            test_id: Test identifier
            winner: Optional winning variant
            
        Returns:
            True if successful

        """
        test_config = self._load_test_config(test_id)
        if not test_config:
            return False

        test_config.status = ABTestStatus.COMPLETED
        test_config.end_time = datetime.utcnow()
        self._save_test_config(test_config)

        # Store winner if specified
        if winner:
            self.redis.set(f"ab_test_winner:{test_id}", winner)

        # Remove from active tests
        self.redis.srem("active_ab_tests", test_id)
        if test_id in self.routing_rules:
            del self.routing_rules[test_id]

        logger.info(f"Completed A/B test: {test_id}, winner: {winner}")
        return True

    def get_test_metrics(self, test_id: str) -> Dict[str, ABTestMetrics]:
        """Get metrics for an A/B test.
        
        Args:
            test_id: Test identifier
            
        Returns:
            Dictionary mapping variant to metrics

        """
        metrics = {}

        for variant in ["model_a", "model_b"]:
            key = f"ab_metrics:{test_id}:{variant}"
            data = self.redis.get(key)

            if data:
                metrics_data = json.loads(data)
                metrics[variant] = ABTestMetrics(**metrics_data)
            else:
                metrics[variant] = ABTestMetrics(test_id=test_id, variant=variant)

        return metrics

    def record_prediction_result(self, test_id: str, variant: str,
                               latency_ms: float, success: bool,
                               cache_hit: bool = False,
                               custom_metrics: Optional[Dict[str, float]] = None):
        """Record the result of a prediction for metrics.
        
        Args:
            test_id: Test identifier
            variant: Model variant used
            latency_ms: Prediction latency in milliseconds
            success: Whether prediction was successful
            cache_hit: Whether result was from cache
            custom_metrics: Additional metrics to track

        """
        key = f"ab_metrics:{test_id}:{variant}"

        # Get current metrics
        data = self.redis.get(key)
        if data:
            metrics = ABTestMetrics(**json.loads(data))
        else:
            metrics = ABTestMetrics(test_id=test_id, variant=variant)

        # Update metrics
        metrics.total_requests += 1
        metrics.total_latency_ms += latency_ms
        if success:
            metrics.successful_predictions += 1
        else:
            metrics.failed_predictions += 1
        if cache_hit:
            metrics.cache_hits += 1

        # Update custom metrics
        if custom_metrics:
            for metric_name, value in custom_metrics.items():
                if metric_name in metrics.custom_metrics:
                    # Assuming we want to average custom metrics
                    current_total = metrics.custom_metrics[metric_name] * (metrics.total_requests - 1)
                    metrics.custom_metrics[metric_name] = (current_total + value) / metrics.total_requests
                else:
                    metrics.custom_metrics[metric_name] = value

        # Save updated metrics
        self.redis.set(key, json.dumps(asdict(metrics)))

    def _load_active_tests(self):
        """Load active A/B tests from Redis."""
        active_test_ids = self.redis.smembers("active_ab_tests")

        for test_id in active_test_ids:
            test_id = test_id.decode() if isinstance(test_id, bytes) else test_id
            test_config = self._load_test_config(test_id)
            if test_config and test_config.status == ABTestStatus.ACTIVE:
                self.routing_rules[test_id] = test_config

    def _find_active_test(self, model_family: str) -> Optional[ABTestConfig]:
        """Find active test for a model family."""
        for test_config in self.routing_rules.values():
            # Check if this test is for the requested model family
            if (test_config.status == ABTestStatus.ACTIVE and
                (model_family in test_config.model_a or
                 model_family in test_config.model_b)):
                # Check if test is still valid
                if test_config.end_time and datetime.utcnow() > test_config.end_time:
                    # Test has expired, complete it
                    self.complete_test(test_config.test_id)
                    continue
                return test_config
        return None

    def _get_sticky_assignment(self, user_id: str,
                             test_config: ABTestConfig) -> str:
        """Get sticky assignment for a user."""
        assignment_key = f"ab_assignment:{test_config.test_id}:{user_id}"
        assignment = self.redis.get(assignment_key)

        if assignment:
            return assignment.decode() if isinstance(assignment, bytes) else assignment

        # New assignment
        variant = self._get_random_assignment(test_config)
        self.redis.set(assignment_key, variant, ex=86400 * 30)  # 30 days TTL
        return variant

    def _get_deterministic_assignment(self, request_id: str,
                                    test_config: ABTestConfig) -> str:
        """Get deterministic assignment based on request ID."""
        # Hash the request ID
        hash_value = int(hashlib.md5(request_id.encode()).hexdigest(), 16)

        # Normalize to [0, 1]
        normalized = (hash_value % 10000) / 10000.0

        # Assign based on traffic split
        if normalized < test_config.traffic_split.get("model_a", 0.5):
            return "model_a"
        return "model_b"

    def _get_random_assignment(self, test_config: ABTestConfig) -> str:
        """Get random assignment based on traffic split."""
        rand = random.random()

        if rand < test_config.traffic_split.get("model_a", 0.5):
            return "model_a"
        return "model_b"

    def _is_in_segment(self, user_id: Optional[str],
                      features: Optional[Dict[str, Any]],
                      segments: Optional[Dict[str, Any]]) -> bool:
        """Check if user/request is in target segment."""
        if not segments:
            return True

        # Example segment checks
        if "user_type" in segments and features:
            if features.get("user_type") not in segments["user_type"]:
                return False

        if "regions" in segments and features:
            if features.get("region") not in segments["regions"]:
                return False

        return True

    def _get_default_model(self, model_family: str) -> str:
        """Get default model for a family."""
        # This would typically query the model registry
        # For now, return a placeholder
        return f"{model_family}/production"

    def _record_assignment(self, request_id: str, test_id: str, variant: str):
        """Record variant assignment for a request."""
        key = f"ab_assignment_log:{test_id}:{datetime.utcnow().strftime('%Y%m%d')}"
        self.redis.hincrby(key, variant, 1)
        self.redis.expire(key, 86400 * 7)  # 7 days TTL

    def _load_test_config(self, test_id: str) -> Optional[ABTestConfig]:
        """Load test configuration from Redis."""
        test_key = f"ab_test:{test_id}"
        data = self.redis.get(test_key)

        if data:
            config_dict = json.loads(data)
            return ABTestConfig.from_dict(config_dict)
        return None

    def _save_test_config(self, test_config: ABTestConfig):
        """Save test configuration to Redis."""
        test_key = f"ab_test:{test_config.test_id}"
        self.redis.set(test_key, json.dumps(test_config.to_dict()))


class ABTestAnalyzer:
    """Analyzes A/B test results and provides recommendations."""

    def __init__(self, redis_client: redis.Redis):
        """Initialize the analyzer.
        
        Args:
            redis_client: Redis client for accessing test data

        """
        self.redis = redis_client

    def analyze_test(self, test_id: str) -> Dict[str, Any]:
        """Analyze an A/B test and provide results.
        
        Args:
            test_id: Test identifier
            
        Returns:
            Analysis results including winner recommendation

        """
        # Load test configuration
        test_config = self._load_test_config(test_id)
        if not test_config:
            raise ValueError(f"Test {test_id} not found")

        # Get metrics
        router = ModelTrafficRouter(self.redis)
        metrics = router.get_test_metrics(test_id)

        # Calculate statistical significance
        significance = self._calculate_significance(
            metrics["model_a"],
            metrics["model_b"],
            test_config.confidence_level
        )

        # Determine winner
        winner = self._determine_winner(metrics, significance, test_config)

        # Calculate lift
        lift = self._calculate_lift(metrics)

        return {
            "test_id": test_id,
            "test_name": test_config.test_name,
            "status": test_config.status.value,
            "metrics": {
                "model_a": asdict(metrics["model_a"]),
                "model_b": asdict(metrics["model_b"])
            },
            "statistical_significance": significance,
            "winner": winner,
            "lift": lift,
            "recommendation": self._generate_recommendation(winner, significance, lift),
            "analysis_timestamp": datetime.utcnow().isoformat()
        }

    def _calculate_significance(self, metrics_a: ABTestMetrics,
                              metrics_b: ABTestMetrics,
                              confidence_level: float) -> Dict[str, float]:
        """Calculate statistical significance of results."""
        from scipy import stats

        # Success rate comparison
        n_a = metrics_a.total_requests
        n_b = metrics_b.total_requests

        if n_a == 0 or n_b == 0:
            return {"success_rate_pvalue": 1.0, "is_significant": False}

        # Two-proportion z-test
        successes_a = metrics_a.successful_predictions
        successes_b = metrics_b.successful_predictions

        # Pooled proportion
        p_pool = (successes_a + successes_b) / (n_a + n_b)

        # Standard error
        se = np.sqrt(p_pool * (1 - p_pool) * (1/n_a + 1/n_b))

        if se == 0:
            return {"success_rate_pvalue": 1.0, "is_significant": False}

        # Z-score
        z = (metrics_a.success_rate - metrics_b.success_rate) / se

        # P-value (two-tailed)
        p_value = 2 * (1 - stats.norm.cdf(abs(z)))

        return {
            "success_rate_pvalue": p_value,
            "is_significant": p_value < (1 - confidence_level),
            "z_score": z,
            "sample_size_a": n_a,
            "sample_size_b": n_b
        }

    def _determine_winner(self, metrics: Dict[str, ABTestMetrics],
                        significance: Dict[str, Any],
                        test_config: ABTestConfig) -> Optional[str]:
        """Determine the winning variant."""
        # Check minimum sample size
        if (metrics["model_a"].total_requests < test_config.minimum_sample_size or
            metrics["model_b"].total_requests < test_config.minimum_sample_size):
            return None

        # Check statistical significance
        if not significance["is_significant"]:
            return None

        # Compare success rates
        if metrics["model_a"].success_rate > metrics["model_b"].success_rate:
            return "model_a"
        elif metrics["model_b"].success_rate > metrics["model_a"].success_rate:
            return "model_b"

        return None

    def _calculate_lift(self, metrics: Dict[str, ABTestMetrics]) -> Dict[str, float]:
        """Calculate lift metrics."""
        if metrics["model_a"].success_rate == 0:
            success_rate_lift = float("inf") if metrics["model_b"].success_rate > 0 else 0
        else:
            success_rate_lift = (
                (metrics["model_b"].success_rate - metrics["model_a"].success_rate) /
                metrics["model_a"].success_rate * 100
            )

        if metrics["model_a"].average_latency_ms == 0:
            latency_lift = 0
        else:
            latency_lift = (
                (metrics["model_b"].average_latency_ms - metrics["model_a"].average_latency_ms) /
                metrics["model_a"].average_latency_ms * 100
            )

        return {
            "success_rate_lift_percent": success_rate_lift,
            "latency_lift_percent": latency_lift
        }

    def _generate_recommendation(self, winner: Optional[str],
                               significance: Dict[str, Any],
                               lift: Dict[str, float]) -> str:
        """Generate recommendation based on analysis."""
        if not winner:
            if not significance["is_significant"]:
                return "Continue testing - results not statistically significant"
            return "Continue testing - insufficient sample size"

        if winner == "model_b":
            if lift["success_rate_lift_percent"] > 5:
                return f"Deploy model B - {lift['success_rate_lift_percent']:.1f}% improvement"
            else:
                return "Model B wins but improvement is marginal"
        else:
            return "Keep model A - no significant improvement from model B"

    def _load_test_config(self, test_id: str) -> Optional[ABTestConfig]:
        """Load test configuration from Redis."""
        test_key = f"ab_test:{test_id}"
        data = self.redis.get(test_key)

        if data:
            config_dict = json.loads(data)
            return ABTestConfig.from_dict(config_dict)
        return None
