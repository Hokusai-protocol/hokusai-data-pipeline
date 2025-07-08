"""Unit tests for DSPy validators."""

import pytest
from unittest.mock import Mock, MagicMock

from src.services.dspy.validators import DSPyValidator


class MockDSPyProgram:
    """Mock DSPy program for testing."""

    def __init__(self, has_forward=True, has_signatures=True):
        if has_forward:
            self.forward = lambda self, x: x

        if has_signatures:
            # Mock signature with fields
            self.text_signature = Mock()
            self.text_signature.fields = {"input": "text", "output": "text"}
            self.text_signature.input_fields = {"prompt": Mock()}
            self.text_signature.output_fields = {"completion": Mock()}


class TestDSPyValidator:
    """Test suite for DSPy validator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = DSPyValidator()

    def test_validate_valid_config(self):
        """Test validating a valid configuration."""
        config = {
            "name": "test-model",
            "version": "1.0",
            "source": {
                "type": "local",
                "path": "/path/to/model.py"
            }
        }

        result = self.validator.validate_config(config)

        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_validate_config_missing_fields(self):
        """Test validation catches missing required fields."""
        config = {
            "name": "test-model"
            # Missing version and source
        }

        result = self.validator.validate_config(config)

        assert result["valid"] is False
        assert any("version" in error for error in result["errors"])
        assert any("source" in error for error in result["errors"])

    def test_validate_config_invalid_source(self):
        """Test validation of invalid source configuration."""
        config = {
            "name": "test",
            "version": "1.0",
            "source": "invalid"  # Should be dict
        }

        result = self.validator.validate_config(config)

        assert result["valid"] is False
        assert any("Source must be a dictionary" in error for error in result["errors"])

    def test_validate_config_with_signatures(self):
        """Test validation of signature configurations."""
        config = {
            "name": "test",
            "version": "1.0",
            "source": {"type": "local", "path": "test.py"},
            "signatures": {
                "sig1": {
                    "inputs": ["input1"],
                    "outputs": ["output1"]
                },
                "sig2": {
                    "inputs": "invalid",  # Should be list
                    "outputs": ["output2"]
                }
            }
        }

        result = self.validator.validate_config(config)

        assert result["valid"] is False
        assert any("sig2" in error and "inputs must be a list" in error
                  for error in result["errors"])

    def test_validate_valid_program(self):
        """Test validating a valid DSPy program."""
        program = MockDSPyProgram()

        result = self.validator.validate_program(program)

        assert result["valid"] is True
        assert len(result["errors"]) == 0
        assert "signatures" in result
        assert "text_signature" in result["signatures"]

    def test_validate_program_missing_forward(self):
        """Test validation catches missing forward method."""
        program = MockDSPyProgram(has_forward=False)

        result = self.validator.validate_program(program)

        assert result["valid"] is False
        assert any("forward" in error for error in result["errors"])

    def test_validate_program_none(self):
        """Test validation of None program."""
        result = self.validator.validate_program(None)

        assert result["valid"] is False
        assert any("None" in error for error in result["errors"])

    def test_validate_signature(self):
        """Test validating a single signature."""
        signature = Mock()
        signature.fields = {
            "input": Mock(type="text", description="Input text"),
            "output": Mock(type="text", description="Output text")
        }

        result = self.validator.validate_signature(signature)

        assert result["valid"] is True
        assert "input" in result["fields"]
        assert "output" in result["fields"]

    def test_validate_chains_config(self):
        """Test validation of chain configurations."""
        config = {
            "name": "test",
            "version": "1.0",
            "source": {"type": "local", "path": "test.py"},
            "signatures": {
                "sig1": {"inputs": ["a"], "outputs": ["b"]}
            },
            "chains": {
                "chain1": {
                    "steps": ["sig1"]  # Valid reference
                },
                "chain2": {
                    "steps": ["unknown_sig"]  # Invalid reference
                }
            }
        }

        result = self.validator.validate_config(config)

        assert result["valid"] is False
        assert any("unknown_sig" in error for error in result["errors"])

    def test_create_validation_report(self):
        """Test creating a validation report."""
        program = MockDSPyProgram()
        config = {
            "name": "test",
            "version": "1.0",
            "source": {"type": "local", "path": "test.py"}
        }

        report = self.validator.create_validation_report(program, config)

        assert "DSPy Program Validation Report" in report
        assert "Program Valid: True" in report
        assert "Configuration Valid: True" in report
        assert "Signatures Found:" in report

    def test_extract_signatures(self):
        """Test signature extraction from program."""
        program = MockDSPyProgram()

        result = self.validator.validate_program(program)
        signatures = result["signatures"]

        assert "text_signature" in signatures
        assert signatures["text_signature"]["type"] == "Mock"

    def test_validate_forward_method(self):
        """Test validation of forward method."""
        program = Mock()
        program.forward = "not_callable"  # Invalid

        result = self.validator.validate_program(program)

        assert result["valid"] is False
        assert any("not callable" in error for error in result["errors"])
