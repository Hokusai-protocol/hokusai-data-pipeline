"""
Unit tests for model registration CLI commands.

MLflow is mocked throughout; real auth (MLFLOW_TRACKING_TOKEN / Authorization headers)
is exercised by integration tests against a live MLflow server.
"""

import os
import sys
from unittest.mock import patch

import pytest
from click.testing import CliRunner

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from src.cli._api import BenchmarkSpecLookupError
from src.cli.model import register


class TestModelRegistrationCLI:
    """Test the model registration CLI command"""

    @pytest.fixture
    def runner(self):
        """Create a CLI test runner"""
        return CliRunner()

    @pytest.fixture
    def mock_dependencies(self):
        """Mock all external dependencies"""
        with (
            patch("src.cli.model.DatabaseConnection") as mock_db,
            patch("src.cli.model.TokenOperations") as mock_token_ops,
            patch("src.cli.model.mlflow") as mock_mlflow,
            patch("src.cli.model.EventPublisher") as mock_publisher,
            patch("src.cli.model.MetricValidator") as mock_validator,
            patch("src.cli.model.BaselineComparator") as mock_comparator,
        ):
            # Configure mocks
            mock_validator.return_value.validate_metric_name.return_value = True
            mock_validator.return_value.validate_baseline.return_value = True

            mock_comparator.return_value.validate_improvement.return_value = {
                "meets_baseline": True,
                "improvement": 0.01,
                "improvement_percentage": 1.2,
            }

            mock_mlflow.start_run.return_value.__enter__.return_value.info.run_id = "test-run-id"

            yield {
                "db": mock_db,
                "token_ops": mock_token_ops,
                "mlflow": mock_mlflow,
                "publisher": mock_publisher,
                "validator": mock_validator,
                "comparator": mock_comparator,
            }

    def test_register_command_success(self, runner, mock_dependencies):
        """Test successful model registration"""
        with runner.isolated_filesystem():
            # Create a mock model file
            with open("model.pkl", "w") as f:
                f.write("mock model")

            result = runner.invoke(
                register,
                [
                    "--token-id",
                    "XRAY",
                    "--model-path",
                    "model.pkl",
                    "--metric",
                    "auroc",
                    "--baseline",
                    "0.82",
                ],
            )

            assert result.exit_code == 0
            assert "Registering model for token: XRAY" in result.output
            assert "Model registration complete" in result.output

    def test_register_command_invalid_metric(self, runner, mock_dependencies):
        """Test registration with invalid metric"""
        mock_dependencies["validator"].return_value.validate_metric_name.return_value = False

        with runner.isolated_filesystem():
            with open("model.pkl", "w") as f:
                f.write("mock model")

            result = runner.invoke(
                register,
                [
                    "--token-id",
                    "XRAY",
                    "--model-path",
                    "model.pkl",
                    "--metric",
                    "invalid_metric",
                    "--baseline",
                    "0.82",
                ],
            )

            assert result.exit_code != 0
            assert "Unsupported metric" in result.output

    def test_register_command_invalid_baseline(self, runner, mock_dependencies):
        """Test registration with invalid baseline"""
        mock_dependencies["validator"].return_value.validate_baseline.return_value = False

        with runner.isolated_filesystem():
            with open("model.pkl", "w") as f:
                f.write("mock model")

            result = runner.invoke(
                register,
                [
                    "--token-id",
                    "XRAY",
                    "--model-path",
                    "model.pkl",
                    "--metric",
                    "auroc",
                    "--baseline",
                    "1.5",  # Invalid baseline > 1
                ],
            )

            assert result.exit_code != 0
            assert "Invalid baseline value" in result.output

    def test_register_command_model_file_not_found(self, runner, mock_dependencies):
        """Test registration with non-existent model file"""
        result = runner.invoke(
            register,
            [
                "--token-id",
                "XRAY",
                "--model-path",
                "nonexistent.pkl",
                "--metric",
                "auroc",
                "--baseline",
                "0.82",
            ],
        )

        assert result.exit_code != 0

    def test_register_command_token_not_found(self, runner, mock_dependencies):
        """Test registration with non-existent token"""
        # Mock token validation to raise error
        mock_token_ops = mock_dependencies["token_ops"]
        mock_token_ops.return_value.validate_token_status.side_effect = ValueError(
            "Token XRAY not found"
        )

        with runner.isolated_filesystem():
            with open("model.pkl", "w") as f:
                f.write("mock model")

            result = runner.invoke(
                register,
                [
                    "--token-id",
                    "XRAY",
                    "--model-path",
                    "model.pkl",
                    "--metric",
                    "auroc",
                    "--baseline",
                    "0.82",
                ],
            )

            assert result.exit_code != 0
            assert "not found" in result.output

    def test_register_command_with_webhook(self, runner, mock_dependencies):
        """Test registration with webhook URL"""
        with runner.isolated_filesystem():
            with open("model.pkl", "w") as f:
                f.write("mock model")

            result = runner.invoke(
                register,
                [
                    "--token-id",
                    "XRAY",
                    "--model-path",
                    "model.pkl",
                    "--metric",
                    "auroc",
                    "--baseline",
                    "0.82",
                    "--webhook-url",
                    "https://example.com/webhook",
                ],
            )

            assert result.exit_code == 0
            # Verify webhook handler was registered
            mock_dependencies["publisher"].return_value.register_handler.assert_called()

    def test_register_command_performance_below_baseline(self, runner, mock_dependencies):
        """Test registration when model performance is below baseline"""
        mock_dependencies["comparator"].return_value.validate_improvement.return_value = {
            "meets_baseline": False,
            "improvement": -0.01,
            "improvement_percentage": -1.2,
        }

        with runner.isolated_filesystem():
            with open("model.pkl", "w") as f:
                f.write("mock model")

            result = runner.invoke(
                register,
                [
                    "--token-id",
                    "XRAY",
                    "--model-path",
                    "model.pkl",
                    "--metric",
                    "auroc",
                    "--baseline",
                    "0.82",
                ],
            )

            assert result.exit_code != 0
            assert "does not meet baseline requirement" in result.output

    # ------------------------------------------------------------------
    # Tests for --benchmark-spec-id flag
    # ------------------------------------------------------------------

    @pytest.fixture
    def mock_dependencies_with_spec(self, mock_dependencies):
        """Extend mock_dependencies with a fetch_benchmark_spec patch."""
        with patch("src.cli.model.fetch_benchmark_spec") as mock_fetch:
            mock_fetch.return_value = {
                "id": "bs-abc123",
                "model_id": "XRAY",
                "metric_name": "auroc",
                "metric_direction": "maximize",
                "baseline_value": 0.82,
                "is_active": True,
            }
            yield mock_dependencies, mock_fetch

    def test_register_with_benchmark_spec_id_happy_path(self, runner, mock_dependencies_with_spec):
        """Spec supplies metric and baseline; command succeeds end-to-end."""
        mock_deps, mock_fetch = mock_dependencies_with_spec

        with runner.isolated_filesystem():
            with open("model.pkl", "w") as f:
                f.write("mock model")

            result = runner.invoke(
                register,
                [
                    "--token-id",
                    "XRAY",
                    "--model-path",
                    "model.pkl",
                    "--benchmark-spec-id",
                    "bs-abc123",
                ],
                catch_exceptions=False,
            )

        assert result.exit_code == 0, result.output
        assert "Resolved benchmark spec bs-abc123" in result.output
        assert "Model registration complete" in result.output
        # Verify benchmark_spec_id tag was set on the MLflow run
        mock_deps["mlflow"].set_tag.assert_any_call("benchmark_spec_id", "bs-abc123")

    def test_register_with_benchmark_spec_id_token_mismatch(
        self, runner, mock_dependencies_with_spec
    ):
        """Spec model_id doesn't match --token-id → clean error."""
        mock_deps, mock_fetch = mock_dependencies_with_spec
        mock_fetch.return_value["model_id"] = "OTHER"

        with runner.isolated_filesystem():
            with open("model.pkl", "w") as f:
                f.write("mock model")

            result = runner.invoke(
                register,
                [
                    "--token-id",
                    "XRAY",
                    "--model-path",
                    "model.pkl",
                    "--benchmark-spec-id",
                    "bs-abc123",
                ],
            )

        assert result.exit_code != 0
        assert "bound to model 'OTHER'" in result.output

    def test_register_with_benchmark_spec_id_inactive(self, runner, mock_dependencies_with_spec):
        """Inactive spec → clean error."""
        mock_deps, mock_fetch = mock_dependencies_with_spec
        mock_fetch.return_value["is_active"] = False

        with runner.isolated_filesystem():
            with open("model.pkl", "w") as f:
                f.write("mock model")

            result = runner.invoke(
                register,
                [
                    "--token-id",
                    "XRAY",
                    "--model-path",
                    "model.pkl",
                    "--benchmark-spec-id",
                    "bs-abc123",
                ],
            )

        assert result.exit_code != 0
        assert "inactive" in result.output

    def test_register_with_benchmark_spec_id_not_found(self, runner, mock_dependencies_with_spec):
        """API returns 404 / fetch raises → clean error."""
        mock_deps, mock_fetch = mock_dependencies_with_spec
        mock_fetch.side_effect = BenchmarkSpecLookupError("Benchmark spec 'bs-abc123' not found")

        with runner.isolated_filesystem():
            with open("model.pkl", "w") as f:
                f.write("mock model")

            result = runner.invoke(
                register,
                [
                    "--token-id",
                    "XRAY",
                    "--model-path",
                    "model.pkl",
                    "--benchmark-spec-id",
                    "bs-abc123",
                ],
            )

        assert result.exit_code != 0
        assert "not found" in result.output

    def test_register_with_explicit_overrides_logs_warning(
        self, runner, mock_dependencies_with_spec
    ):
        """Explicit --metric and --baseline differ from spec → warnings logged, values used."""
        mock_deps, mock_fetch = mock_dependencies_with_spec
        mock_fetch.return_value["metric_name"] = "accuracy"
        mock_fetch.return_value["baseline_value"] = 0.7

        with runner.isolated_filesystem():
            with open("model.pkl", "w") as f:
                f.write("mock model")

            result = runner.invoke(
                register,
                [
                    "--token-id",
                    "XRAY",
                    "--model-path",
                    "model.pkl",
                    "--benchmark-spec-id",
                    "bs-abc123",
                    "--metric",
                    "auroc",
                    "--baseline",
                    "0.82",
                ],
            )

        # Both warnings must appear
        combined = result.output + (result.stderr if hasattr(result, "stderr") else "")
        assert "auroc" in combined and "accuracy" in combined
        assert "0.82" in combined and "0.7" in combined
        assert result.exit_code == 0, result.output

    def test_register_without_metric_or_baseline_and_no_spec_id_fails(
        self, runner, mock_dependencies
    ):
        """Omitting both --metric/--baseline and --benchmark-spec-id → clear error."""
        with runner.isolated_filesystem():
            with open("model.pkl", "w") as f:
                f.write("mock model")

            result = runner.invoke(
                register,
                [
                    "--token-id",
                    "XRAY",
                    "--model-path",
                    "model.pkl",
                ],
            )

        assert result.exit_code != 0
        assert "required" in result.output.lower()

    def test_register_with_spec_missing_baseline(self, runner, mock_dependencies_with_spec):
        """Spec has no baseline_value and --baseline not provided → clear error."""
        mock_deps, mock_fetch = mock_dependencies_with_spec
        mock_fetch.return_value["baseline_value"] = None

        with runner.isolated_filesystem():
            with open("model.pkl", "w") as f:
                f.write("mock model")

            result = runner.invoke(
                register,
                [
                    "--token-id",
                    "XRAY",
                    "--model-path",
                    "model.pkl",
                    "--benchmark-spec-id",
                    "bs-abc123",
                ],
            )

        assert result.exit_code != 0
        assert "no baseline_value" in result.output
