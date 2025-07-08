"""Unit tests for CLI teleprompt commands."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner
import json
from datetime import datetime, timedelta

from src.cli.teleprompt import (
    teleprompt, optimize, list_traces, list_attestations,
    show_attestation, calculate_rewards
)
from src.services.teleprompt_finetuner import OptimizationResult
from src.services.optimization_attestation import OptimizationAttestation


class TestTelepromptCLI:
    """Test suite for teleprompt CLI commands."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_teleprompt_group(self):
        """Test teleprompt command group."""
        result = self.runner.invoke(teleprompt, ["--help"])
        assert result.exit_code == 0
        assert "Manage teleprompt fine-tuning pipeline" in result.output

    @patch("src.cli.teleprompt.DSPyModelLoader")
    @patch("src.cli.teleprompt.TelepromptFinetuner")
    def test_optimize_command_success(self, mock_finetuner_class, mock_loader_class):
        """Test successful optimization command."""
        # Mock loader
        mock_loader = Mock()
        mock_program = Mock()
        mock_loader.load_signature_from_library.return_value = mock_program
        mock_loader_class.return_value = mock_loader

        # Mock optimization result
        mock_result = OptimizationResult(
            success=True,
            trace_count=5000,
            optimization_time=120.5,
            strategy="bootstrap_fewshot",
            contributors={"user1": {"address": "0x123", "weight": 1.0, "trace_count": 5000}}
        )

        # Mock deltaone result
        mock_deltaone = {
            "deltaone_achieved": True,
            "delta": 0.025
        }

        # Mock attestation
        mock_attestation = {
            "attestation_hash": "abcd1234567890"
        }

        # Mock finetuner
        mock_finetuner = Mock()
        mock_finetuner.run_optimization.return_value = mock_result
        mock_finetuner.evaluate_deltaone.return_value = mock_deltaone
        mock_finetuner.generate_attestation.return_value = mock_attestation
        mock_finetuner_class.return_value = mock_finetuner

        # Run command
        result = self.runner.invoke(optimize, [
            "--program", "EmailDraft",
            "--days", "7",
            "--min-traces", "1000",
            "--outcome-metric", "reply_rate",
            "--deltaone-threshold", "0.01"
        ])

        assert result.exit_code == 0
        assert "✓ Optimization successful!" in result.output
        assert "Traces used: 5000" in result.output
        assert "Performance delta: 2.50%" in result.output
        assert "🎉 DeltaOne threshold reached!" in result.output

    @patch("src.cli.teleprompt.DSPyModelLoader")
    @patch("src.cli.teleprompt.TelepromptFinetuner")
    def test_optimize_command_failure(self, mock_finetuner_class, mock_loader_class):
        """Test failed optimization command."""
        # Mock loader
        mock_loader = Mock()
        mock_program = Mock()
        mock_loader.load_signature_from_library.return_value = mock_program
        mock_loader_class.return_value = mock_loader

        # Mock failed result
        mock_result = OptimizationResult(
            success=False,
            error_message="Insufficient traces"
        )

        # Mock finetuner
        mock_finetuner = Mock()
        mock_finetuner.run_optimization.return_value = mock_result
        mock_finetuner_class.return_value = mock_finetuner

        result = self.runner.invoke(optimize, [
            "--program", "EmailDraft",
            "--days", "7"
        ])

        assert result.exit_code == 0
        assert "Optimization failed: Insufficient traces" in result.output

    @patch("src.cli.teleprompt.DSPyModelLoader")
    @patch("src.cli.teleprompt.TelepromptFinetuner")
    def test_optimize_with_save_model(self, mock_finetuner_class, mock_loader_class):
        """Test optimization with model saving."""
        # Mock loader
        mock_loader = Mock()
        mock_program = Mock()
        mock_loader.load_signature_from_library.return_value = mock_program
        mock_loader_class.return_value = mock_loader

        # Mock successful optimization
        mock_result = OptimizationResult(
            success=True,
            model_version="1.0.0-opt-bfs-20240115120000",
            trace_count=5000,
            optimization_time=120.5,
            strategy="bootstrap_fewshot",
            contributors={}
        )

        mock_deltaone = {
            "deltaone_achieved": True,
            "delta": 0.025
        }

        mock_model_info = {
            "model_name": "EmailDraft-Optimized",
            "version": "1.0.0-opt-bfs-20240115120000"
        }

        # Mock finetuner
        mock_finetuner = Mock()
        mock_finetuner.run_optimization.return_value = mock_result
        mock_finetuner.evaluate_deltaone.return_value = mock_deltaone
        mock_finetuner.generate_attestation.return_value = {"attestation_hash": "abc123"}
        mock_finetuner.save_optimized_model.return_value = mock_model_info
        mock_finetuner_class.return_value = mock_finetuner

        result = self.runner.invoke(optimize, [
            "--program", "EmailDraft",
            "--save-model",
            "--model-name", "MyOptimizedModel"
        ])

        assert result.exit_code == 0
        assert "Model saved: MyOptimizedModel" in result.output

    @patch("src.cli.teleprompt.TraceLoader")
    def test_list_traces_command(self, mock_loader_class):
        """Test list traces command."""
        # Mock traces
        mock_traces = [
            {
                "program_name": "EmailDraft",
                "timestamp": datetime.now(),
                "outcome_score": 0.85,
                "contributor_id": "user123"
            }
        ]

        mock_loader = Mock()
        mock_loader.load_traces.return_value = mock_traces
        mock_loader_class.return_value = mock_loader

        result = self.runner.invoke(list_traces, [
            "--program", "EmailDraft",
            "--limit", "10"
        ])

        assert result.exit_code == 0
        assert "Found 1 traces" in result.output
        assert "EmailDraft" in result.output

    @patch("src.cli.teleprompt.TraceLoader")
    def test_list_traces_json_format(self, mock_loader_class):
        """Test list traces with JSON format."""
        mock_traces = [{"program_name": "EmailDraft", "outcome_score": 0.85}]

        mock_loader = Mock()
        mock_loader.load_traces.return_value = mock_traces
        mock_loader_class.return_value = mock_loader

        result = self.runner.invoke(list_traces, [
            "--format", "json"
        ])

        assert result.exit_code == 0
        assert "program_name" in result.output

    @patch("src.cli.teleprompt.OptimizationAttestationService")
    def test_list_attestations_command(self, mock_service_class):
        """Test list attestations command."""
        # Mock attestation
        mock_attestation = Mock()
        mock_attestation.attestation_id = "att_123456789"
        mock_attestation.model_id = "EmailDraft"
        mock_attestation.performance_delta = 0.023
        mock_attestation.trace_count = 5000
        mock_attestation.timestamp = "2024-01-15T12:00:00"

        mock_service = Mock()
        mock_service.list_attestations.return_value = [mock_attestation]
        mock_service_class.return_value = mock_service

        result = self.runner.invoke(list_attestations, [
            "--model-id", "EmailDraft"
        ])

        assert result.exit_code == 0
        assert "Found 1 attestations" in result.output
        assert "EmailDraft" in result.output

    @patch("src.cli.teleprompt.OptimizationAttestationService")
    def test_show_attestation_command(self, mock_service_class):
        """Test show attestation command."""
        # Mock attestation
        mock_attestation = OptimizationAttestation(
            attestation_id="att_123456789",
            model_id="EmailDraft",
            baseline_version="1.0.0",
            optimized_version="1.0.0-opt",
            optimization_strategy="bootstrap_fewshot",
            deltaone_achieved=True,
            performance_delta=0.023,
            baseline_metrics={"accuracy": 0.85},
            optimized_metrics={"accuracy": 0.873},
            trace_count=5000,
            optimization_time_seconds=120.5,
            outcome_metric="accuracy",
            contributors=[{
                "contributor_id": "user1",
                "address": "0x123456789",
                "weight": 1.0,
                "trace_count": 5000
            }],
            attestation_hash="abcd1234"
        )

        mock_service = Mock()
        mock_service.list_attestations.return_value = [mock_attestation]
        mock_service.verify_attestation.return_value = True
        mock_service_class.return_value = mock_service

        result = self.runner.invoke(show_attestation, ["att_123"])

        assert result.exit_code == 0
        assert "Attestation: att_123456789" in result.output
        assert "Model ID: EmailDraft" in result.output
        assert "Performance Delta: 2.30%" in result.output

    @patch("src.cli.teleprompt.OptimizationAttestationService")
    def test_show_attestation_json_format(self, mock_service_class):
        """Test show attestation with JSON format."""
        mock_attestation = Mock()
        mock_attestation.attestation_id = "att_123456789"
        mock_attestation.to_json.return_value = '{"attestation_id": "att_123456789"}'

        mock_service = Mock()
        mock_service.list_attestations.return_value = [mock_attestation]
        mock_service_class.return_value = mock_service

        result = self.runner.invoke(show_attestation, [
            "att_123",
            "--format", "json"
        ])

        assert result.exit_code == 0
        assert "attestation_id" in result.output

    @patch("src.cli.teleprompt.OptimizationAttestationService")
    def test_calculate_rewards_command(self, mock_service_class):
        """Test calculate rewards command."""
        # Mock attestation
        mock_attestation = Mock()
        mock_attestation.attestation_id = "att_123456789"
        mock_attestation.deltaone_achieved = True
        mock_attestation.contributors = [
            {
                "contributor_id": "user1",
                "address": "0x1234567890abcdef",
                "weight": 0.7,
                "trace_count": 3500
            },
            {
                "contributor_id": "user2",
                "address": "0xabcdef1234567890",
                "weight": 0.3,
                "trace_count": 1500
            }
        ]

        mock_rewards = {
            "0x1234567890abcdef": 700.0,
            "0xabcdef1234567890": 300.0
        }

        mock_service = Mock()
        mock_service.list_attestations.return_value = [mock_attestation]
        mock_service.calculate_rewards.return_value = mock_rewards
        mock_service_class.return_value = mock_service

        result = self.runner.invoke(calculate_rewards, [
            "att_123",
            "--total-reward", "1000",
            "--token", "HOKU"
        ])

        assert result.exit_code == 0
        assert "Reward Distribution (1000.0 HOKU)" in result.output
        assert "700.000000 HOKU" in result.output
        assert "300.000000 HOKU" in result.output

    @patch("src.cli.teleprompt.OptimizationAttestationService")
    def test_calculate_rewards_no_deltaone(self, mock_service_class):
        """Test calculate rewards when DeltaOne not achieved."""
        mock_attestation = Mock()
        mock_attestation.attestation_id = "att_123456789"
        mock_attestation.deltaone_achieved = False

        mock_service = Mock()
        mock_service.list_attestations.return_value = [mock_attestation]
        mock_service_class.return_value = mock_service

        result = self.runner.invoke(calculate_rewards, [
            "att_123",
            "--total-reward", "1000"
        ])

        assert result.exit_code == 0
        assert "Attestation did not achieve DeltaOne - no rewards" in result.output

    def test_optimize_invalid_strategy(self):
        """Test optimize with invalid strategy."""
        result = self.runner.invoke(optimize, [
            "--program", "EmailDraft",
            "--strategy", "invalid_strategy"
        ])

        assert result.exit_code != 0
        assert "Invalid value" in result.output

    @patch("src.cli.teleprompt.OptimizationAttestationService")
    def test_show_attestation_not_found(self, mock_service_class):
        """Test show attestation when not found."""
        mock_service = Mock()
        mock_service.list_attestations.return_value = []
        mock_service_class.return_value = mock_service

        result = self.runner.invoke(show_attestation, ["nonexistent"])

        assert result.exit_code == 0
        assert "No attestation found matching: nonexistent" in result.output

    @patch("src.cli.teleprompt.OptimizationAttestationService")
    def test_show_attestation_multiple_matches(self, mock_service_class):
        """Test show attestation with multiple matches."""
        mock_att1 = Mock()
        mock_att1.attestation_id = "att_123456789"

        mock_att2 = Mock()
        mock_att2.attestation_id = "att_123456790"

        mock_service = Mock()
        mock_service.list_attestations.return_value = [mock_att1, mock_att2]
        mock_service_class.return_value = mock_service

        result = self.runner.invoke(show_attestation, ["att_123"])

        assert result.exit_code == 0
        assert "Multiple attestations match" in result.output
