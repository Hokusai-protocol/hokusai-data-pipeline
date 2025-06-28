# DSPy Signature Library

The DSPy Signature Library provides a comprehensive collection of reusable prompt signatures for the Hokusai ML platform. It standardizes common prompt patterns, improves consistency across models, and accelerates development of new DSPy programs.

## Overview

The signature library includes:
- **20+ Pre-built Signatures**: Common patterns for text generation, analysis, conversation, and task-specific operations
- **Signature Registry**: Centralized management of all available signatures
- **Aliasing System**: Create shortcuts for frequently used signatures
- **Customization Support**: Extend and modify signatures for specific use cases
- **Type Safety**: Built-in validation for inputs and outputs
- **Integration**: Seamless integration with DSPy Model Loader and Pipeline Executor

## Architecture

```
┌─────────────────────────┐
│   Signature Registry    │
│  - Global singleton     │
│  - Thread-safe access   │
└───────────┬─────────────┘
            │
  ┌─────────┴──────────┐
  │                    │
┌─▼────────────┐  ┌───▼──────────┐
│Base Signature│  │Signature     │
│Classes       │  │Categories    │
│              │  │- Text Gen    │
│- Validation  │  │- Analysis    │
│- Type hints  │  │- Conversation│
│- Examples    │  │- Task-Specific│
└──────────────┘  └──────────────┘
```

## Installation

The signature library is included with the Hokusai ML Platform:

```bash
pip install git+https://github.com/Hokusai-protocol/hokusai-data-pipeline.git#subdirectory=hokusai-ml-platform
```

## Quick Start

### Using Pre-built Signatures

```python
from src.dspy_signatures import get_global_registry, EmailDraft

# Method 1: Direct import
email_sig = EmailDraft()

# Method 2: Load from registry
registry = get_global_registry()
email_sig = registry.get("EmailDraft")

# Method 3: Use alias
email_sig = registry.get("Email")  # "Email" is an alias for "EmailDraft"
```

### Executing with Signatures

```python
from src.services.dspy_pipeline_executor import DSPyPipelineExecutor

executor = DSPyPipelineExecutor()

# Execute with signature
result = executor.execute(
    program=email_sig,
    inputs={
        "recipient": "john@example.com",
        "subject": "Project Update",
        "purpose": "inform about progress",
        "key_points": ["Milestone completed", "On schedule"],
        "tone": "professional"
    }
)

print(result.outputs["email_body"])
```

## Available Signatures

### Text Generation

#### DraftText
Generate initial text drafts based on topic and purpose.

**Inputs:**
- `topic` (str, required): Main topic to write about
- `purpose` (str, required): Purpose of the text
- `style` (str, optional): Writing style
- `target_length` (int, optional): Target word count
- `audience` (str, optional): Target audience

**Outputs:**
- `draft` (str): Generated text draft
- `outline` (str, optional): Brief outline

#### ReviseText
Revise and improve existing text based on feedback.

**Inputs:**
- `original_text` (str, required): Text to revise
- `feedback` (str, required): Specific feedback
- `revision_goals` (list, optional): Goals for revision
- `preserve_style` (bool, optional): Keep original style

**Outputs:**
- `revised_text` (str): Improved text
- `changes_made` (list): Summary of changes

#### ExpandText
Expand text with more detail and examples.

**Inputs:**
- `text` (str, required): Text to expand
- `expansion_points` (list, required): Areas to expand
- `target_length` (int, optional): Target length
- `expansion_type` (str, optional): Type of expansion

**Outputs:**
- `expanded_text` (str): Expanded version
- `additions_summary` (list, optional): What was added

#### RefineText
Polish text for clarity and conciseness.

**Inputs:**
- `text` (str, required): Text to refine
- `refinement_criteria` (list, required): Refinement goals
- `maintain_length` (bool, optional): Keep same length
- `formality_level` (str, optional): Target formality

**Outputs:**
- `refined_text` (str): Polished text
- `refinement_summary` (str): Changes made

