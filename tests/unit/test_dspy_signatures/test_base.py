"""Unit tests for base signature classes."""

import pytest

from src.dspy_signatures.base import (
    BaseSignature,
    SignatureComposer,
    SignatureField,
    SignatureValidator,
)


class TestSignatureField:
    """Test cases for SignatureField."""

    def test_field_creation(self):
        """Test creating a signature field."""
        field = SignatureField(
            name="text",
            description="Input text to process",
            type_hint=str,
            required=True,
            default=None,
        )

        assert field.name == "text"
        assert field.description == "Input text to process"
        assert field.type_hint == str
        assert field.required
        assert field.default is None

    def test_field_with_default(self):
        """Test field with default value."""
        field = SignatureField(
            name="max_length",
            description="Maximum length of output",
            type_hint=int,
            required=False,
            default=100,
        )

        assert not field.required
        assert field.default == 100

    def test_field_validation(self):
        """Test field validates type hints."""
        field = SignatureField(
            name="count", description="Number of items", type_hint=int, required=True
        )

        # Valid value
        assert field.validate(5)

        # Invalid type
        assert not field.validate("five")

        # None for required field
        assert not field.validate(None)

    def test_field_with_optional(self):
        """Test optional field validation."""
        field = SignatureField(
            name="context",
            description="Optional context",
            type_hint=str,
            required=False,
            default="",
        )

        assert field.validate(None)
        assert field.validate("some context")
        assert not field.validate(123)


class TestBaseSignature:
    """Test cases for BaseSignature."""

    def test_base_signature_creation(self):
        """Test creating a base signature."""

        class TestSignature(BaseSignature):
            """Test signature for unit tests."""

            @classmethod
            def get_input_fields(cls):
                return [
                    SignatureField("text", "Input text", str, True),
                    SignatureField("context", "Context", str, False, ""),
                ]

            @classmethod
            def get_output_fields(cls):
                return [SignatureField("result", "Result", str, True)]

        sig = TestSignature()

        assert sig.name == "TestSignature"
        assert len(sig.input_fields) == 2
        assert len(sig.output_fields) == 1
        assert sig.description == "Test signature for unit tests."

    def test_signature_to_dspy(self):
        """Test converting to DSPy signature."""

        class EmailSignature(BaseSignature):
            """Generate email content."""

            @classmethod
            def get_input_fields(cls):
                return [
                    SignatureField("recipient", "Email recipient", str, True),
                    SignatureField("subject", "Email subject", str, True),
                    SignatureField("context", "Email context", str, False, ""),
                ]

            @classmethod
            def get_output_fields(cls):
                return [SignatureField("email_body", "Generated email body", str, True)]

        sig = EmailSignature()
        dspy_sig = sig.to_dspy_signature()

        # Check if it creates a valid DSPy signature string
        assert "recipient" in dspy_sig
        assert "subject" in dspy_sig
        assert "email_body" in dspy_sig
        assert "->" in dspy_sig

    def test_signature_validation(self):
        """Test signature input validation."""

        class ValidatedSignature(BaseSignature):
            """Signature with validation."""

            @classmethod
            def get_input_fields(cls):
                return [
                    SignatureField("number", "A number", int, True),
                    SignatureField("text", "Some text", str, True),
                ]

            @classmethod
            def get_output_fields(cls):
                return [SignatureField("result", "Result", str, True)]

        sig = ValidatedSignature()

        # Valid inputs
        valid_inputs = {"number": 42, "text": "hello"}
        assert sig.validate_inputs(valid_inputs)

        # Missing required field
        invalid_inputs = {"number": 42}
        with pytest.raises(ValueError, match="Missing required field: text"):
            sig.validate_inputs(invalid_inputs)

        # Wrong type
        invalid_inputs = {"number": "not a number", "text": "hello"}
        with pytest.raises(ValueError, match="Invalid type for field 'number'"):
            sig.validate_inputs(invalid_inputs)

    def test_signature_with_examples(self):
        """Test signature with example inputs/outputs."""

        class ExampleSignature(BaseSignature):
            """Signature with examples."""

            @classmethod
            def get_input_fields(cls):
                return [SignatureField("query", "User query", str, True)]

            @classmethod
            def get_output_fields(cls):
                return [SignatureField("answer", "Answer", str, True)]

            @classmethod
            def get_examples(cls):
                return [
                    {"query": "What is 2+2?", "answer": "4"},
                    {"query": "Capital of France?", "answer": "Paris"},
                ]

        sig = ExampleSignature()
        examples = sig.get_examples()

        assert len(examples) == 2
        assert examples[0]["query"] == "What is 2+2?"
        assert examples[0]["answer"] == "4"


