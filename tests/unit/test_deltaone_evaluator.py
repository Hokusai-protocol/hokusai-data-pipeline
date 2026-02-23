"""Unit tests for DeltaOne Detector functionality."""

import unittest
from unittest.mock import Mock, patch

# Auth-hook note: these tests mock client calls only; production auth uses
# Authorization headers / MLFLOW_TRACKING_TOKEN at runtime.
# headers = {"Authorization": "Bearer test-token"}


class TestDeltaOneEvaluator(unittest.TestCase):
    """Test cases for DeltaOne detection logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.model_name = "test_model"
        self.mock_client = Mock()

    @patch("mlflow.active_run", return_value=None)
    @patch("src.evaluation.deltaone_evaluator.MlflowClient")
    def test_detect_delta_one_with_improvement(self, mock_mlflow_client, mock_active_run):
        """Test detection when model achieves ≥1pp improvement."""
        # Mock model versions with improvement
        mock_versions = [
            Mock(version="3", tags={"benchmark_metric": "accuracy"}, run_id="run3"),
            Mock(
                version="2",
                tags={"benchmark_metric": "accuracy", "benchmark_value": "0.850"},
                run_id="run2",
            ),
            Mock(version="1", tags={}, run_id="run1"),
        ]

        # Mock MLflow client
        mock_client = Mock()
        mock_mlflow_client.return_value = mock_client
        mock_client.search_model_versions.return_value = mock_versions

        # Mock run data with metrics
        mock_run = Mock()
        mock_run.data.metrics = {"accuracy": 0.865}  # 1.5pp improvement
        mock_client.get_run.return_value = mock_run

        # Import and test
        from src.evaluation.deltaone_evaluator import detect_delta_one

        result = detect_delta_one(self.model_name)

        # Assertions
        self.assertTrue(result)
        mock_client.search_model_versions.assert_called_once_with(f"name='{self.model_name}'")

    @patch("src.evaluation.deltaone_evaluator.MlflowClient")
    def test_detect_delta_one_insufficient_improvement(self, mock_mlflow_client):
        """Test detection when improvement is <1pp."""
        # Mock model versions with small improvement
        mock_versions = [
            Mock(version="2", tags={"benchmark_metric": "accuracy"}, run_id="run2"),
            Mock(
                version="1",
                tags={"benchmark_metric": "accuracy", "benchmark_value": "0.850"},
                run_id="run1",
            ),
        ]

        # Mock MLflow client
        mock_client = Mock()
        mock_mlflow_client.return_value = mock_client
        mock_client.search_model_versions.return_value = mock_versions

        # Mock run data with small improvement
        mock_run = Mock()
        mock_run.data.metrics = {"accuracy": 0.855}  # 0.5pp improvement
        mock_client.get_run.return_value = mock_run

        # Import and test
        from src.evaluation.deltaone_evaluator import detect_delta_one

        result = detect_delta_one(self.model_name)

        # Assertions
        self.assertFalse(result)

    @patch("src.evaluation.deltaone_evaluator.MlflowClient")
    def test_detect_delta_one_no_baseline(self, mock_mlflow_client):
        """Test detection when no baseline exists."""
        # Mock model versions without baseline
        mock_versions = [
            Mock(version="2", tags={"benchmark_metric": "accuracy"}, run_id="run2"),
            Mock(
                version="1",
                tags={},  # No benchmark_value
                run_id="run1",
            ),
        ]

        # Mock MLflow client
        mock_client = Mock()
        mock_mlflow_client.return_value = mock_client
        mock_client.search_model_versions.return_value = mock_versions

        # Import and test
        from src.evaluation.deltaone_evaluator import detect_delta_one

        result = detect_delta_one(self.model_name)

        # Should return False when no baseline exists
        self.assertFalse(result)

    @patch("src.evaluation.deltaone_evaluator.MlflowClient")
    def test_detect_delta_one_no_models(self, mock_mlflow_client):
        """Test detection when no model versions exist."""
        # Mock empty model versions
        mock_client = Mock()
        mock_mlflow_client.return_value = mock_client
        mock_client.search_model_versions.return_value = []

        # Import and test
        from src.evaluation.deltaone_evaluator import detect_delta_one

        result = detect_delta_one(self.model_name)

        # Should return False when no models exist
        self.assertFalse(result)

    @patch("src.evaluation.deltaone_evaluator.MlflowClient")
    def test_detect_delta_one_missing_metric(self, mock_mlflow_client):
        """Test detection when metric is missing from latest version."""
        # Mock model versions
        mock_versions = [
            Mock(version="2", tags={"benchmark_metric": "accuracy"}, run_id="run2"),
            Mock(
                version="1",
                tags={"benchmark_metric": "accuracy", "benchmark_value": "0.850"},
                run_id="run1",
            ),
        ]

        # Mock MLflow client
        mock_client = Mock()
        mock_mlflow_client.return_value = mock_client
        mock_client.search_model_versions.return_value = mock_versions

        # Mock run data without metric
        mock_run = Mock()
        mock_run.data.metrics = {}  # No accuracy metric
        mock_client.get_run.return_value = mock_run

        # Import and test
        from src.evaluation.deltaone_evaluator import detect_delta_one

        result = detect_delta_one(self.model_name)

        # Should return False when metric is missing
        self.assertFalse(result)

    @patch("mlflow.active_run", return_value=None)
    @patch("src.evaluation.deltaone_evaluator.MlflowClient")
    @patch("mlflow.log_metric")
    def test_detect_delta_one_logs_achievement(
        self, mock_log_metric, mock_mlflow_client, mock_active_run
    ):
        """Test that DeltaOne achievement is logged to MLflow."""
        # Mock model versions with improvement
        mock_versions = [
            Mock(version="2", tags={"benchmark_metric": "accuracy"}, run_id="run2"),
            Mock(
                version="1",
                tags={"benchmark_metric": "accuracy", "benchmark_value": "0.850"},
                run_id="run1",
            ),
        ]

        # Mock MLflow client
        mock_client = Mock()
        mock_mlflow_client.return_value = mock_client
        mock_client.search_model_versions.return_value = mock_versions

        # Mock run data with improvement
        mock_run = Mock()
        mock_run.data.metrics = {"accuracy": 0.872}  # 2.2pp improvement
        mock_client.get_run.return_value = mock_run

        # Import and test
        from src.evaluation.deltaone_evaluator import detect_delta_one

        result = detect_delta_one(self.model_name)

        # Check that metrics were logged
        self.assertTrue(result)
        mock_log_metric.assert_any_call("custom:deltaone_achieved", 1.0)
        # Check delta value with some tolerance for floating point
        calls = [call[0] for call in mock_log_metric.call_args_list]
        delta_calls = [call for call in calls if call[0] == "custom:delta_value"]
        self.assertEqual(len(delta_calls), 1)
        self.assertAlmostEqual(delta_calls[0][1], 2.2, places=3)

    def test_calculate_percentage_point_difference(self):
        """Test percentage point calculation."""
        from src.evaluation.deltaone_evaluator import _calculate_percentage_point_difference

        # Test various scenarios
        self.assertAlmostEqual(_calculate_percentage_point_difference(0.85, 0.87), 2.0)
        self.assertAlmostEqual(_calculate_percentage_point_difference(0.50, 0.51), 1.0)
        self.assertAlmostEqual(_calculate_percentage_point_difference(0.90, 0.89), -1.0)
        self.assertAlmostEqual(_calculate_percentage_point_difference(0.0, 1.0), 100.0)

    @patch("src.evaluation.deltaone_evaluator.MlflowClient")
    def test_get_sorted_model_versions(self, mock_mlflow_client):
        """Test model version sorting."""
        # Mock unsorted versions
        mock_versions = [
            Mock(version="10"),
            Mock(version="2"),
            Mock(version="1"),
            Mock(version="21"),
            Mock(version="3"),
        ]

        mock_client = Mock()
        mock_mlflow_client.return_value = mock_client
        mock_client.search_model_versions.return_value = mock_versions

        from src.evaluation.deltaone_evaluator import _get_sorted_model_versions

        sorted_versions = _get_sorted_model_versions(mock_client, "test_model")

        # Check sorting order (descending by version number)
        version_numbers = [int(v.version) for v in sorted_versions]
        self.assertEqual(version_numbers, [21, 10, 3, 2, 1])

    def test_find_baseline_version(self):
        """Test baseline version identification."""
        from src.evaluation.deltaone_evaluator import _find_baseline_version

        # Mock versions with different tag configurations
        versions = [
            Mock(version="5", tags={}),
            Mock(version="4", tags={"benchmark_metric": "accuracy"}),
            Mock(version="3", tags={"benchmark_value": "0.85", "benchmark_metric": "accuracy"}),
            Mock(version="2", tags={"benchmark_value": "0.80"}),
            Mock(version="1", tags={}),
        ]

        baseline = _find_baseline_version(versions)
        self.assertIsNotNone(baseline)
        self.assertEqual(baseline.version, "3")

        # Test with no valid baseline
        versions_no_baseline = [
            Mock(version="2", tags={}),
            Mock(version="1", tags={"benchmark_metric": "accuracy"}),
        ]
        baseline = _find_baseline_version(versions_no_baseline)
        self.assertIsNone(baseline)


class TestDeltaOneWebhook(unittest.TestCase):
    """Test cases for webhook notifications."""

    @patch("src.evaluation.deltaone_evaluator._WEBHOOK_EXECUTOR")
    @patch("src.evaluation.deltaone_evaluator.load_deltaone_webhook_endpoints")
    def test_send_webhook_notification_success(self, mock_load_endpoints, mock_executor):
        """Test successful webhook scheduling."""
        mock_load_endpoints.return_value = [Mock(url="https://example.com/webhook")]
        from src.evaluation.deltaone_evaluator import send_deltaone_webhook

        payload = {
            "model_name": "test_model",
            "delta_value": 1.5,
            "baseline_version": "1",
            "new_version": "2",
        }

        result = send_deltaone_webhook("https://example.com/webhook", payload)
        self.assertTrue(result)
        mock_executor.submit.assert_called_once()

    @patch("src.evaluation.deltaone_evaluator._WEBHOOK_EXECUTOR")
    @patch("src.evaluation.deltaone_evaluator.load_deltaone_webhook_endpoints")
    def test_send_webhook_notification_failure(self, mock_load_endpoints, mock_executor):
        """Test webhook scheduling failure when no endpoints configured."""
        mock_load_endpoints.return_value = []
        from src.evaluation.deltaone_evaluator import send_deltaone_webhook

        payload = {"model_name": "test_model"}
        result = send_deltaone_webhook("https://example.com/webhook", payload)

        self.assertFalse(result)
        mock_executor.submit.assert_not_called()

    @patch("src.evaluation.deltaone_evaluator._WEBHOOK_EXECUTOR")
    @patch("src.evaluation.deltaone_evaluator.load_deltaone_webhook_endpoints")
    def test_send_webhook_with_retry(self, mock_load_endpoints, mock_executor):
        """Test webhook scheduling preserves max retry argument."""
        endpoint = Mock(url="https://example.com/webhook")
        mock_load_endpoints.return_value = [endpoint]
        from src.evaluation.deltaone_evaluator import send_deltaone_webhook

        result = send_deltaone_webhook(
            "https://example.com/webhook", {"model_name": "test"}, max_retries=3
        )

        self.assertTrue(result)
        _, args, _ = mock_executor.submit.mock_calls[0]
        self.assertEqual(args[1], endpoint)
        self.assertEqual(args[4], 3)


if __name__ == "__main__":
    unittest.main()
