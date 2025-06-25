"""A/B Testing framework for model comparison"""
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from collections import defaultdict
import statistics


class ABTestException(Exception):
    """Exception raised by A/B testing operations"""
    pass


@dataclass
class TrafficSplit:
    """Traffic split configuration"""
    splits: Dict[str, float]
    
    def __post_init__(self):
        # Validate splits sum to 1.0
        total = sum(self.splits.values())
        if abs(total - 1.0) > 0.001:
            raise ABTestException(f"Traffic split must sum to 1.0, got {total}")
        
        # Validate all values are between 0 and 1
        for model, split in self.splits.items():
            if not 0 <= split <= 1:
                raise ABTestException("Traffic split values must be between 0 and 1")


@dataclass
class ABTestConfig:
    """Configuration for an A/B test"""
    test_id: str
    traffic_split: Dict[str, float]
    duration_hours: int = 24
    model_a: Optional[str] = None
    model_b: Optional[str] = None
    models: Optional[List[str]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        # Handle both binary and multi-variant tests
        if self.model_a and self.model_b:
            # Binary test
            if self.models:
                raise ABTestException("Cannot specify both binary and multi-variant models")
            self.models = [self.model_a, self.model_b]
            
            # Validate traffic split keys
            if set(self.traffic_split.keys()) != {"model_a", "model_b"}:
                raise ABTestException("Traffic split keys must be 'model_a' and 'model_b' for binary test")
        elif self.models:
            # Multi-variant test
            if self.model_a or self.model_b:
                raise ABTestException("Cannot specify both binary and multi-variant models")
            
            # Validate traffic split keys match models
            expected_keys = set(self.models)
            actual_keys = set(self.traffic_split.keys())
            if expected_keys != actual_keys:
                # Also check for model_a/model_b pattern in multi-variant
                if "model_a" in actual_keys and "model_b" in actual_keys and len(self.models) == 2:
                    # Convert to model names
                    new_split = {
                        self.models[0]: self.traffic_split["model_a"],
                        self.models[1]: self.traffic_split["model_b"]
                    }
                    self.traffic_split = new_split
                else:
                    raise ABTestException(f"Traffic split keys must match models: {expected_keys}")
        else:
            raise ABTestException("Must specify either binary (model_a, model_b) or multi-variant (models)")
        
        # Validate traffic split
        TrafficSplit(self.traffic_split)
    
    def is_expired(self) -> bool:
        """Check if the test has expired"""
        expiry = self.created_at + timedelta(hours=self.duration_hours)
        return datetime.utcnow() > expiry


@dataclass
class ABTestResult:
    """Results of an A/B test"""
    test_id: str
    model_a: str
    model_b: str
    metrics_comparison: Dict[str, Dict[str, float]]
    winner: Optional[str] = None
    confidence_level: float = 0.0
    total_requests: Dict[str, int] = field(default_factory=dict)


class ModelTrafficRouter:
    """Routes traffic between models for A/B testing"""
    
    def __init__(self):
        self.active_tests: Dict[str, ABTestConfig] = {}
        self.test_metrics: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        self.request_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    
    def create_ab_test(self, config: ABTestConfig) -> str:
        """Create a new A/B test"""
        if config.test_id in self.active_tests:
            raise ABTestException(f"Test {config.test_id} already exists")
        
        self.active_tests[config.test_id] = config
        return config.test_id
    
    def route_request(self, test_id: str, user_id: str) -> str:
        """Route a request to a model based on user ID"""
        test = self.get_active_test(test_id)
        if not test:
            raise ABTestException(f"No active test found: {test_id}")
        
        # Deterministic routing based on user ID
        hash_input = f"{test_id}:{user_id}".encode()
        hash_value = int(hashlib.md5(hash_input).hexdigest(), 16)
        normalized = (hash_value % 10000) / 10000.0
        
        # Determine which model based on traffic split
        cumulative = 0.0
        if test.model_a and test.model_b:
            # Binary test
            cumulative += test.traffic_split.get("model_a", 0.5)
            if normalized < cumulative:
                selected = test.model_a
            else:
                selected = test.model_b
        else:
            # Multi-variant test
            for model in test.models:
                cumulative += test.traffic_split.get(model, 0)
                if normalized < cumulative:
                    selected = model
                    break
            else:
                selected = test.models[-1]  # Fallback to last model
        
        # Track request count
        self.request_counts[test_id][selected] += 1
        
        return selected
    
    def get_active_test(self, test_id: str) -> Optional[ABTestConfig]:
        """Get an active test, checking for expiry"""
        if test_id not in self.active_tests:
            return None
        
        test = self.active_tests[test_id]
        
        # Check if expired
        if test.is_expired():
            self.stop_ab_test(test_id)
            return None
        
        return test
    
    def stop_ab_test(self, test_id: str) -> None:
        """Stop an A/B test"""
        if test_id in self.active_tests:
            del self.active_tests[test_id]
    
    def record_metric(
        self,
        test_id: str,
        model_id: str,
        metric_name: str,
        value: float
    ) -> None:
        """Record a metric for a model in a test"""
        if test_id not in self.active_tests:
            return  # Silently ignore metrics for non-active tests
        
        self.test_metrics[test_id][f"{model_id}:{metric_name}"].append(value)
    
    def get_test_metrics(self, test_id: str) -> Dict[str, Dict[str, List[float]]]:
        """Get all metrics for a test"""
        if test_id not in self.test_metrics:
            return {}
        
        # Organize by model
        result = defaultdict(dict)
        for key, values in self.test_metrics[test_id].items():
            model_id, metric_name = key.split(":", 1)
            result[model_id][metric_name] = values
        
        return dict(result)
    
    def get_ab_test_results(self, test_id: str) -> ABTestResult:
        """Get results of an A/B test with statistical analysis"""
        test = self.active_tests.get(test_id)
        if not test:
            raise ABTestException(f"Test {test_id} not found")
        
        metrics = self.get_test_metrics(test_id)
        
        # For binary tests only (simplified for now)
        if not (test.model_a and test.model_b):
            raise ABTestException("Results only available for binary tests currently")
        
        model_a = test.model_a
        model_b = test.model_b
        
        # Compare metrics
        metrics_comparison = {}
        winner = None
        confidence = 0.0
        
        for metric_name in set(
            list(metrics.get(model_a, {}).keys()) + 
            list(metrics.get(model_b, {}).keys())
        ):
            values_a = metrics.get(model_a, {}).get(metric_name, [])
            values_b = metrics.get(model_b, {}).get(metric_name, [])
            
            if values_a and values_b:
                mean_a = statistics.mean(values_a)
                mean_b = statistics.mean(values_b)
                
                # Simple statistical test (in production, use proper statistical tests)
                improvement = (mean_b - mean_a) / mean_a if mean_a != 0 else 0
                
                metrics_comparison[metric_name] = {
                    "mean_a": mean_a,
                    "mean_b": mean_b,
                    "improvement": improvement,
                    "samples_a": len(values_a),
                    "samples_b": len(values_b)
                }
                
                # Determine winner based on accuracy (simplified)
                if metric_name == "accuracy" and improvement > 0.01:
                    winner = model_b
                    confidence = min(0.95, abs(improvement) * 10)  # Simplified confidence
        
        return ABTestResult(
            test_id=test_id,
            model_a=model_a,
            model_b=model_b,
            metrics_comparison=metrics_comparison,
            winner=winner,
            confidence_level=confidence,
            total_requests=dict(self.request_counts.get(test_id, {}))
        )
    
    def list_active_tests(self) -> List[str]:
        """List all active test IDs"""
        # Clean up expired tests first
        expired = [
            test_id for test_id, test in self.active_tests.items()
            if test.is_expired()
        ]
        for test_id in expired:
            self.stop_ab_test(test_id)
        
        return list(self.active_tests.keys())
    
    def update_traffic_split(self, test_id: str, new_split: Dict[str, float]) -> None:
        """Update traffic split for an active test"""
        test = self.get_active_test(test_id)
        if not test:
            raise ABTestException(f"Test {test_id} not found or expired")
        
        # Validate new split
        TrafficSplit(new_split)
        
        # Update the configuration
        test.traffic_split = new_split