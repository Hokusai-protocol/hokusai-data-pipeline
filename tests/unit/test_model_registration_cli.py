"""
Unit tests for model registration CLI commands
"""

import os
import sys
from unittest.mock import patch

import pytest
from click.testing import CliRunner

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
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
