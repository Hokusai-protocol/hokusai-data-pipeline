"""Unit tests for performance tracker service."""

from unittest.mock import patch

import pytest

from src.services.performance_tracker import PerformanceTracker


class TestPerformanceTracker:
    """Test suite for PerformanceTracker class."""

    def test_initialization(self):
        tracker = PerformanceTracker()
        assert tracker is not None

    @patch("mlflow.log_metrics")
    @patch("mlflow.log_dict")
    @patch("mlflow.log_params")
    def test_track_improvement(self, mock_log_params, mock_log_dict, mock_log_metrics):
        tracker = PerformanceTracker()

        baseline_metrics = {"accuracy": 0.85, "f1_score": 0.83, "auroc": 0.87}
        improved_metrics = {"accuracy": 0.88, "f1_score": 0.86, "auroc": 0.90}
        data_contribution = {
            "contributor_id": "contributor_001",
            "dataset_hash": "abc123",
            "data_size": 1000,
            "data_quality_score": 0.9,
        }

        delta, attestation = tracker.track_improvement(
            baseline_metrics, improved_metrics, data_contribution
        )

        assert delta["accuracy"] == 0.03
        assert delta["f1_score"] == 0.03
        assert delta["auroc"] == 0.03
        assert attestation["contributor_info"]["id"] == "contributor_001"
        assert "attestation_hash" in attestation

        mock_log_metrics.assert_called()
        mock_log_dict.assert_called_once()
        mock_log_params.assert_called_once()

    def test_calculate_delta(self):
        tracker = PerformanceTracker()

        baseline = {"accuracy": 0.80, "f1": 0.75}
        improved = {"accuracy": 0.85, "f1": 0.78}

        delta = tracker._calculate_delta(baseline, improved, percentage=True)

        assert delta["accuracy"] == 0.05
        assert delta["f1"] == 0.03
        assert delta["accuracy_pct"] == 6.25
        assert delta["f1_pct"] == 4.0

    def test_calculate_delta_zero_baseline(self):
        tracker = PerformanceTracker()

        baseline = {"accuracy": 0.0, "f1": 0.75}
        improved = {"accuracy": 0.85, "f1": 0.78}

        delta = tracker._calculate_delta(baseline, improved, percentage=True)

        assert delta["accuracy"] == 0.85
        assert "accuracy_pct" not in delta
        assert delta["f1_pct"] == 4.0

    def test_validate_metrics(self):
        tracker = PerformanceTracker()
        tracker._validate_metrics({"accuracy": 0.85, "f1": 0.83})

        with pytest.raises(ValueError, match="Metrics cannot be empty"):
            tracker._validate_metrics({})

        with pytest.raises(ValueError, match="must be numeric"):
            tracker._validate_metrics({"accuracy": "high"})

    def test_generate_attestation(self):
        tracker = PerformanceTracker()

        delta = {"accuracy": 0.03, "f1": 0.02}
        data_contribution = {
            "contributor_id": "contributor_001",
            "dataset_hash": "abc123",
            "data_size": 1000,
            "data_quality_score": 0.9,
        }

        attestation = tracker._generate_attestation(delta, data_contribution)

        assert attestation["contributor_info"]["id"] == "contributor_001"
        assert attestation["data_contribution"]["dataset_hash"] == "abc123"
        assert attestation["delta_metrics"] == delta
        assert "timestamp" in attestation
        assert "attestation_hash" in attestation
        assert "deltaone_value" in attestation

    def test_generate_deltaone_value(self):
        tracker = PerformanceTracker()

        delta = {"accuracy": 0.015, "f1_score": 0.008}
        deltaone = tracker._generate_deltaone_value(delta)
        assert deltaone == 2.22

        delta = {"precision": -0.01}
        assert tracker._generate_deltaone_value(delta) == 0

    def test_get_contributor_impact(self):
        tracker = PerformanceTracker()
        impact = tracker.get_contributor_impact("0x123")

        assert impact["total_models_improved"] == 0
        assert impact["total_improvement_score"] == 0.0
        assert impact["contributions"] == []

    @patch("mlflow.log_metrics")
    @patch("mlflow.log_dict")
    @patch("mlflow.log_params")
    def test_log_improvement_to_mlflow(self, mock_log_params, mock_log_dict, mock_log_metrics):
        tracker = PerformanceTracker()

        delta = {"accuracy": 0.03, "f1": 0.02}
        attestation = {"deltaone_value": 3.2}
        data_contribution = {"contributor_id": "contributor_001", "dataset_hash": "hash123"}

        tracker._log_improvement_to_mlflow(delta, attestation, data_contribution)

        mock_log_metrics.assert_called_once_with(
            {"accuracy_improvement": 0.03, "f1_improvement": 0.02}
        )
        mock_log_dict.assert_called_once()
        mock_log_params.assert_called_once()

    def test_aggregate_impacts(self):
        tracker = PerformanceTracker()

        impacts = [
            {"model": "m1", "delta": {"accuracy": 0.02, "f1": 0.01}},
            {"model": "m1", "delta": {"accuracy": 0.01, "f1": 0.02}},
            {"model": "m2", "delta": {"accuracy": 0.03}},
        ]

        aggregated = tracker._aggregate_impacts(impacts)

        assert set(aggregated.keys()) == {"m1", "m2"}
        assert aggregated["m1"]["contribution_count"] == 2
        assert aggregated["m1"]["metrics"]["accuracy"] == 0.03
        assert aggregated["m2"]["contribution_count"] == 1
