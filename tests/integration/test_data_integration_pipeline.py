"""Integration tests for data integration in pipeline context."""

import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.modules.data_integration import DataIntegrator


class TestDataIntegrationPipelineIntegration:
    """Test data integration integration with pipeline context."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()

        # Create test contributed data
        self.test_data = pd.DataFrame(
            {
                "query_id": [f"contrib_q_{i}" for i in range(50)],
                "query_text": [f"contributed query {i}" for i in range(50)],
                "feature_1": [0.1 * i for i in range(50)],
                "feature_2": [0.2 * i for i in range(50)],
                "feature_3": [0.3 * i for i in range(50)],
                "label": [i % 2 for i in range(50)],
            }
        )

        self.test_data_path = Path(self.temp_dir) / "contributed_data.csv"
        self.test_data.to_csv(self.test_data_path, index=False)

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_end_to_end_data_integration_workflow(self):
        """Test complete data integration workflow."""
        integrator = DataIntegrator(random_seed=42)

        # Step 1: Load contributed data
        contributed_data = integrator.load_data(
            self.test_data_path, run_id="test_run", metaflow_run_id="test_metaflow"
        )

        assert len(contributed_data) == 50
        assert list(contributed_data.columns) == [
            "query_id",
            "query_text",
            "feature_1",
            "feature_2",
            "feature_3",
            "label",
        ]

        # Step 2: Validate schema
        required_columns = [
            "query_id",
            "query_text",
            "feature_1",
            "feature_2",
            "feature_3",
            "label",
        ]
        assert integrator.validate_schema(contributed_data, required_columns)

        # Step 3: Clean data
        clean_data = integrator.remove_pii(contributed_data)
        deduped_data = integrator.deduplicate(clean_data)

        assert len(deduped_data) <= len(contributed_data)  # Should be same or fewer rows

        # Step 4: Create base dataset (simulating existing training data)
        base_data = pd.DataFrame(
            {
                "query_id": [f"base_q_{i}" for i in range(200)],
                "query_text": [f"base query {i}" for i in range(200)],
                "feature_1": [0.05 * i for i in range(200)],
                "feature_2": [0.15 * i for i in range(200)],
                "feature_3": [0.25 * i for i in range(200)],
                "label": [i % 2 for i in range(200)],
            }
        )

        # Step 5: Merge datasets
        integrated_data = integrator.merge_datasets(
            base_data,
            deduped_data,
            merge_strategy="append",
            run_id="test_run",
            metaflow_run_id="test_metaflow",
        )

        assert len(integrated_data) == len(base_data) + len(deduped_data)
        assert set(integrated_data.columns) == set(base_data.columns)

        # Step 6: Create data manifest
        manifest = integrator.create_data_manifest(deduped_data, self.test_data_path)

        assert "source_path" in manifest
        assert manifest["row_count"] == len(deduped_data)
        assert "data_hash" in manifest

        # Verify manifest contains expected fields
        expected_fields = [
            "source_path",
            "row_count",
            "column_count",
            "columns",
            "data_hash",
            "dtypes",
            "null_counts",
            "unique_counts",
        ]
        for field in expected_fields:
            assert field in manifest

        return integrated_data, manifest

    @patch("mlflow.start_run")
    @patch("mlflow.set_tag")
    @patch("mlflow.log_param")
    @patch("mlflow.log_metric")
    def test_data_integration_with_mlflow_tracking(
        self, mock_log_metric, mock_log_param, mock_set_tag, mock_start_run
    ):
        """Test data integration with full MLFlow tracking."""
        # Setup mock run context
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value.__enter__.return_value = mock_run

        integrated_data, manifest = self.test_end_to_end_data_integration_workflow()

        # Verify MLFlow tracking calls were made
        assert mock_start_run.call_count >= 2  # At least load and merge steps
        assert mock_log_param.call_count > 0
        assert mock_log_metric.call_count > 0

        # Verify data integrity
        assert len(integrated_data) > 0
        assert manifest["data_hash"] is not None

    def test_pipeline_simulation_with_data_integration(self):
        """Test simulating pipeline behavior with data integration."""
        integrator = DataIntegrator(random_seed=42)

        # Simulate pipeline parameters
        # config = {
        #     "random_seed": 42,
        #     "evaluation_metrics": ["accuracy", "precision", "recall", "f1_score", "auroc"]
        # }

        # Step 1: Load and integrate data (simulating integrate_contributed_data step)
        contributed_data = integrator.load_data(
            self.test_data_path, run_id="pipeline_test", metaflow_run_id="pipeline_metaflow"
        )

        # Clean and validate
        required_columns = ["query_id", "label"]
        integrator.validate_schema(contributed_data, required_columns)

        clean_data = integrator.remove_pii(contributed_data)
        deduped_data = integrator.deduplicate(clean_data)

        # Create mock base dataset
        base_data = pd.DataFrame(
            {
                "query_id": [f"base_q_{i}" for i in range(500)],
                "query_text": [f"base query {i}" for i in range(500)],
                "feature_1": [0.1 * i for i in range(500)],
                "feature_2": [0.2 * i for i in range(500)],
                "feature_3": [0.3 * i for i in range(500)],
                "label": [i % 2 for i in range(500)],
            }
        )

        # Merge datasets
        integrated_data = integrator.merge_datasets(
            base_data,
            deduped_data,
            merge_strategy="append",
            run_id="pipeline_test",
            metaflow_run_id="pipeline_metaflow",
        )

        # Create manifest
        data_manifest = integrator.create_data_manifest(deduped_data, self.test_data_path)

        # Step 2: Simulate model training with integrated data
        training_samples = len(integrated_data)
        contributed_samples = len(deduped_data)

        new_model = {
            "type": "mock_model",
            "version": "2.0.0",
            "training_samples": training_samples,
            "contributed_samples": contributed_samples,
            "data_hash": data_manifest["data_hash"],
            "metrics": {
                "accuracy": 0.88,
                "precision": 0.86,
                "recall": 0.89,
                "f1_score": 0.87,
                "auroc": 0.93,
            },
        }

        # Step 3: Simulate attestation output generation
        attestation_output = {
            "schema_version": "1.0",
            "run_id": "pipeline_test",
            "contributor_data_hash": data_manifest["data_hash"],
            "contributor_data_manifest": data_manifest,
            "new_model_metrics": new_model["metrics"],
            "training_samples": training_samples,
            "contributed_samples": contributed_samples,
        }

        # Validate pipeline simulation results
        assert integrated_data is not None
        assert len(integrated_data) == training_samples
        assert attestation_output["contributor_data_hash"] == data_manifest["data_hash"]
        assert attestation_output["training_samples"] > 0
        assert attestation_output["contributed_samples"] > 0

        # Verify data consistency
        hash1 = integrator.calculate_data_hash(deduped_data)
        hash2 = data_manifest["data_hash"]
        assert hash1 == hash2, "Data hashes should be consistent"

        logging.info("Pipeline simulation successful:")
        logging.info(f"  - Integrated {training_samples} total samples")
        logging.info(f"  - Added {contributed_samples} contributed samples")
        logging.info(f"  - Data hash: {data_manifest['data_hash'][:16]}...")
        logging.info(f"  - Mock model accuracy: {new_model['metrics']['accuracy']}")

        return attestation_output

    def test_error_handling_in_pipeline_context(self):
        """Test error handling scenarios in pipeline context."""
        integrator = DataIntegrator(random_seed=42)

        # Test 1: Invalid file path
        with pytest.raises(FileNotFoundError):
            integrator.load_data(
                Path("/nonexistent/file.csv"), run_id="error_test", metaflow_run_id="error_metaflow"
            )

        # Test 2: Schema validation failure
        invalid_data = pd.DataFrame({"wrong_column": [1, 2, 3], "another_wrong": ["a", "b", "c"]})

        with pytest.raises(ValueError, match="Missing required columns"):
            integrator.validate_schema(invalid_data, ["query_id", "label"])

        # Test 3: Invalid merge strategy
        base_data = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
        contrib_data = pd.DataFrame({"col1": [3, 4], "col2": ["c", "d"]})

        with pytest.raises(ValueError, match="Unknown merge strategy"):
            integrator.merge_datasets(
                base_data,
                contrib_data,
                merge_strategy="invalid_strategy",
                run_id="error_test",
                metaflow_run_id="error_metaflow",
            )

    def test_performance_with_larger_dataset(self):
        """Test performance with a larger dataset."""
        integrator = DataIntegrator(random_seed=42)

        # Create larger test dataset
        large_data = pd.DataFrame(
            {
                "query_id": [f"large_q_{i}" for i in range(1000)],
                "query_text": [f"large query {i}" for i in range(1000)],
                "feature_1": [0.1 * i for i in range(1000)],
                "feature_2": [0.2 * i for i in range(1000)],
                "feature_3": [0.3 * i for i in range(1000)],
                "label": [i % 2 for i in range(1000)],
            }
        )

        large_data_path = Path(self.temp_dir) / "large_data.csv"
        large_data.to_csv(large_data_path, index=False)

        import time

        start_time = time.time()

        # Load data
        loaded_data = integrator.load_data(
            large_data_path, run_id="perf_test", metaflow_run_id="perf_metaflow"
        )

        # Process data
        clean_data = integrator.remove_pii(loaded_data)
        deduped_data = integrator.deduplicate(clean_data)
        manifest = integrator.create_data_manifest(deduped_data, large_data_path)

        end_time = time.time()
        processing_time = end_time - start_time

        # Verify performance
        assert processing_time < 10.0  # Should complete within 10 seconds
        assert len(loaded_data) == 1000
        assert manifest["data_hash"] is not None

        logging.info(f"Performance test completed in {processing_time:.2f} seconds")
        logging.info(f"Processed {len(loaded_data)} rows successfully")
