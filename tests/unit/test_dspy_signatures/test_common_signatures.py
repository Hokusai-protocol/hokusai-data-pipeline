"""Unit tests for common DSPy signatures."""

import pytest
from unittest.mock import Mock, patch
import dspy

from src.dspy_signatures.text_generation import (
    DraftText,
    ReviseText,
    ExpandText,
    RefineText
)
from src.dspy_signatures.analysis import (
    CritiqueText,
    SummarizeText,
    ExtractInfo,
    ClassifyText
)
from src.dspy_signatures.conversation import (
    RespondToUser,
    ClarifyIntent,
    GenerateFollowUp,
    ResolveQuery
)
from src.dspy_signatures.task_specific import (
    EmailDraft,
    CodeGeneration,
    DataAnalysis,
    ReportGeneration
)


class TestTextGenerationSignatures:
    """Test cases for text generation signatures."""

    def test_draft_text_signature(self):
        """Test DraftText signature."""
        sig = DraftText()

        assert sig.name == "DraftText"
        assert sig.category == "text_generation"

        # Check input fields
        input_names = [f.name for f in sig.get_input_fields()]
        assert "topic" in input_names
        assert "purpose" in input_names
        assert "style" in input_names

        # Check output fields
        output_names = [f.name for f in sig.get_output_fields()]
        assert "draft" in output_names

        # Test with sample inputs
        inputs = {
            "topic": "AI in healthcare",
            "purpose": "blog post",
            "style": "informative"
        }
        assert sig.validate_inputs(inputs) == True

    def test_revise_text_signature(self):
        """Test ReviseText signature."""
        sig = ReviseText()

        assert sig.name == "ReviseText"

        input_names = [f.name for f in sig.get_input_fields()]
        assert "original_text" in input_names
        assert "feedback" in input_names
        assert "revision_goals" in input_names

        output_names = [f.name for f in sig.get_output_fields()]
        assert "revised_text" in output_names
        assert "changes_made" in output_names

    def test_expand_text_signature(self):
        """Test ExpandText signature."""
        sig = ExpandText()

        input_names = [f.name for f in sig.get_input_fields()]
        assert "text" in input_names
        assert "expansion_points" in input_names
        assert "target_length" in input_names

        output_names = [f.name for f in sig.get_output_fields()]
        assert "expanded_text" in output_names

        # Test with optional field
        inputs = {
            "text": "Brief text",
            "expansion_points": ["add examples", "provide details"]
        }
        assert sig.validate_inputs(inputs) == True

    def test_refine_text_signature(self):
        """Test RefineText signature."""
        sig = RefineText()

        input_names = [f.name for f in sig.get_input_fields()]
        assert "text" in input_names
        assert "refinement_criteria" in input_names

        output_names = [f.name for f in sig.get_output_fields()]
        assert "refined_text" in output_names
        assert "refinement_summary" in output_names


class TestAnalysisSignatures:
    """Test cases for analysis signatures."""

    def test_critique_text_signature(self):
        """Test CritiqueText signature."""
        sig = CritiqueText()

        assert sig.category == "analysis"

        input_names = [f.name for f in sig.get_input_fields()]
        assert "text" in input_names
        assert "criteria" in input_names
        assert "perspective" in input_names

        output_names = [f.name for f in sig.get_output_fields()]
        assert "critique" in output_names
        assert "strengths" in output_names
        assert "weaknesses" in output_names
        assert "suggestions" in output_names

    def test_summarize_text_signature(self):
        """Test SummarizeText signature."""
        sig = SummarizeText()

        input_names = [f.name for f in sig.get_input_fields()]
        assert "text" in input_names
        assert "max_length" in input_names
        assert "style" in input_names

        output_names = [f.name for f in sig.get_output_fields()]
        assert "summary" in output_names
        assert "key_points" in output_names

    def test_extract_info_signature(self):
        """Test ExtractInfo signature."""
        sig = ExtractInfo()

        input_names = [f.name for f in sig.get_input_fields()]
        assert "text" in input_names
        assert "info_types" in input_names
        assert "format" in input_names

        output_names = [f.name for f in sig.get_output_fields()]
        assert "extracted_info" in output_names
        assert "confidence_scores" in output_names

        # Test with specific info types
        inputs = {
            "text": "John Doe, CEO of TechCorp, announced...",
            "info_types": ["names", "titles", "organizations"],
            "format": "json"
        }
        assert sig.validate_inputs(inputs) == True

    def test_classify_text_signature(self):
        """Test ClassifyText signature."""
        sig = ClassifyText()

        input_names = [f.name for f in sig.get_input_fields()]
        assert "text" in input_names
        assert "categories" in input_names
        assert "multi_label" in input_names

        output_names = [f.name for f in sig.get_output_fields()]
        assert "classification" in output_names
        assert "confidence" in output_names
        assert "reasoning" in output_names


