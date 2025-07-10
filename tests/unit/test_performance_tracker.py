"""Unit tests for performance tracker service."""

import hashlib
import json
from datetime import datetime
from unittest.mock import patch

import pytest

from src.services.performance_tracker import PerformanceTracker


class TestPerformanceTracker:
    """Test suite for PerformanceTracker class."""

    def test_initialization(self):
        """Test performance tracker initialization."""
        tracker = PerformanceTracker()
        assert tracker is not None

    @patch("mlflow.log_metrics")
    @patch("mlflow.log_dict")
    def test_track_improvement(self, mock_log_dict, mock_log_metrics):
        """Test tracking performance improvement."""
        tracker = PerformanceTracker()

        baseline_metrics = {"accuracy": 0.85, "f1_score": 0.83, "auroc": 0.87}

        improved_metrics = {"accuracy": 0.88, "f1_score": 0.86, "auroc": 0.90}

        data_contribution = {
            "contributor_id": "contributor_001",
            "data_hash": "abc123",
            "num_samples": 1000,
        }

        delta, attestation = tracker.track_improvement(
            baseline_metrics, improved_metrics, data_contribution
        )

        # Check delta calculation
        assert delta["accuracy"] == 0.03
        assert delta["f1_score"] == 0.03
        assert delta["auroc"] == 0.03

        # Check attestation
        assert attestation["contributor_id"] == "contributor_001"
        assert "timestamp" in attestation
        assert "verification_hash" in attestation
        assert attestation["performance_delta"] == delta

        # Check MLflow logging
        mock_log_metrics.assert_called()
        mock_log_dict.assert_called()

    def test_calculate_delta(self):
        """Test delta calculation."""
        tracker = PerformanceTracker()

        baseline = {"accuracy": 0.80, "f1": 0.75}
        improved = {"accuracy": 0.85, "f1": 0.78}

        delta = tracker._calculate_delta(baseline, improved)

        assert delta["accuracy"] == 0.05
        assert delta["f1"] == 0.03

    def test_calculate_delta_percentage(self):
        """Test delta calculation with percentage."""
        tracker = PerformanceTracker()

        baseline = {"accuracy": 0.80, "f1": 0.50}
        improved = {"accuracy": 0.84, "f1": 0.60}

        delta = tracker._calculate_delta(baseline, improved, percentage=True)

        assert delta["accuracy"] == 5.0  # 5% improvement
        assert delta["f1"] == 20.0  # 20% improvement

    def test_calculate_delta_zero_baseline(self):
        """Test delta calculation with zero baseline."""
        tracker = PerformanceTracker()

        baseline = {"accuracy": 0.0, "f1": 0.75}
        improved = {"accuracy": 0.85, "f1": 0.78}

        delta = tracker._calculate_delta(baseline, improved, percentage=True)

        assert delta["accuracy"] == 100.0  # 100% improvement from 0
        assert delta["f1"] == 4.0  # 4% improvement

    def test_validate_metrics(self):
        """Test metrics validation."""
        tracker = PerformanceTracker()

        # Valid metrics
        valid_metrics = {"accuracy": 0.85, "f1": 0.83}
        tracker._validate_metrics(valid_metrics)  # Should not raise

        # Invalid metrics - empty
        with pytest.raises(ValueError, match="Metrics cannot be empty"):
            tracker._validate_metrics({})

        # Invalid metrics - non-numeric
        with pytest.raises(ValueError, match="Metric values must be numeric"):
            tracker._validate_metrics({"accuracy": "high"})

        # Invalid metrics - out of range
        with pytest.raises(ValueError, match="Metric values must be between 0 and 1"):
            tracker._validate_metrics({"accuracy": 1.5})

    def test_generate_attestation(self):
        """Test attestation generation."""
        tracker = PerformanceTracker()

        delta = {"accuracy": 0.03, "f1": 0.02}
        data_contribution = {
            "contributor_id": "contributor_001",
            "data_hash": "abc123",
            "num_samples": 1000,
        }

        attestation = tracker._generate_attestation(delta, data_contribution)

        assert attestation["contributor_id"] == "contributor_001"
        assert attestation["data_hash"] == "abc123"
        assert attestation["performance_delta"] == delta
        assert attestation["num_samples"] == 1000
        assert "timestamp" in attestation
        assert "verification_hash" in attestation

        # Verify hash is deterministic
        expected_content = json.dumps(
            {
                "contributor_id": "contributor_001",
                "data_hash": "abc123",
                "performance_delta": delta,
                "timestamp": attestation["timestamp"],
            },
            sort_keys=True,
        )
        expected_hash = hashlib.sha256(expected_content.encode()).hexdigest()
        assert attestation["verification_hash"] == expected_hash

    def test_calculate_deltaone_value(self):
        """Test DeltaOne value calculation."""
        tracker = PerformanceTracker()

        # Test with >1% improvement in primary metric
        delta = {"accuracy": 0.015, "f1": 0.008}  # 1.5% and 0.8%
        deltaone = tracker.calculate_deltaone_value(delta, primary_metric="accuracy")
        assert deltaone == 1.0

        # Test with <1% improvement
        delta = {"accuracy": 0.008, "f1": 0.005}  # 0.8% and 0.5%
        deltaone = tracker.calculate_deltaone_value(delta, primary_metric="accuracy")
        assert deltaone == 0.0

        # Test with exactly 1% improvement
        delta = {"accuracy": 0.01, "f1": 0.005}  # 1.0% and 0.5%
        deltaone = tracker.calculate_deltaone_value(delta, primary_metric="accuracy")
        assert deltaone == 1.0

    def test_get_contributor_impact(self):
        """Test contributor impact calculation."""
        tracker = PerformanceTracker()

        attestation = {
            "contributor_id": "contributor_001",
            "performance_delta": {"accuracy": 0.03, "f1": 0.02},
            "num_samples": 1000,
            "timestamp": datetime.now().isoformat(),
        }

        impact = tracker.get_contributor_impact(attestation)

        assert impact["contributor_id"] == "contributor_001"
        assert impact["total_impact"] == 0.025  # Average of 0.03 and 0.02
        assert impact["num_samples"] == 1000
        assert impact["metrics_impact"] == {"accuracy": 0.03, "f1": 0.02}

    @patch("mlflow.log_metrics")
    @patch("mlflow.log_dict")
    @patch("mlflow.set_tag")
    def test_log_improvement_to_mlflow(self, mock_set_tag, mock_log_dict, mock_log_metrics):
        """Test logging improvement to MLflow."""
        tracker = PerformanceTracker()

        delta = {"accuracy": 0.03, "f1": 0.02}
        attestation = {"contributor_id": "contributor_001", "verification_hash": "hash123"}
        data_contribution = {"num_samples": 1000}

        tracker._log_improvement_to_mlflow(delta, attestation, data_contribution)

        # Check metrics logged
        expected_metrics = {"delta_accuracy": 0.03, "delta_f1": 0.02}
        mock_log_metrics.assert_called_with(expected_metrics)

        # Check attestation logged
        mock_log_dict.assert_called_once()
        call_args = mock_log_dict.call_args[0]
        assert call_args[0] == attestation
        assert call_args[1] == "attestation.json"

        # Check tags
        mock_set_tag.assert_any_call("contributor_id", "contributor_001")
        mock_set_tag.assert_any_call("has_improvement", "true")

    def test_verify_attestation(self):
        """Test attestation verification."""
        tracker = PerformanceTracker()

        # Create valid attestation
        delta = {"accuracy": 0.03}
        data_contribution = {"contributor_id": "contributor_001", "data_hash": "abc123"}
        attestation = tracker._generate_attestation(delta, data_contribution)

        # Verify should pass
        assert tracker.verify_attestation(attestation) is True

        # Tamper with attestation
        attestation["performance_delta"]["accuracy"] = 0.05

        # Verification should fail
        assert tracker.verify_attestation(attestation) is False

    def test_aggregate_contributor_performance(self):
        """Test aggregating performance across contributors."""
        tracker = PerformanceTracker()

        attestations = [
            {
                "contributor_id": "contributor_001",
                "performance_delta": {"accuracy": 0.02, "f1": 0.01},
                "num_samples": 500,
            },
            {
                "contributor_id": "contributor_001",
                "performance_delta": {"accuracy": 0.01, "f1": 0.02},
                "num_samples": 300,
            },
            {
                "contributor_id": "contributor_002",
                "performance_delta": {"accuracy": 0.03, "f1": 0.03},
                "num_samples": 1000,
            },
        ]

        aggregated = tracker.aggregate_contributor_performance(attestations)

        assert len(aggregated) == 2
        assert aggregated["contributor_001"]["total_samples"] == 800
        assert aggregated["contributor_001"]["avg_accuracy_delta"] == 0.015  # (0.02 + 0.01) / 2
        assert aggregated["contributor_002"]["total_samples"] == 1000
        assert aggregated["contributor_002"]["avg_accuracy_delta"] == 0.03
