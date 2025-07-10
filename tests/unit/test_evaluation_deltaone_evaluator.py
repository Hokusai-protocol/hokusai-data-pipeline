"""Unit tests for DeltaOne evaluator."""

from unittest.mock import Mock, patch

import pytest
from mlflow.entities.model_registry import ModelVersion

from src.evaluation.deltaone_evaluator import (
    _calculate_percentage_point_difference,
    _find_baseline_version,
    _get_metric_value,
    _get_sorted_model_versions,
    detect_delta_one,
    send_deltaone_webhook,
)


class TestDetectDeltaOne:
    """Test suite for detect_delta_one function."""

    @patch("src.evaluation.deltaone_evaluator.MlflowClient")
    @patch("src.evaluation.deltaone_evaluator._get_sorted_model_versions")
    @patch("src.evaluation.deltaone_evaluator._find_baseline_version")
    @patch("src.evaluation.deltaone_evaluator._get_metric_value")
    @patch("src.evaluation.deltaone_evaluator._calculate_percentage_point_difference")
    def test_detect_delta_one_with_improvement(
        self,
        mock_calc_diff,
        mock_get_metric,
        mock_find_baseline,
        mock_get_versions,
        mock_client_class,
    ):
        """Test detection with improvement >= 1pp."""
        # Setup mocks
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Mock versions
        current_version = Mock()
        current_version.version = "2"
        current_version.tags = {"benchmark_metric": "accuracy"}

        baseline_version = Mock()
        baseline_version.version = "1"
        baseline_version.tags = {"benchmark_metric": "accuracy", "benchmark_value": "0.80"}

        mock_get_versions.return_value = [current_version, baseline_version]
        mock_find_baseline.return_value = baseline_version

        # Mock metrics - current: 0.82 (improvement from baseline 0.80)
        mock_get_metric.return_value = 0.82
        mock_calc_diff.return_value = 0.02  # 2 percentage points (0.82 - 0.80)

        result = detect_delta_one("test_model")

        assert result is True

    @patch("src.evaluation.deltaone_evaluator.MlflowClient")
    @patch("src.evaluation.deltaone_evaluator._get_sorted_model_versions")
    def test_detect_delta_one_no_versions(self, mock_get_versions, mock_client_class):
        """Test detection with no model versions."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_get_versions.return_value = []

        result = detect_delta_one("test_model")

        assert result is False

    @patch("src.evaluation.deltaone_evaluator.MlflowClient")
    @patch("src.evaluation.deltaone_evaluator._get_sorted_model_versions")
    @patch("src.evaluation.deltaone_evaluator._find_baseline_version")
    def test_detect_delta_one_no_baseline(
        self, mock_find_baseline, mock_get_versions, mock_client_class
    ):
        """Test detection when no baseline version found."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        current_version = Mock()
        mock_get_versions.return_value = [current_version]
        mock_find_baseline.return_value = None

        result = detect_delta_one("test_model")

        assert result is False


class TestGetSortedModelVersions:
    """Test suite for _get_sorted_model_versions function."""

    def test_get_sorted_versions(self):
        """Test getting sorted model versions."""
        mock_client = Mock()

        # Create mock versions
        v1 = Mock(spec=ModelVersion)
        v1.version = "1"

        v2 = Mock(spec=ModelVersion)
        v2.version = "2"

        v3 = Mock(spec=ModelVersion)
        v3.version = "3"

        mock_client.search_model_versions.return_value = [v1, v3, v2]

        result = _get_sorted_model_versions(mock_client, "test_model")

        # Should be sorted by version number descending (3, 2, 1)
        assert len(result) == 3
        assert result[0].version == "3"
        assert result[1].version == "2"
        assert result[2].version == "1"


class TestFindBaselineVersion:
    """Test suite for _find_baseline_version function."""

    def test_find_baseline_with_production_stage(self):
        """Test finding baseline with benchmark_value tag."""
        v1 = Mock()
        v1.tags = {"some_tag": "value"}

        v2 = Mock()
        v2.tags = {"benchmark_value": "0.80", "benchmark_metric": "accuracy"}

        v3 = Mock()
        v3.tags = {"another_tag": "value"}

        versions = [v3, v2, v1]

        result = _find_baseline_version(versions)

        assert result == v2

    def test_find_baseline_no_production(self):
        """Test finding baseline when no version has benchmark_value."""
        v1 = Mock()
        v1.tags = {"some_tag": "value"}

        v2 = Mock()
        v2.tags = {"another_tag": "value"}

        versions = [v2, v1]

        result = _find_baseline_version(versions)

        # Should return None when no version has benchmark_value
        assert result is None

    def test_find_baseline_single_version(self):
        """Test finding baseline with only one version."""
        v1 = Mock()
        v1.tags = {"benchmark_value": "0.75", "benchmark_metric": "accuracy"}

        result = _find_baseline_version([v1])

        assert result == v1  # Should return the version if it has benchmark_value


