"""Analysis signatures for DSPy."""

from typing import Any

from .base import BaseSignature, SignatureField


class CritiqueText(BaseSignature):
    """Provide constructive critique and analysis of text."""

    category = "analysis"
    tags = ["analysis", "critique", "evaluation"]
    version = "1.0.0"

    @classmethod
    def get_input_fields(cls) -> list[SignatureField]:
        return [
            SignatureField(
                name="text", description="The text to critique", type_hint=str, required=True
            ),
            SignatureField(
                name="criteria",
                description="Specific criteria to evaluate (e.g., clarity, argument, evidence)",
                type_hint=list,
                required=True,
            ),
            SignatureField(
                name="perspective",
                description="Perspective to critique from (e.g., editor, peer, expert)",
                type_hint=str,
                required=False,
                default="objective reviewer",
            ),
            SignatureField(
                name="severity",
                description="Critique severity level (gentle, balanced, strict)",
                type_hint=str,
                required=False,
                default="balanced",
            ),
        ]

    @classmethod
    def get_output_fields(cls) -> list[SignatureField]:
        return [
            SignatureField(
                name="critique",
                description="Overall critique and analysis",
                type_hint=str,
                required=True,
            ),
            SignatureField(
                name="strengths",
                description="List of identified strengths",
                type_hint=list,
                required=True,
            ),
            SignatureField(
                name="weaknesses",
                description="List of identified weaknesses",
                type_hint=list,
                required=True,
            ),
            SignatureField(
                name="suggestions",
                description="Specific suggestions for improvement",
                type_hint=list,
                required=True,
            ),
            SignatureField(
                name="overall_rating",
                description="Overall quality rating or assessment",
                type_hint=str,
                required=False,
            ),
        ]

    @classmethod
    def get_examples(cls) -> list[dict[str, Any]]:
        return [
            {
                "text": "AI will replace all human jobs within 10 years.",
                "criteria": ["evidence", "reasoning", "balance"],
                "perspective": "technology expert",
                "critique": "This statement makes a sweeping generalization without supporting evidence...",
                "strengths": ["Addresses important topic", "Clear position"],
                "weaknesses": ["Lacks evidence", "Overly simplistic", "Ignores nuance"],
                "suggestions": [
                    "Add specific examples",
                    "Consider job categories separately",
                    "Include timeline evidence",
                ],
            }
        ]


class SummarizeText(BaseSignature):
    """Generate concise summaries of longer texts."""

    category = "analysis"
    tags = ["analysis", "summary", "condensation"]
    version = "1.0.0"

    @classmethod
    def get_input_fields(cls) -> list[SignatureField]:
        return [
            SignatureField(
                name="text", description="The text to summarize", type_hint=str, required=True
            ),
            SignatureField(
                name="max_length",
                description="Maximum length of summary in words",
                type_hint=int,
                required=False,
                default=100,
            ),
            SignatureField(
                name="style",
                description="Summary style (bullet_points, paragraph, abstract, executive)",
                type_hint=str,
                required=False,
                default="paragraph",
            ),
            SignatureField(
                name="focus_areas",
                description="Specific areas to focus on in the summary",
                type_hint=list,
                required=False,
                default=[],
            ),
            SignatureField(
                name="preserve_tone",
                description="Whether to preserve the original tone",
                type_hint=bool,
                required=False,
                default=True,
            ),
        ]

    @classmethod
    def get_output_fields(cls) -> list[SignatureField]:
        return [
            SignatureField(
                name="summary", description="The generated summary", type_hint=str, required=True
            ),
            SignatureField(
                name="key_points",
                description="List of key points extracted",
                type_hint=list,
                required=True,
            ),
            SignatureField(
                name="omitted_details",
                description="Important details that were omitted",
                type_hint=list,
                required=False,
            ),
        ]

    @classmethod
    def get_examples(cls) -> list[dict[str, Any]]:
        return [
            {
                "text": "The quarterly financial report shows revenue increased by 15%...",
                "max_length": 50,
                "style": "executive",
                "summary": "Q3 showed strong performance with 15% revenue growth driven by new product launches. Expenses remained controlled. Outlook positive for Q4.",
                "key_points": [
                    "15% revenue growth",
                    "Successful product launches",
                    "Controlled expenses",
                    "Positive Q4 outlook",
                ],
            }
        ]