### Analysis

#### CritiqueText
Provide constructive critique and analysis.

**Inputs:**
- `text` (str, required): Text to critique
- `criteria` (list, required): Evaluation criteria
- `perspective` (str, optional): Critique perspective
- `severity` (str, optional): Critique level

**Outputs:**
- `critique` (str): Overall analysis
- `strengths` (list): Identified strengths
- `weaknesses` (list): Areas for improvement
- `suggestions` (list): Specific recommendations

#### SummarizeText
Generate concise summaries.

**Inputs:**
- `text` (str, required): Text to summarize
- `max_length` (int, optional): Maximum words
- `style` (str, optional): Summary style
- `focus_areas` (list, optional): Areas to focus on

**Outputs:**
- `summary` (str): Generated summary
- `key_points` (list): Main points

#### ExtractInfo
Extract specific information from text.

**Inputs:**
- `text` (str, required): Source text
- `info_types` (list, required): Information to extract
- `format` (str, optional): Output format
- `context_window` (bool, optional): Include context

**Outputs:**
- `extracted_info` (dict): Extracted data
- `confidence_scores` (dict, optional): Extraction confidence

#### ClassifyText
Classify text into categories.

**Inputs:**
- `text` (str, required): Text to classify
- `categories` (list, required): Possible categories
- `multi_label` (bool, optional): Allow multiple categories
- `threshold` (float, optional): Confidence threshold

**Outputs:**
- `classification` (str/list): Assigned categories
- `confidence` (dict): Confidence scores
- `reasoning` (str): Classification rationale

### Conversation

#### RespondToUser
Generate appropriate conversation responses.

**Inputs:**
- `user_message` (str, required): User's message
- `conversation_history` (list, optional): Previous messages
- `persona` (str, optional): Assistant persona
- `context` (dict, optional): Additional context
- `tone` (str, optional): Response tone

**Outputs:**
- `response` (str): Generated response
- `intent_detected` (str, optional): User intent
- `follow_up_needed` (bool, optional): Follow-up flag

#### ClarifyIntent
Generate clarifying questions.

**Inputs:**
- `user_message` (str, required): Ambiguous message
- `possible_intents` (list, required): Possible meanings
- `context` (dict, optional): Context
- `max_options` (int, optional): Options to present

**Outputs:**
- `clarification_question` (str): Clarifying question
- `intent_hypothesis` (str): Best guess
- `options_provided` (list, optional): Presented options

#### GenerateFollowUp
Create relevant follow-up questions.

**Inputs:**
- `conversation` (dict, required): Recent exchange
- `topic` (str, required): Main topic
- `goal` (str, optional): Follow-up goal
- `num_questions` (int, optional): Questions to generate

**Outputs:**
- `follow_up_questions` (list): Generated questions
- `rationale` (str): Reasoning
- `question_types` (list, optional): Question categories

#### ResolveQuery
Provide comprehensive query answers.

**Inputs:**
- `query` (str, required): User query
- `knowledge_base` (dict, optional): Available knowledge
- `constraints` (dict, optional): Answer constraints
- `answer_format` (str, optional): Preferred format

**Outputs:**
- `answer` (str): Complete answer
- `sources` (list, optional): References used
- `confidence` (float): Answer confidence
- `caveats` (list, optional): Limitations

### Task-Specific

#### EmailDraft
Generate professional email drafts.

**Inputs:**
- `recipient` (str, required): Recipient info
- `subject` (str, required): Email subject
- `purpose` (str, required): Email purpose
- `key_points` (list, required): Main points
- `tone` (str, optional): Email tone
- `sender_name` (str, optional): Sender name
- `attachments_mentioned` (list, optional): Attachments

**Outputs:**
- `email_body` (str): Complete email
- `suggested_subject` (str, optional): Alternative subject
- `call_to_action` (str, optional): Identified CTA

#### CodeGeneration
Generate code based on requirements.

