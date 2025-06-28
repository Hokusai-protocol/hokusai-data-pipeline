"""Text generation signatures for DSPy."""

from typing import List, Dict, Any, Optional

from .base import BaseSignature, SignatureField


class DraftText(BaseSignature):
    """Generate an initial draft of text based on topic and purpose."""
    
    category = "text_generation"
    tags = ["writing", "generation", "draft"]
    version = "1.0.0"
    
    @classmethod
    def get_input_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="topic",
                description="The main topic or subject to write about",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="purpose",
                description="The purpose or goal of the text (e.g., inform, persuade, entertain)",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="style",
                description="Writing style (e.g., formal, casual, academic, creative)",
                type_hint=str,
                required=False,
                default="informative"
            ),
            SignatureField(
                name="target_length",
                description="Target length in words",
                type_hint=int,
                required=False,
                default=None
            ),
            SignatureField(
                name="audience",
                description="Target audience for the text",
                type_hint=str,
                required=False,
                default="general"
            )
        ]
    
    @classmethod
    def get_output_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="draft",
                description="The generated text draft",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="outline",
                description="Brief outline of the draft structure",
                type_hint=str,
                required=False
            )
        ]
    
    @classmethod
    def get_examples(cls) -> List[Dict[str, Any]]:
        return [
            {
                "topic": "Climate change impacts",
                "purpose": "inform",
                "style": "academic",
                "draft": "Climate change represents one of the most pressing challenges...",
                "outline": "1. Introduction\n2. Current impacts\n3. Future projections\n4. Conclusion"
            },
            {
                "topic": "New product launch",
                "purpose": "marketing",
                "style": "persuasive",
                "audience": "potential customers",
                "draft": "Introducing our revolutionary new product that will transform..."
            }
        ]


class ReviseText(BaseSignature):
    """Revise and improve existing text based on feedback."""
    
    category = "text_generation"
    tags = ["writing", "revision", "editing"]
    version = "1.0.0"
    
    @classmethod
    def get_input_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="original_text",
                description="The original text to revise",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="feedback",
                description="Specific feedback or critique to address",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="revision_goals",
                description="List of revision goals (e.g., clarity, conciseness, tone)",
                type_hint=list,
                required=False,
                default=[]
            ),
            SignatureField(
                name="preserve_style",
                description="Whether to preserve the original writing style",
                type_hint=bool,
                required=False,
                default=True
            )
        ]
    
    @classmethod
    def get_output_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="revised_text",
                description="The revised and improved text",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="changes_made",
                description="Summary of changes made during revision",
                type_hint=list,
                required=True
            ),
            SignatureField(
                name="revision_notes",
                description="Additional notes about the revision process",
                type_hint=str,
                required=False
            )
        ]
    
    @classmethod
    def get_examples(cls) -> List[Dict[str, Any]]:
        return [
            {
                "original_text": "The project was completed by the team.",
                "feedback": "Too passive, lacks detail",
                "revision_goals": ["active voice", "add specifics"],
                "revised_text": "Our engineering team successfully completed the mobile app project.",
                "changes_made": ["Changed to active voice", "Added specific details"]
            }
        ]


class ExpandText(BaseSignature):
    """Expand text by adding more detail, examples, or elaboration."""
    
    category = "text_generation"
    tags = ["writing", "expansion", "elaboration"]
    version = "1.0.0"
    
    @classmethod
    def get_input_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="text",
                description="The text to expand",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="expansion_points",
                description="Specific points or sections to expand",
                type_hint=list,
                required=True
            ),
            SignatureField(
                name="target_length",
                description="Target length after expansion (in words)",
                type_hint=int,
                required=False,
                default=None
            ),
            SignatureField(
                name="expansion_type",
                description="Type of expansion (examples, details, context, all)",
                type_hint=str,
                required=False,
                default="all"
            )
        ]
    
    @classmethod
    def get_output_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="expanded_text",
                description="The expanded version of the text",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="additions_summary",
                description="Summary of what was added",
                type_hint=list,
                required=False
            )
        ]
    
    @classmethod
    def get_examples(cls) -> List[Dict[str, Any]]:
        return [
            {
                "text": "Machine learning can help businesses.",
                "expansion_points": ["specific examples", "benefits"],
                "expansion_type": "examples",
                "expanded_text": "Machine learning can help businesses in numerous ways. For instance, retail companies use ML for demand forecasting, reducing inventory costs by up to 20%. Financial institutions employ ML algorithms for fraud detection, catching suspicious transactions in real-time.",
                "additions_summary": ["Added retail example", "Added financial services example", "Included specific metrics"]
            }
        ]


class RefineText(BaseSignature):
    """Refine text for clarity, conciseness, and polish."""
    
    category = "text_generation"
    tags = ["writing", "refinement", "polish"]
    version = "1.0.0"
    
    @classmethod
    def get_input_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="text",
                description="The text to refine",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="refinement_criteria",
                description="Criteria for refinement (clarity, conciseness, flow, grammar)",
                type_hint=list,
                required=True
            ),
            SignatureField(
                name="maintain_length",
                description="Whether to maintain approximately the same length",
                type_hint=bool,
                required=False,
                default=False
            ),
            SignatureField(
                name="formality_level",
                description="Target formality level (very_formal, formal, neutral, casual)",
                type_hint=str,
                required=False,
                default="neutral"
            )
        ]
    
    @classmethod
    def get_output_fields(cls) -> List[SignatureField]:
        return [
            SignatureField(
                name="refined_text",
                description="The refined version of the text",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="refinement_summary",
                description="Summary of refinements made",
                type_hint=str,
                required=True
            ),
            SignatureField(
                name="readability_score",
                description="Estimated readability improvement",
                type_hint=str,
                required=False
            )
        ]
    
    @classmethod
    def get_examples(cls) -> List[Dict[str, Any]]:
        return [
            {
                "text": "Due to the fact that the weather was bad, the event that was planned got cancelled by the organizers.",
                "refinement_criteria": ["conciseness", "clarity"],
                "refined_text": "The organizers cancelled the event due to bad weather.",
                "refinement_summary": "Removed redundant phrases, simplified sentence structure, reduced from 19 to 9 words"
            }
        ]