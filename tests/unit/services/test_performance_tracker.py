"""Unit tests for the PerformanceTracker service."""

import pytest
from unittest.mock import patch
from datetime import datetime

from src.services.performance_tracker import PerformanceTracker


class TestPerformanceTracker:
    """Test cases for PerformanceTracker class."""

    @pytest.fixture
    def tracker(self):
        """Create a tracker instance for testing."""
        return PerformanceTracker()

    @pytest.fixture
    def baseline_metrics(self):
        """Sample baseline metrics for testing."""
        return {
            "accuracy": 0.85,
            "auroc": 0.82,
            "f1_score": 0.83,
            "precision": 0.84,
            "recall": 0.82
        }

    @pytest.fixture
    def improved_metrics(self):
        """Sample improved metrics for testing."""
        return {
            "accuracy": 0.89,
            "auroc": 0.86,
            "f1_score": 0.87,
            "precision": 0.88,
            "recall": 0.86
        }

    @pytest.fixture
    def data_contribution(self):
        """Sample data contribution metadata."""
        return {
            "contributor_id": "contributor_001",
            "contributor_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f62341",
            "dataset_hash": "0xdeadbeef123456789",
            "data_size": 10000,
            "data_quality_score": 0.95,
            "contribution_timestamp": "2024-01-01T00:00:00Z"
        }

    def test_calculate_delta_basic(self, tracker, baseline_metrics, improved_metrics):
        """Test basic delta calculation between metrics."""
        delta = tracker._calculate_delta(baseline_metrics, improved_metrics)

        assert delta["accuracy"] == pytest.approx(0.04, 0.001)
        assert delta["auroc"] == pytest.approx(0.04, 0.001)
        assert delta["f1_score"] == pytest.approx(0.04, 0.001)
        assert delta["precision"] == pytest.approx(0.04, 0.001)
        assert delta["recall"] == pytest.approx(0.04, 0.001)

    def test_calculate_delta_percentage(self, tracker, baseline_metrics, improved_metrics):
        """Test delta calculation with percentage improvements."""
        delta = tracker._calculate_delta(baseline_metrics, improved_metrics, percentage=True)

        assert delta["accuracy_pct"] == pytest.approx(4.71, 0.01)
        assert delta["auroc_pct"] == pytest.approx(4.88, 0.01)
        assert delta["f1_score_pct"] == pytest.approx(4.82, 0.01)

    def test_calculate_delta_missing_metrics(self, tracker):
        """Test delta calculation with missing metrics."""
        baseline = {"accuracy": 0.85, "auroc": 0.82}
        improved = {"accuracy": 0.89}  # Missing auroc

        with pytest.raises(ValueError, match="Metric 'auroc' missing"):
            tracker._calculate_delta(baseline, improved)

    def test_generate_attestation_basic(self, tracker, data_contribution):
        """Test basic attestation generation."""
        delta = {"accuracy": 0.04, "auroc": 0.03}

        attestation = tracker._generate_attestation(delta, data_contribution)

        assert attestation["version"] == "1.0"
        assert attestation["timestamp"] is not None
        assert attestation["delta_metrics"] == delta
        assert attestation["contributor_info"]["address"] == data_contribution["contributor_address"]
        assert attestation["data_contribution"]["dataset_hash"] == data_contribution["dataset_hash"]
        assert "attestation_hash" in attestation
        assert "signature" in attestation  # Placeholder for now

    def test_generate_attestation_hash_consistency(self, tracker, data_contribution):
        """Test that attestation hash is deterministic for same inputs."""
        import time
        delta = {"accuracy": 0.04}

        # Generate two attestations
        attestation1 = tracker._generate_attestation(delta, data_contribution)
        time.sleep(1.1)  # Sleep for more than 1 second to ensure different timestamps
        attestation2 = tracker._generate_attestation(delta, data_contribution)

        # The timestamps will be different, so hashes will be different
        assert attestation1["timestamp"] != attestation2["timestamp"]
        assert attestation1["attestation_hash"] != attestation2["attestation_hash"]

        # But the core data should be the same
        assert attestation1["delta_metrics"] == attestation2["delta_metrics"]
        assert attestation1["contributor_info"] == attestation2["contributor_info"]
        assert attestation1["deltaone_value"] == attestation2["deltaone_value"]

    @patch("mlflow.log_metrics")
    @patch("mlflow.log_params")
    @patch("mlflow.log_dict")
    def test_track_improvement_success(self, mock_log_dict, mock_log_params,
                                     mock_log_metrics, tracker, baseline_metrics,
                                     improved_metrics, data_contribution):
        """Test successful improvement tracking."""
        delta, attestation = tracker.track_improvement(
            baseline_metrics=baseline_metrics,
            improved_metrics=improved_metrics,
            data_contribution=data_contribution
        )

        # Verify delta calculation
        assert delta["accuracy"] == pytest.approx(0.04, 0.001)

        # Verify attestation structure
        assert attestation["version"] == "1.0"
        assert attestation["contributor_info"]["address"] == data_contribution["contributor_address"]

        # Verify MLflow logging
        mock_log_metrics.assert_called()
        logged_metrics = mock_log_metrics.call_args[0][0]
        assert "accuracy_improvement" in logged_metrics
        assert "auroc_improvement" in logged_metrics

        mock_log_dict.assert_called_once()
        dict_call_args = mock_log_dict.call_args
        assert dict_call_args[0][0] == attestation
        assert dict_call_args[1]["artifact_file"] == "attestation.json"

    @patch("mlflow.log_metrics")
    @patch("mlflow.log_params")
    def test_log_contribution_impact_success(self, mock_log_params, mock_log_metrics, tracker):
        """Test logging contributor impact."""
        contributor_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f62341"
        model_id = "lead_scoring_model/3"
        delta = {"accuracy": 0.04, "auroc": 0.03}

        tracker.log_contribution_impact(contributor_address, model_id, delta)

        # Verify logging calls
        mock_log_params.assert_called()
        params = mock_log_params.call_args[0][0]
        assert params["contributor_address"] == contributor_address
        assert params["model_id"] == model_id
        assert "impact_score" in params

        mock_log_metrics.assert_called_once()
        metrics = mock_log_metrics.call_args[0][0]
        assert "total_improvement" in metrics

    def test_calculate_impact_score(self, tracker):
        """Test impact score calculation."""
        delta = {
            "accuracy": 0.04,
            "auroc": 0.03,
            "f1_score": 0.035
        }

        score = tracker._calculate_impact_score(delta)

        # Score should be average of improvements
        expected = (0.04 + 0.03 + 0.035) / 3
        assert score == pytest.approx(expected, 0.001)

    def test_validate_metrics_format(self, tracker):
        """Test metrics format validation."""
        valid_metrics = {"accuracy": 0.85, "auroc": 0.82}
        assert tracker._validate_metrics(valid_metrics) is True

        # Invalid metrics
        with pytest.raises(ValueError, match="must be a dictionary"):
            tracker._validate_metrics("not a dict")

        with pytest.raises(ValueError, match="cannot be empty"):
            tracker._validate_metrics({})

        with pytest.raises(ValueError, match="must be numeric"):
            tracker._validate_metrics({"accuracy": "0.85"})

    def test_generate_deltaone_value(self, tracker):
        """Test DeltaOne value generation."""
        delta = {"accuracy": 0.04, "auroc": 0.03}

        deltaone = tracker._generate_deltaone_value(delta)

        assert isinstance(deltaone, float)
        assert deltaone > 0
        # accuracy: 0.04 * 1.0 * 100 = 4.0
        # auroc: 0.03 * 0.8 * 100 = 2.4
        # total = 6.4
        assert deltaone == pytest.approx(6.4, 0.01)

    @patch("src.services.performance_tracker.datetime")
    def test_attestation_timestamp_format(self, mock_datetime, tracker):
        """Test attestation timestamp formatting."""
        mock_now = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = mock_now

        delta = {"accuracy": 0.04}
        contribution = {"contributor_address": "0x123", "dataset_hash": "0xabc"}

        attestation = tracker._generate_attestation(delta, contribution)

        assert attestation["timestamp"] == "2024-01-01T12:00:00Z"

    def test_track_improvement_negative_delta(self, tracker):
        """Test tracking when model performance decreases."""
        baseline = {"accuracy": 0.85}
        improved = {"accuracy": 0.83}  # Worse performance
        contribution = {"contributor_address": "0x123", "dataset_hash": "0xabc"}

        delta, attestation = tracker.track_improvement(baseline, improved, contribution)

        assert delta["accuracy"] == pytest.approx(-0.02, 0.001)
        assert attestation["delta_metrics"]["accuracy"] < 0

    def test_aggregate_contributor_impacts(self, tracker):
        """Test aggregating impacts from multiple contributions."""
        impacts = [
            {"model": "model1", "delta": {"accuracy": 0.02}},
            {"model": "model2", "delta": {"accuracy": 0.03}},
            {"model": "model1", "delta": {"accuracy": 0.01}}  # Second contribution to model1
        ]

        aggregated = tracker._aggregate_impacts(impacts)

        assert aggregated["model1"]["total_improvement"] == pytest.approx(0.03, 0.001)
        assert aggregated["model1"]["contribution_count"] == 2
        assert aggregated["model2"]["total_improvement"] == pytest.approx(0.03, 0.001)
        assert aggregated["model2"]["contribution_count"] == 1
