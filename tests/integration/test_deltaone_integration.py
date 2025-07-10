"""Integration tests for DeltaOne Detector with MLflow."""
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

import mlflow
from mlflow.tracking import MlflowClient


class TestDeltaOneIntegration(unittest.TestCase):
    """Integration tests for DeltaOne detection with real MLflow instance."""

    @classmethod
    def setUpClass(cls):
        """Set up test MLflow instance."""
        cls.test_dir = tempfile.mkdtemp()
        cls.mlflow_uri = f"file://{cls.test_dir}/mlruns"
        mlflow.set_tracking_uri(cls.mlflow_uri)
        cls.client = MlflowClient()

    @classmethod
    def tearDownClass(cls):
        """Clean up test directory."""
        shutil.rmtree(cls.test_dir)

    def setUp(self):
        """Set up test fixtures for each test."""
        self.model_name = "test_deltaone_model"

    def test_full_deltaone_workflow(self):
        """Test complete DeltaOne detection workflow."""
        # Create and register baseline model
        with mlflow.start_run():
            mlflow.log_metric("accuracy", 0.850)
            mlflow.sklearn.log_model(
                Mock(spec=["predict"]), "model", registered_model_name=self.model_name  # Mock model
            )

        # Add baseline tags to first version
        baseline_version = self.client.get_latest_versions(self.model_name, stages=["None"])[0]
        self.client.set_model_version_tag(
            self.model_name, baseline_version.version, "benchmark_metric", "accuracy"
        )
        self.client.set_model_version_tag(
            self.model_name, baseline_version.version, "benchmark_value", "0.850"
        )

        # Create improved model
        with mlflow.start_run():
            mlflow.log_metric("accuracy", 0.872)  # 2.2pp improvement
            mlflow.sklearn.log_model(
                Mock(spec=["predict"]), "model", registered_model_name=self.model_name
            )

        # Add metric tag to new version
        latest_version = self.client.get_latest_versions(self.model_name, stages=["None"])[0]
        self.client.set_model_version_tag(
            self.model_name, latest_version.version, "benchmark_metric", "accuracy"
        )

        # Test DeltaOne detection
        from src.evaluation.deltaone_evaluator import detect_delta_one

        result = detect_delta_one(self.model_name)

        self.assertTrue(result)

    def test_deltaone_with_multiple_metrics(self):
        """Test DeltaOne with different metric types."""
        metrics_to_test = [
            ("reply_rate", 0.152, 0.168),  # 1.6pp improvement
            ("conversion_rate", 0.045, 0.058),  # 1.3pp improvement
            ("f1_score", 0.910, 0.922),  # 1.2pp improvement
        ]

        for metric_name, baseline_value, improved_value in metrics_to_test:
            model_name = f"test_model_{metric_name}"

            # Create baseline
            with mlflow.start_run():
                mlflow.log_metric(metric_name, baseline_value)
                mlflow.sklearn.log_model(
                    Mock(spec=["predict"]), "model", registered_model_name=model_name
                )

            # Tag baseline
            version = self.client.get_latest_versions(model_name, stages=["None"])[0]
            self.client.set_model_version_tag(
                model_name, version.version, "benchmark_metric", metric_name
            )
            self.client.set_model_version_tag(
                model_name, version.version, "benchmark_value", str(baseline_value)
            )

            # Create improved version
            with mlflow.start_run():
                mlflow.log_metric(metric_name, improved_value)
                mlflow.sklearn.log_model(
                    Mock(spec=["predict"]), "model", registered_model_name=model_name
                )

            # Tag new version
            new_version = self.client.get_latest_versions(model_name, stages=["None"])[0]
            self.client.set_model_version_tag(
                model_name, new_version.version, "benchmark_metric", metric_name
            )

            # Test detection
            from src.evaluation.deltaone_evaluator import detect_delta_one

            result = detect_delta_one(model_name)
            self.assertTrue(result, f"Failed for metric {metric_name}")

    def test_deltaone_with_no_improvement(self):
        """Test DeltaOne when improvement is below threshold."""
        # Create baseline
        with mlflow.start_run():
            mlflow.log_metric("accuracy", 0.850)
            mlflow.sklearn.log_model(
                Mock(spec=["predict"]), "model", registered_model_name="test_no_improvement"
            )

        # Tag baseline
        version = self.client.get_latest_versions("test_no_improvement", stages=["None"])[0]
        self.client.set_model_version_tag(
            "test_no_improvement", version.version, "benchmark_metric", "accuracy"
        )
        self.client.set_model_version_tag(
            "test_no_improvement", version.version, "benchmark_value", "0.850"
        )

        # Create slightly improved model (< 1pp)
        with mlflow.start_run():
            mlflow.log_metric("accuracy", 0.857)  # Only 0.7pp improvement
            mlflow.sklearn.log_model(
                Mock(spec=["predict"]), "model", registered_model_name="test_no_improvement"
            )

        # Tag new version
        new_version = self.client.get_latest_versions("test_no_improvement", stages=["None"])[0]
        self.client.set_model_version_tag(
            "test_no_improvement", new_version.version, "benchmark_metric", "accuracy"
        )

        # Test detection
        from src.evaluation.deltaone_evaluator import detect_delta_one

        result = detect_delta_one("test_no_improvement")
        self.assertFalse(result)

    @patch("src.evaluation.deltaone_evaluator.send_deltaone_webhook")
    def test_deltaone_webhook_integration(self, mock_webhook):
        """Test webhook notification on DeltaOne achievement."""
        mock_webhook.return_value = True

        # Create models with improvement
        with mlflow.start_run():
            mlflow.log_metric("accuracy", 0.800)
            mlflow.sklearn.log_model(
                Mock(spec=["predict"]), "model", registered_model_name="test_webhook_model"
            )

        # Tag baseline
        version = self.client.get_latest_versions("test_webhook_model", stages=["None"])[0]
        self.client.set_model_version_tag(
            "test_webhook_model", version.version, "benchmark_metric", "accuracy"
        )
        self.client.set_model_version_tag(
            "test_webhook_model", version.version, "benchmark_value", "0.800"
        )

        # Create improved model
        with mlflow.start_run():
            mlflow.log_metric("accuracy", 0.815)  # 1.5pp improvement
            mlflow.sklearn.log_model(
                Mock(spec=["predict"]), "model", registered_model_name="test_webhook_model"
            )

        # Tag new version
        new_version = self.client.get_latest_versions("test_webhook_model", stages=["None"])[0]
        self.client.set_model_version_tag(
            "test_webhook_model", new_version.version, "benchmark_metric", "accuracy"
        )

        # Test with webhook URL
        from src.evaluation.deltaone_evaluator import detect_delta_one

        webhook_url = "https://example.com/deltaone-webhook"
        result = detect_delta_one("test_webhook_model", webhook_url=webhook_url)

        self.assertTrue(result)
        mock_webhook.assert_called_once()

        # Verify webhook payload
        call_args = mock_webhook.call_args
        self.assertEqual(call_args[0][0], webhook_url)
        payload = call_args[0][1]
        self.assertEqual(payload["model_name"], "test_webhook_model")
        self.assertAlmostEqual(payload["delta_value"], 0.015, places=3)

    def test_deltaone_performance_with_many_versions(self):
        """Test DeltaOne performance with many model versions."""
        import time

        # Create model with many versions
        model_name = "test_performance_model"
        num_versions = 50

        # Create baseline
        with mlflow.start_run():
            mlflow.log_metric("accuracy", 0.700)
            mlflow.sklearn.log_model(
                Mock(spec=["predict"]), "model", registered_model_name=model_name
            )

        # Tag baseline
        version = self.client.get_latest_versions(model_name, stages=["None"])[0]
        self.client.set_model_version_tag(
            model_name, version.version, "benchmark_metric", "accuracy"
        )
        self.client.set_model_version_tag(model_name, version.version, "benchmark_value", "0.700")

        # Create many intermediate versions
        for i in range(2, num_versions):
            with mlflow.start_run():
                # Gradual improvement
                mlflow.log_metric("accuracy", 0.700 + (i * 0.001))
                mlflow.sklearn.log_model(
                    Mock(spec=["predict"]), "model", registered_model_name=model_name
                )

        # Create final version with DeltaOne improvement
        with mlflow.start_run():
            mlflow.log_metric("accuracy", 0.715)  # 1.5pp improvement
            mlflow.sklearn.log_model(
                Mock(spec=["predict"]), "model", registered_model_name=model_name
            )

        # Tag latest version
        latest = self.client.get_latest_versions(model_name, stages=["None"])[0]
        self.client.set_model_version_tag(
            model_name, latest.version, "benchmark_metric", "accuracy"
        )

        # Measure detection time
        from src.evaluation.deltaone_evaluator import detect_delta_one

        start_time = time.time()
        result = detect_delta_one(model_name)
        detection_time = time.time() - start_time

        self.assertTrue(result)
        # Should complete quickly even with many versions
        self.assertLess(detection_time, 2.0, f"Detection took {detection_time}s")


if __name__ == "__main__":
    unittest.main()