**Inputs:**
- `description` (str, required): What code should do
- `language` (str, required): Programming language
- `framework` (str, optional): Framework to use
- `requirements` (list, optional): Specific requirements
- `style_guide` (str, optional): Coding style
- `include_tests` (bool, optional): Include unit tests

**Outputs:**
- `code` (str): Generated code
- `explanation` (str): Code explanation
- `dependencies` (list, optional): Required imports
- `usage_example` (str, optional): How to use

#### DataAnalysis
Generate data analysis insights.

**Inputs:**
- `data_description` (str, required): Data description
- `analysis_goals` (list, required): Analysis objectives
- `metrics` (list, optional): Key metrics
- `constraints` (dict, optional): Limitations
- `audience` (str, optional): Target audience

**Outputs:**
- `analysis` (str): Detailed findings
- `insights` (list): Key insights
- `recommendations` (list): Action items
- `visualizations` (list, optional): Suggested charts

#### ReportGeneration
Create structured reports.

**Inputs:**
- `data` (dict, required): Report data
- `report_type` (str, required): Type of report
- `sections` (list, required): Required sections
- `audience` (str, optional): Target readers
- `format` (str, optional): Output format
- `length_limit` (int, optional): Max words

**Outputs:**
- `report` (str): Complete report
- `executive_summary` (str): Summary
- `table_of_contents` (list, optional): Sections
- `key_findings` (list, optional): Highlights

## Advanced Usage

### Creating Custom Signatures

```python
from src.dspy_signatures.base import BaseSignature, SignatureField
from src.dspy_signatures.metadata import SignatureMetadata

class ProductDescription(BaseSignature):
    """Generate compelling product descriptions."""
    
    category = "task_specific"
    tags = ["ecommerce", "marketing", "writing"]
    
    @classmethod
    def get_input_fields(cls):
        return [
            SignatureField("product_name", "Product name", str, True),
            SignatureField("features", "Product features", list, True),
            SignatureField("target_market", "Target audience", str, True),
            SignatureField("tone", "Description tone", str, False, "enthusiastic")
        ]
    
    @classmethod
    def get_output_fields(cls):
        return [
            SignatureField("description", "Product description", str, True),
            SignatureField("tagline", "Product tagline", str, True)
        ]

# Register the custom signature
registry = get_global_registry()
sig = ProductDescription()
metadata = SignatureMetadata(
    name="ProductDescription",
    description="Generate product descriptions",
    category="task_specific",
    tags=["ecommerce", "marketing"]
)
registry.register(sig, metadata)
```

### Composing Signatures

```python
from src.dspy_signatures.base import SignatureComposer

composer = SignatureComposer()

# Chain signatures together
email_workflow = composer.compose(
    DraftText,  # First draft the content
    ReviseText  # Then revise it
)

# Merge signatures for parallel execution
analysis_suite = composer.merge(
    SummarizeText,  # Summarize
    ExtractInfo     # And extract info simultaneously
)
```

### Using Aliases

```python
registry = get_global_registry()

# Create custom aliases
registry.create_alias("QuickEmail", "EmailDraft")
registry.create_alias("Summarizer", "SummarizeText")

# Use aliases
email_sig = registry.get("QuickEmail")
```

### Searching Signatures

```python
# Find by category
text_sigs = registry.search(category="text_generation")

# Find by tags
email_sigs = registry.search(tags=["email"])

# Find by multiple tags (AND operation)
pro_email_sigs = registry.search(tags=["email", "professional"])
```

## Integration with DSPy Programs

### Using Library Signatures in YAML Config

```yaml
name: customer-support-bot
version: 1.0.0

signatures:
  understand:
    library: ClarifyIntent
    
  draft_response:
    library: RespondToUser
    overrides:
      persona: "helpful support agent"
      tone: "friendly"
      
  follow_up:
    library: GenerateFollowUp

modules:
  - name: support_chain
    type: ChainOfThought
    signatures: [understand, draft_response, follow_up]
```

### Loading with DSPy Model Loader