class TestGetMetricValue:
    """Test suite for _get_metric_value function."""

    def test_get_metric_value_success(self):
        """Test successfully getting metric value."""
        mock_client = Mock()
        mock_version = Mock()
        mock_version.run_id = "run_123"

        mock_run = Mock()
        mock_run.data.metrics = {"accuracy": 0.85}
        mock_client.get_run.return_value = mock_run

        result = _get_metric_value(mock_client, mock_version, "accuracy")

        assert result == 0.85

    def test_get_metric_value_not_found(self):
        """Test getting metric that doesn't exist."""
        mock_client = Mock()
        mock_version = Mock()
        mock_version.run_id = "run_123"

        mock_run = Mock()
        mock_run.data.metrics = {"f1": 0.80}
        mock_client.get_run.return_value = mock_run

        result = _get_metric_value(mock_client, mock_version, "accuracy")

        assert result is None

    def test_get_metric_value_exception(self):
        """Test handling exception when getting metric."""
        mock_client = Mock()
        mock_version = Mock()
        mock_version.run_id = "run_123"

        mock_client.get_run.side_effect = Exception("Run not found")

        result = _get_metric_value(mock_client, mock_version, "accuracy")

        assert result is None


class TestCalculatePercentagePointDifference:
    """Test suite for _calculate_percentage_point_difference function."""

    def test_calculate_positive_difference(self):
        """Test calculating positive percentage point difference."""
        result = _calculate_percentage_point_difference(0.80, 0.85)
        assert result == pytest.approx(0.05, 0.0001)  # 0.05 raw difference

    def test_calculate_negative_difference(self):
        """Test calculating negative percentage point difference."""
        result = _calculate_percentage_point_difference(0.85, 0.80)
        assert result == pytest.approx(-0.05, 0.0001)  # -0.05 raw difference

    def test_calculate_no_difference(self):
        """Test calculating with no difference."""
        result = _calculate_percentage_point_difference(0.80, 0.80)
        assert result == 0.0

    def test_calculate_small_difference(self):
        """Test calculating small percentage point difference."""
        result = _calculate_percentage_point_difference(0.800, 0.805)
        assert result == pytest.approx(0.005, 0.0001)  # 0.005 raw difference


class TestSendDeltaoneWebhook:
    """Test suite for send_deltaone_webhook function."""

    @patch("requests.post")
    def test_send_webhook_success(self, mock_post):
        """Test successful webhook send."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        payload = {"model": "test", "delta": 2.0}
        result = send_deltaone_webhook("https://example.com/hook", payload)

        assert result is True
        mock_post.assert_called_once_with(
            "https://example.com/hook",
            json=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Hokusai-DeltaOne/1.0"},
            timeout=10,
        )

    @patch("requests.post")
    @patch("time.sleep")
    def test_send_webhook_retry_then_success(self, mock_sleep, mock_post):
        """Test webhook retry mechanism."""
        # First call fails with non-200 status, second succeeds
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500

        mock_response_success = Mock()
        mock_response_success.status_code = 200

        mock_post.side_effect = [mock_response_fail, mock_response_success]

        payload = {"model": "test", "delta": 2.0}
        result = send_deltaone_webhook("https://example.com/hook", payload, max_retries=2)

        assert result is True
        assert mock_post.call_count == 2
        mock_sleep.assert_called_once_with(1)  # Exponential backoff: 2^0 = 1

    @patch("requests.post")
    @patch("time.sleep")
    def test_send_webhook_all_retries_fail(self, mock_sleep, mock_post):
        """Test webhook when all retries fail."""
        # Mock response with non-200 status
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        payload = {"model": "test", "delta": 2.0}
        result = send_deltaone_webhook("https://example.com/hook", payload, max_retries=2)

        assert result is False
        assert mock_post.call_count == 2
