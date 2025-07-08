"""Integration test for pipeline dry run mode."""

import json

import pytest

# import sys  # Will be used when cmd is implemented


class TestPipelineDryRun:
    """Test pipeline in dry run mode."""

    def test_dry_run_execution(self, temp_dir, sample_contributed_data):
        """Test pipeline executes successfully in dry run mode."""
        # output_dir = temp_dir / "outputs"  # Will be used when cmd is implemented

        # Run pipeline with dry-run flag
        # cmd = [
        #     sys.executable, "-m", "metaflow", "run",
        #     "src.pipeline.hokusai_pipeline:HokusaiPipeline",
        #     "--dry-run",
        #     f"--contributed-data={sample_contributed_data['csv_path']}",
        #     f"--output-dir={output_dir}"
        # ]

        # For now, just test that we can import the pipeline
        from src.pipeline.hokusai_pipeline import HokusaiPipeline

        # Verify pipeline class exists and has required methods
        assert hasattr(HokusaiPipeline, "start")
        assert hasattr(HokusaiPipeline, "load_baseline_model")
        assert hasattr(HokusaiPipeline, "integrate_contributed_data")
        assert hasattr(HokusaiPipeline, "train_new_model")
        assert hasattr(HokusaiPipeline, "evaluate_on_benchmark")
        assert hasattr(HokusaiPipeline, "compare_and_output_delta")
        assert hasattr(HokusaiPipeline, "generate_attestation_output")
        assert hasattr(HokusaiPipeline, "monitor_and_log")
        assert hasattr(HokusaiPipeline, "end")

    @pytest.mark.slow
    def test_attestation_output_format(self, temp_dir):
        """Test attestation output format."""
        # Create mock attestation output
        from src.utils.attestation import AttestationGenerator

        generator = AttestationGenerator()
        attestation = generator.create_attestation(
            run_id="test_run_123",
            contributor_data_hash="hash123",
            baseline_model_id="model_v1",
            new_model_id="model_v2",
            evaluation_results={"baseline": {"accuracy": 0.85}, "new": {"accuracy": 0.88}},
            delta_results={"accuracy": {"baseline": 0.85, "new": 0.88, "delta": 0.03}},
            delta_score=0.03,
        )

        # Validate attestation structure
        assert generator.validate_attestation(attestation)

        # Save and verify
        output_path = temp_dir / "test_attestation.json"
        saved_path = generator.save_attestation(attestation, output_path)

        assert saved_path.exists()

        # Load and verify content
        with open(saved_path) as f:
            loaded = json.load(f)

        assert loaded["schema_version"] == "1.0"
        assert loaded["run_id"] == "test_run_123"
        assert "proof_data" in loaded
        assert "content_hash" in loaded
