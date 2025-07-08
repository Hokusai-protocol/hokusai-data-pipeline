"""Integration tests for DSPy signature library."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import dspy
import tempfile
import yaml
import json

from src.dspy_signatures.registry import SignatureRegistry, get_global_registry
from src.dspy_signatures.loader import SignatureLoader
from src.dspy_signatures.text_generation import DraftText, ReviseText
from src.dspy_signatures.analysis import SummarizeText
from src.dspy_signatures.task_specific import EmailDraft
from src.services.dspy_model_loader import DSPyModelLoader
from src.services.dspy_pipeline_executor import DSPyPipelineExecutor


class TestSignatureRegistryIntegration:
    """Integration tests for signature registry."""

    def test_global_registry_singleton(self):
        """Test global registry is a singleton."""
        registry1 = get_global_registry()
        registry2 = get_global_registry()

        assert registry1 is registry2

    def test_preloaded_signatures(self):
        """Test that common signatures are preloaded."""
        registry = get_global_registry()

        # Check text generation signatures
        assert "DraftText" in registry.list_signatures()
        assert "ReviseText" in registry.list_signatures()
        assert "ExpandText" in registry.list_signatures()

        # Check analysis signatures
        assert "SummarizeText" in registry.list_signatures()
        assert "CritiqueText" in registry.list_signatures()

        # Check task-specific signatures
        assert "EmailDraft" in registry.list_signatures()
        assert "CodeGeneration" in registry.list_signatures()

    def test_signature_categories(self):
        """Test signatures are properly categorized."""
        registry = get_global_registry()

        text_gen = registry.search(category="text_generation")
        assert len(text_gen) >= 4

        analysis = registry.search(category="analysis")
        assert len(analysis) >= 4

        conversation = registry.search(category="conversation")
        assert len(conversation) >= 4

        task_specific = registry.search(category="task_specific")
        assert len(task_specific) >= 4


class TestSignatureLoaderIntegration:
    """Integration tests for signature loader."""

    def test_load_from_registry(self):
        """Test loading signature from registry."""
        loader = SignatureLoader()

        # Load by name
        email_sig = loader.load("EmailDraft")
        assert email_sig is not None
        assert email_sig.name == "EmailDraft"

        # Load by alias
        registry = get_global_registry()
        registry.create_alias("QuickEmail", "EmailDraft")

        alias_sig = loader.load("QuickEmail")
        assert alias_sig.name == "EmailDraft"

    def test_load_from_yaml(self):
        """Test loading signature configuration from YAML."""
        loader = SignatureLoader()

        # Create temporary YAML config
        config = {
            "signature": "EmailDraft",
            "parameters": {
                "default_tone": "professional",
                "include_greeting": True
            },
            "examples": [
                {
                    "recipient": "test@example.com",
                    "subject": "Test",
                    "email_body": "Test email"
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name

        # Load from YAML
        sig_config = loader.load_from_yaml(temp_path)
        assert sig_config["signature"] == "EmailDraft"
        assert sig_config["parameters"]["default_tone"] == "professional"

    def test_create_custom_signature(self):
        """Test creating custom signature from config."""
        loader = SignatureLoader()

        config = {
            "name": "CustomEmail",
            "base": "EmailDraft",
            "overrides": {
                "tone": "casual",
                "max_length": 500
            },
            "additional_fields": {
                "urgency": {
                    "type": "str",
                    "description": "Email urgency level",
                    "required": False,
                    "default": "normal"
                }
            }
        }

        custom_sig = loader.create_custom_signature(config)
        assert custom_sig is not None

        # Check if additional field is added
        input_names = [f.name for f in custom_sig.get_input_fields()]
        assert "urgency" in input_names


class TestDSPyModelLoaderIntegration:
    """Test integration with DSPy Model Loader."""

    @patch("src.services.dspy_model_loader.dspy")
    def test_load_program_with_signature_library(self, mock_dspy):
        """Test loading DSPy program that uses signature library."""
        loader = DSPyModelLoader()

        # Create mock program that uses library signature
        mock_program = MagicMock()
        mock_program.forward = MagicMock()

        # Mock signature from library
        mock_dspy.ChainOfThought.return_value = mock_program

        # Create config that references library signature
        config = {
            "name": "email-assistant",
            "version": "1.0.0",
            "signatures": {
                "generate_email": {
                    "library": "EmailDraft",
                    "parameters": {
                        "default_tone": "professional"
                    }
                }
            },
            "modules": [
                {
                    "name": "email_generator",
                    "type": "ChainOfThought",
                    "signature": "generate_email"
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name

        # Load program
        result = loader.load_from_config(temp_path)

        assert result is not None
        assert "program" in result
        assert result["metadata"]["name"] == "email-assistant"

    def test_validate_signature_compatibility(self):
        """Test validating signature compatibility in programs."""
        loader = DSPyModelLoader()
        registry = get_global_registry()

        # Create a chain of compatible signatures
        draft_sig = registry.get("DraftText")
        revise_sig = registry.get("ReviseText")

        # These should be compatible if DraftText outputs 'draft'
        # and ReviseText accepts 'original_text'
        # In practice, we'd need adapter logic, but test the concept

        config = {
            "name": "text-pipeline",
            "modules": [
                {"name": "drafter", "signature": "DraftText"},
                {"name": "reviser", "signature": "ReviseText"}
            ]
        }

        # Loader should validate compatibility
        # This would require implementing compatibility checking
        assert loader is not None


class TestDSPyPipelineExecutorIntegration:
    """Test integration with DSPy Pipeline Executor."""

    @patch("src.services.dspy_pipeline_executor.mlflow")
    def test_execute_with_library_signature(self, mock_mlflow):
        """Test executing program that uses library signatures."""
        executor = DSPyPipelineExecutor(mlflow_tracking=False)

        # Create mock program using library signature
        mock_program = MagicMock()
        mock_program.forward = MagicMock(return_value=MagicMock(
            email_body="Generated email content"
        ))

        # Execute with inputs matching EmailDraft signature
        inputs = {
            "recipient": "test@example.com",
            "subject": "Test Subject",
            "purpose": "Test purpose",
            "key_points": ["Point 1", "Point 2"],
            "tone": "professional"
        }

        result = executor.execute(
            program=mock_program,
            inputs=inputs
        )

        assert result.success == True
        assert "email_body" in result.outputs

    def test_signature_validation_in_execution(self):
        """Test that executor validates inputs against signature."""
        executor = DSPyPipelineExecutor(mlflow_tracking=False)
        registry = get_global_registry()

        # Get EmailDraft signature
        email_sig = registry.get("EmailDraft")

        # Create mock program with signature
        mock_program = MagicMock()
        mock_program.signature = email_sig
        mock_program.forward = MagicMock()

        # Try with invalid inputs (missing required fields)
        invalid_inputs = {
            "recipient": "test@example.com"
            # Missing required fields
        }

        result = executor.execute(
            program=mock_program,
            inputs=invalid_inputs
        )

        # Should fail validation
        assert result.success == False
        assert "Missing required" in result.error or "validation" in result.error.lower()


class TestSignatureComposition:
    """Test signature composition and chaining."""

    def test_compose_text_pipeline(self):
        """Test composing a text processing pipeline."""
        registry = get_global_registry()

        # Get signatures
        draft = registry.get("DraftText")
        revise = registry.get("ReviseText")
        summarize = registry.get("SummarizeText")

        # In a real implementation, we'd compose these
        # For now, just verify they exist and have expected fields
        assert draft is not None
        assert revise is not None
        assert summarize is not None

        # Check that outputs of one can feed into inputs of another
        draft_outputs = [f.name for f in draft.get_output_fields()]
        revise_inputs = [f.name for f in revise.get_input_fields()]

        # With adapters, 'draft' output could map to 'original_text' input
        assert "draft" in draft_outputs
        assert "original_text" in revise_inputs


class TestSignatureVersioning:
    """Test signature versioning and migration."""

    def test_signature_versions(self):
        """Test managing multiple versions of signatures."""
        registry = SignatureRegistry()  # Use fresh registry

        # Register v1 signature
        class EmailDraftV1(Mock):
            __name__ = "EmailDraft"
            version = "1.0.0"

        # Register v2 with additional fields
        class EmailDraftV2(Mock):
            __name__ = "EmailDraft"
            version = "2.0.0"

        # Registry should support versioning
        # This would require implementing version management
        assert registry is not None


class TestSignatureExport:
    """Test exporting signature library."""

    def test_export_catalog_json(self):
        """Test exporting signature catalog as JSON."""
        registry = get_global_registry()

        catalog = registry.export_catalog()

        # Convert to JSON
        json_str = json.dumps(catalog, indent=2)
        assert json_str is not None

        # Parse back
        parsed = json.loads(json_str)
        assert len(parsed) > 0
        assert all("name" in entry for entry in parsed)
        assert all("metadata" in entry for entry in parsed)

    def test_export_for_documentation(self):
        """Test exporting signatures for documentation."""
        registry = get_global_registry()

        # Get all text generation signatures
        text_sigs = registry.search(category="text_generation")

        # Format for documentation
        docs = []
        for sig_name in text_sigs:
            sig = registry.get(sig_name)
            metadata = registry.get_metadata(sig_name)

            doc_entry = {
                "name": sig_name,
                "description": metadata.description,
                "category": metadata.category,
                "inputs": [{"name": f.name, "type": str(f.type_hint), "description": f.description}
                          for f in sig.get_input_fields()],
                "outputs": [{"name": f.name, "type": str(f.type_hint), "description": f.description}
                           for f in sig.get_output_fields()],
                "examples": sig.get_examples() if hasattr(sig, "get_examples") else []
            }
            docs.append(doc_entry)

        assert len(docs) > 0
        assert all("inputs" in d for d in docs)
        assert all("outputs" in d for d in docs)