class TestConversationSignatures:
    """Test cases for conversation signatures."""

    def test_respond_to_user_signature(self):
        """Test RespondToUser signature."""
        sig = RespondToUser()

        assert sig.category == "conversation"

        input_names = [f.name for f in sig.get_input_fields()]
        assert "user_message" in input_names
        assert "conversation_history" in input_names
        assert "persona" in input_names
        assert "context" in input_names

        output_names = [f.name for f in sig.get_output_fields()]
        assert "response" in output_names
        assert "intent_detected" in output_names

    def test_clarify_intent_signature(self):
        """Test ClarifyIntent signature."""
        sig = ClarifyIntent()

        input_names = [f.name for f in sig.get_input_fields()]
        assert "user_message" in input_names
        assert "possible_intents" in input_names
        assert "context" in input_names

        output_names = [f.name for f in sig.get_output_fields()]
        assert "clarification_question" in output_names
        assert "intent_hypothesis" in output_names

    def test_generate_follow_up_signature(self):
        """Test GenerateFollowUp signature."""
        sig = GenerateFollowUp()

        input_names = [f.name for f in sig.get_input_fields()]
        assert "conversation" in input_names
        assert "topic" in input_names
        assert "goal" in input_names

        output_names = [f.name for f in sig.get_output_fields()]
        assert "follow_up_questions" in output_names
        assert "rationale" in output_names

    def test_resolve_query_signature(self):
        """Test ResolveQuery signature."""
        sig = ResolveQuery()

        input_names = [f.name for f in sig.get_input_fields()]
        assert "query" in input_names
        assert "knowledge_base" in input_names
        assert "constraints" in input_names

        output_names = [f.name for f in sig.get_output_fields()]
        assert "answer" in output_names
        assert "sources" in output_names
        assert "confidence" in output_names


class TestTaskSpecificSignatures:
    """Test cases for task-specific signatures."""

    def test_email_draft_signature(self):
        """Test EmailDraft signature."""
        sig = EmailDraft()

        assert sig.category == "task_specific"

        input_names = [f.name for f in sig.get_input_fields()]
        assert "recipient" in input_names
        assert "subject" in input_names
        assert "purpose" in input_names
        assert "key_points" in input_names
        assert "tone" in input_names

        output_names = [f.name for f in sig.get_output_fields()]
        assert "email_body" in output_names
        assert "suggested_subject" in output_names

        # Test email generation
        inputs = {
            "recipient": "client@company.com",
            "subject": "Project Update",
            "purpose": "inform about milestone completion",
            "key_points": ["Milestone 1 complete", "On schedule"],
            "tone": "professional"
        }
        assert sig.validate_inputs(inputs) == True

    def test_code_generation_signature(self):
        """Test CodeGeneration signature."""
        sig = CodeGeneration()

        input_names = [f.name for f in sig.get_input_fields()]
        assert "description" in input_names
        assert "language" in input_names
        assert "framework" in input_names
        assert "requirements" in input_names
        assert "style_guide" in input_names

        output_names = [f.name for f in sig.get_output_fields()]
        assert "code" in output_names
        assert "explanation" in output_names
        assert "dependencies" in output_names

    def test_data_analysis_signature(self):
        """Test DataAnalysis signature."""
        sig = DataAnalysis()

        input_names = [f.name for f in sig.get_input_fields()]
        assert "data_description" in input_names
        assert "analysis_goals" in input_names
        assert "metrics" in input_names
        assert "constraints" in input_names

        output_names = [f.name for f in sig.get_output_fields()]
        assert "analysis" in output_names
        assert "insights" in output_names
        assert "recommendations" in output_names
        assert "visualizations" in output_names

    def test_report_generation_signature(self):
        """Test ReportGeneration signature."""
        sig = ReportGeneration()

        input_names = [f.name for f in sig.get_input_fields()]
        assert "data" in input_names
        assert "report_type" in input_names
        assert "sections" in input_names
        assert "audience" in input_names
        assert "format" in input_names

        output_names = [f.name for f in sig.get_output_fields()]
        assert "report" in output_names
        assert "executive_summary" in output_names
        assert "table_of_contents" in output_names


class TestSignatureExamples:
    """Test signature examples."""

    def test_email_draft_examples(self):
        """Test EmailDraft includes examples."""
        sig = EmailDraft()
        examples = sig.get_examples()

        assert len(examples) > 0
        assert all("recipient" in ex for ex in examples)
        assert all("email_body" in ex for ex in examples)

    def test_code_generation_examples(self):
        """Test CodeGeneration includes examples."""
        sig = CodeGeneration()
        examples = sig.get_examples()

        assert len(examples) > 0
        assert all("description" in ex for ex in examples)
        assert all("code" in ex for ex in examples)

    def test_summarize_text_examples(self):
        """Test SummarizeText includes examples."""
        sig = SummarizeText()
        examples = sig.get_examples()

        assert len(examples) > 0
        assert all("text" in ex for ex in examples)
        assert all("summary" in ex for ex in examples)