class ExtractInfo(BaseSignature):
    """Extract specific information from text."""

    category = "analysis"
    tags = ["analysis", "extraction", "parsing"]
    version = "1.0.0"

    @classmethod
    def get_input_fields(cls) -> list[SignatureField]:
        return [
            SignatureField(
                name="text",
                description="The text to extract information from",
                type_hint=str,
                required=True,
            ),
            SignatureField(
                name="info_types",
                description="Types of information to extract (e.g., names, dates, numbers, entities)",
                type_hint=list,
                required=True,
            ),
            SignatureField(
                name="format",
                description="Output format (json, list, structured)",
                type_hint=str,
                required=False,
                default="structured",
            ),
            SignatureField(
                name="context_window",
                description="Include surrounding context for extractions",
                type_hint=bool,
                required=False,
                default=False,
            ),
        ]

    @classmethod
    def get_output_fields(cls) -> list[SignatureField]:
        return [
            SignatureField(
                name="extracted_info",
                description="The extracted information organized by type",
                type_hint=dict,
                required=True,
            ),
            SignatureField(
                name="confidence_scores",
                description="Confidence scores for each extraction",
                type_hint=dict,
                required=False,
            ),
            SignatureField(
                name="extraction_count",
                description="Count of items extracted by type",
                type_hint=dict,
                required=False,
            ),
        ]

    @classmethod
    def get_examples(cls) -> list[dict[str, Any]]:
        return [
            {
                "text": "John Smith, CEO of TechCorp, announced on March 15, 2024 that revenue reached $2.5 billion.",
                "info_types": ["names", "titles", "organizations", "dates", "money"],
                "format": "json",
                "extracted_info": {
                    "names": ["John Smith"],
                    "titles": ["CEO"],
                    "organizations": ["TechCorp"],
                    "dates": ["March 15, 2024"],
                    "money": ["$2.5 billion"],
                },
                "extraction_count": {
                    "names": 1,
                    "titles": 1,
                    "organizations": 1,
                    "dates": 1,
                    "money": 1,
                },
            }
        ]


class ClassifyText(BaseSignature):
    """Classify text into predefined categories."""

    category = "analysis"
    tags = ["analysis", "classification", "categorization"]
    version = "1.0.0"

    @classmethod
    def get_input_fields(cls) -> list[SignatureField]:
        return [
            SignatureField(
                name="text", description="The text to classify", type_hint=str, required=True
            ),
            SignatureField(
                name="categories",
                description="List of possible categories",
                type_hint=list,
                required=True,
            ),
            SignatureField(
                name="multi_label",
                description="Whether text can belong to multiple categories",
                type_hint=bool,
                required=False,
                default=False,
            ),
            SignatureField(
                name="include_confidence",
                description="Include confidence scores for each category",
                type_hint=bool,
                required=False,
                default=True,
            ),
            SignatureField(
                name="threshold",
                description="Minimum confidence threshold for classification",
                type_hint=float,
                required=False,
                default=0.5,
            ),
        ]

    @classmethod
    def get_output_fields(cls) -> list[SignatureField]:
        return [
            SignatureField(
                name="classification",
                description="The assigned category/categories",
                type_hint=str,  # or list if multi_label
                required=True,
            ),
            SignatureField(
                name="confidence",
                description="Confidence scores for the classification",
                type_hint=dict,
                required=True,
            ),
            SignatureField(
                name="reasoning",
                description="Explanation for the classification",
                type_hint=str,
                required=True,
            ),
            SignatureField(
                name="alternative_categories",
                description="Other possible categories considered",
                type_hint=list,
                required=False,
            ),
        ]

    @classmethod
    def get_examples(cls) -> list[dict[str, Any]]:
        return [
            {
                "text": "I'm very disappointed with the product quality and customer service.",
                "categories": ["positive", "negative", "neutral"],
                "multi_label": False,
                "classification": "negative",
                "confidence": {"negative": 0.95, "neutral": 0.04, "positive": 0.01},
                "reasoning": "Text expresses disappointment and dissatisfaction with multiple aspects",
            }
        ]