```python
from src.services.dspy_model_loader import DSPyModelLoader

loader = DSPyModelLoader()

# List available signatures
signatures = loader.list_available_signatures(category="conversation")

# Load specific signature
email_sig = loader.load_signature_from_library("EmailDraft")

# Create program with library signatures
config = {
    "name": "email-assistant",
    "signatures": {
        "draft": {"library": "EmailDraft"},
        "polish": {"library": "RefineText"}
    }
}
program_data = loader.create_program_with_library_signatures(config)
```

## Best Practices

1. **Choose the Right Signature**: Select signatures that match your use case
2. **Validate Inputs**: Always provide required fields
3. **Use Type Hints**: Leverage type safety for better results
4. **Create Aliases**: Make shortcuts for frequently used signatures
5. **Extend Don't Replace**: Build on existing signatures when possible
6. **Document Custom Signatures**: Include examples and clear descriptions
7. **Test Thoroughly**: Validate custom signatures before production use

## Troubleshooting

### Signature Not Found

```python
try:
    sig = registry.get("NonExistent")
except KeyError:
    print("Available signatures:", registry.list_signatures())
```

### Input Validation Errors

```python
sig = EmailDraft()
try:
    sig.validate_inputs({"recipient": "test@example.com"})
except ValueError as e:
    print(f"Missing fields: {e}")
```

### Custom Signature Issues

Ensure your custom signature:
- Inherits from `BaseSignature`
- Implements `get_input_fields()` and `get_output_fields()`
- Returns `SignatureField` instances
- Has at least one input and output field

## Examples

### Complete Email Workflow

```python
from src.dspy_signatures import DraftText, ReviseText, RefineText
from src.services.dspy_pipeline_executor import DSPyPipelineExecutor

executor = DSPyPipelineExecutor()

# Step 1: Draft initial content
draft_result = executor.execute(
    program=DraftText(),
    inputs={
        "topic": "Q4 project update",
        "purpose": "inform stakeholders",
        "style": "professional"
    }
)

# Step 2: Revise based on feedback
revise_result = executor.execute(
    program=ReviseText(),
    inputs={
        "original_text": draft_result.outputs["draft"],
        "feedback": "Add specific metrics and timeline",
        "revision_goals": ["add_details", "quantify_results"]
    }
)

# Step 3: Polish final version
final_result = executor.execute(
    program=RefineText(),
    inputs={
        "text": revise_result.outputs["revised_text"],
        "refinement_criteria": ["clarity", "conciseness"],
        "formality_level": "formal"
    }
)
```

### Multi-Purpose Analysis

```python
# Analyze customer feedback
feedback = "The product quality is excellent but delivery was slow..."

# Get multiple perspectives
summary = executor.execute(
    program=SummarizeText(),
    inputs={"text": feedback, "max_length": 50}
)

sentiment = executor.execute(
    program=ClassifyText(),
    inputs={
        "text": feedback,
        "categories": ["positive", "negative", "mixed"],
        "multi_label": False
    }
)

insights = executor.execute(
    program=ExtractInfo(),
    inputs={
        "text": feedback,
        "info_types": ["product_aspects", "service_aspects"],
        "format": "structured"
    }
)
```

## CLI Tools

The signature library includes comprehensive CLI tools for management and discovery:

```bash
# List all signatures
python cli/src/cli.py signatures list

# Show signature details
python cli/src/cli.py signatures show EmailDraft

# Test a signature
python cli/src/cli.py signatures test DraftText --inputs '{"topic": "AI"}'

# Export signatures
python cli/src/cli.py signatures export-catalog --format yaml
```

See [CLI_SIGNATURES.md](CLI_SIGNATURES.md) for complete CLI documentation.

## Contributing

To contribute new signatures:

1. Create signature class inheriting from `BaseSignature`
2. Implement required methods
3. Add comprehensive examples
4. Write unit tests
5. Update documentation
6. Submit pull request

See `CONTRIBUTING.md` for detailed guidelines.