class TestSignatureValidator:
    """Test cases for SignatureValidator."""

    def test_validator_initialization(self):
        """Test validator initialization."""
        validator = SignatureValidator()
        assert validator.rules is not None

    def test_validate_signature_class(self):
        """Test validating a signature class."""
        validator = SignatureValidator()

        class GoodSignature(BaseSignature):
            """Valid signature."""

            @classmethod
            def get_input_fields(cls):
                return [SignatureField("input", "Input", str, True)]

            @classmethod
            def get_output_fields(cls):
                return [SignatureField("output", "Output", str, True)]

        # Should not raise any errors
        validator.validate_signature_class(GoodSignature)

    def test_validate_signature_without_fields(self):
        """Test validating signature without fields."""
        validator = SignatureValidator()

        class BadSignature(BaseSignature):
            """Invalid signature without fields."""

            @classmethod
            def get_input_fields(cls):
                return []

            @classmethod
            def get_output_fields(cls):
                return []

        with pytest.raises(ValueError, match="must have at least one input field"):
            validator.validate_signature_class(BadSignature)

    def test_validate_field_names(self):
        """Test field name validation."""
        validator = SignatureValidator()

        # Valid field names
        assert validator.validate_field_name("text_input")
        assert validator.validate_field_name("query")
        assert validator.validate_field_name("user_id")

        # Invalid field names
        assert not validator.validate_field_name("123start")
        assert not validator.validate_field_name("has-dash")
        assert not validator.validate_field_name("has space")
        assert not validator.validate_field_name("")


class TestSignatureComposer:
    """Test cases for SignatureComposer."""

    def test_compose_signatures(self):
        """Test composing two signatures."""
        composer = SignatureComposer()

        class FirstSignature(BaseSignature):
            """First signature in chain."""

            @classmethod
            def get_input_fields(cls):
                return [SignatureField("text", "Input text", str, True)]

            @classmethod
            def get_output_fields(cls):
                return [SignatureField("summary", "Summary", str, True)]

        class SecondSignature(BaseSignature):
            """Second signature in chain."""

            @classmethod
            def get_input_fields(cls):
                return [SignatureField("summary", "Summary text", str, True)]

            @classmethod
            def get_output_fields(cls):
                return [SignatureField("analysis", "Analysis", str, True)]

        # Compose signatures
        composed = composer.compose(FirstSignature, SecondSignature)

        assert composed.__name__ == "FirstSignature_SecondSignature"
        assert len(composed.get_input_fields()) == 1
        assert composed.get_input_fields()[0].name == "text"
        assert len(composed.get_output_fields()) == 1
        assert composed.get_output_fields()[0].name == "analysis"

    def test_compose_incompatible_signatures(self):
        """Test composing incompatible signatures."""
        composer = SignatureComposer()

        class FirstSignature(BaseSignature):
            """First signature."""

            @classmethod
            def get_input_fields(cls):
                return [SignatureField("text", "Text", str, True)]

            @classmethod
            def get_output_fields(cls):
                return [SignatureField("number", "Number", int, True)]

        class SecondSignature(BaseSignature):
            """Second signature."""

            @classmethod
            def get_input_fields(cls):
                return [SignatureField("data", "Data", str, True)]

            @classmethod
            def get_output_fields(cls):
                return [SignatureField("result", "Result", str, True)]

        with pytest.raises(ValueError, match="Cannot compose"):
            composer.compose(FirstSignature, SecondSignature)

    def test_merge_signatures(self):
        """Test merging signatures (parallel execution)."""
        composer = SignatureComposer()

        class TextSignature(BaseSignature):
            """Process text."""

            @classmethod
            def get_input_fields(cls):
                return [
                    SignatureField("text", "Text", str, True),
                    SignatureField("lang", "Language", str, True),
                ]

            @classmethod
            def get_output_fields(cls):
                return [SignatureField("processed", "Processed text", str, True)]

        class MetaSignature(BaseSignature):
            """Extract metadata."""

            @classmethod
            def get_input_fields(cls):
                return [
                    SignatureField("text", "Text", str, True),
                    SignatureField("format", "Format", str, False, "json"),
                ]

            @classmethod
            def get_output_fields(cls):
                return [SignatureField("metadata", "Metadata", dict, True)]

        # Merge signatures
        merged = composer.merge(TextSignature, MetaSignature)

        # Should have union of input fields
        input_names = [f.name for f in merged.get_input_fields()]
        assert "text" in input_names
        assert "lang" in input_names
        assert "format" in input_names

        # Should have all output fields
        output_names = [f.name for f in merged.get_output_fields()]
        assert "processed" in output_names
        assert "metadata" in output_names
