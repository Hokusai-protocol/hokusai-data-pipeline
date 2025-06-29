---
id: dspy-integration
title: DSPy Integration
sidebar_label: DSPy Integration
sidebar_position: 3
---

# DSPy Integration

Hokusai integrates DSPy for advanced prompt optimization and signature-based programming, enabling systematic improvement of language model outputs.

## What is DSPy?

DSPy (Declarative Self-improving Language Programs) is a framework for:
- **Prompt Optimization**: Automatically improve prompts based on examples
- **Signature Programming**: Define input/output specifications
- **Modular Composition**: Build complex LM programs from simple components
- **Automatic Compilation**: Optimize entire programs, not just prompts

## Core Concepts

### Signatures

Signatures define the input/output behavior of LM programs:

```python
from hokusai.dspy_signatures import BaseSignature, SignatureField

class SummarizeEmail(BaseSignature):
    """Summarize an email into key points."""
    
    email_content = SignatureField(
        description="The full email content to summarize"
    )
    
    summary = SignatureField(
        description="A concise summary with key points",
        prefix="Summary:"
    )
```

### Pre-built Signatures

Hokusai includes a library of common signatures:

```python
from hokusai.dspy_signatures import (
    # Text Generation
    DraftText,
    ReviseText,
    ExpandText,
    RefineText,
    
    # Analysis
    CritiqueText,
    SummarizeText,
    ExtractInfo,
    ClassifyText,
    
    # Conversation
    RespondToUser,
    ClarifyIntent,
    GenerateFollowUp,
    ResolveQuery,
    
    # Task-Specific
    EmailDraft,
    CodeGeneration,
    DataAnalysis,
    ReportGeneration
)
```

## Basic Usage

### Using Pre-built Signatures

```python
from hokusai.services.dspy_pipeline_executor import DSPyPipelineExecutor

# Initialize executor
executor = DSPyPipelineExecutor()

# Generate an email draft
result = executor.execute_signature(
    signature_name="EmailDraft",
    inputs={
        "recipient": "John Smith",
        "subject": "Project Update",
        "key_points": "Milestone completed, Next steps, Budget update"
    }
)

print(result["email_body"])
```

### Creating Custom Signatures

```python
from hokusai.dspy_signatures import BaseSignature, SignatureField

class ProductDescription(BaseSignature):
    """Generate compelling product descriptions."""
    
    product_name = SignatureField(
        description="Name of the product"
    )
    
    features = SignatureField(
        description="List of key features"
    )
    
    target_audience = SignatureField(
        description="Target customer demographic"
    )
    
    description = SignatureField(
        description="Engaging product description",
        prefix="Description:"
    )

# Register and use
executor.register_signature("ProductDescription", ProductDescription)

result = executor.execute_signature(
    signature_name="ProductDescription",
    inputs={
        "product_name": "SmartWatch Pro",
        "features": "Heart rate monitor, GPS, 7-day battery",
        "target_audience": "Fitness enthusiasts"
    }
)
```

## Pipeline Executor

### Configuration

```python
from hokusai.services.dspy_pipeline_executor import (
    DSPyPipelineExecutor,
    ExecutionMode
)

# Configure executor
executor = DSPyPipelineExecutor(
    cache_enabled=True,  # Cache results
    mlflow_tracking=True,  # Track with MLflow
    timeout=30,  # Timeout in seconds
    max_workers=4  # Parallel execution
)

# Set execution mode
executor.set_mode(ExecutionMode.PRODUCTION)  # or DEVELOPMENT, TESTING
```

### Batch Processing

```python
# Process multiple inputs
inputs_batch = [
    {
        "recipient": "Alice",
        "subject": "Welcome",
        "key_points": "Account created, Next steps"
    },
    {
        "recipient": "Bob",
        "subject": "Update",
        "key_points": "New features, Maintenance"
    }
]

results = executor.execute_batch(
    signature_name="EmailDraft",
    inputs_list=inputs_batch,
    parallel=True
)

for i, result in enumerate(results):
    print(f"Email {i+1}: {result['email_body'][:100]}...")
```

## Teleprompt Fine-tuning

### Automatic Optimization

Use Teleprompt to optimize signatures based on examples:

```python
from hokusai.services.teleprompt_finetuner import TelepromptFineTuner

# Initialize fine-tuner
finetuner = TelepromptFineTuner()

# Prepare training examples
examples = [
    {
        "inputs": {
            "email_content": "Long email about project delays..."
        },
        "outputs": {
            "summary": "Project delayed by 2 weeks due to dependencies"
        }
    },
    # More examples...
]

# Fine-tune signature
optimized_signature = finetuner.compile(
    signature=SummarizeEmail,
    examples=examples,
    metric="accuracy"
)

# Use optimized version
executor.register_signature(
    "OptimizedSummarizer",
    optimized_signature
)
```

### Feedback-based Improvement

```python
from hokusai.services.teleprompt_finetuner import FeedbackCollector

collector = FeedbackCollector()

# Execute and collect feedback
result = executor.execute_signature(
    signature_name="EmailDraft",
    inputs=inputs,
    collect_feedback=True
)

# User provides feedback
collector.add_feedback(
    execution_id=result["execution_id"],
    rating=4,  # 1-5 scale
    corrections={
        "email_body": "Improved version of the email..."
    }
)

# Periodically retrain with feedback
if collector.feedback_count() >= 100:
    finetuner.compile_from_feedback(
        signature_name="EmailDraft",
        feedback=collector.get_feedback()
    )
```

## Signature Library

### Text Generation Signatures

```python
# Draft new text
result = executor.execute_signature(
    "DraftText",
    inputs={
        "topic": "Climate change solutions",
        "tone": "informative",
        "length": "500 words"
    }
)

# Revise existing text
result = executor.execute_signature(
    "ReviseText",
    inputs={
        "original_text": "First draft...",
        "revision_goals": "Improve clarity, Add examples"
    }
)

# Expand on ideas
result = executor.execute_signature(
    "ExpandText",
    inputs={
        "core_idea": "Renewable energy is important",
        "aspects_to_expand": "Economic benefits, Environmental impact"
    }
)
```

### Analysis Signatures

```python
# Critique text
critique = executor.execute_signature(
    "CritiqueText",
    inputs={
        "text": "Article draft...",
        "criteria": "Clarity, Accuracy, Engagement"
    }
)

# Extract information
info = executor.execute_signature(
    "ExtractInfo",
    inputs={
        "document": "Company report...",
        "info_types": "Revenue figures, Key personnel, Deadlines"
    }
)

# Classify text
classification = executor.execute_signature(
    "ClassifyText",
    inputs={
        "text": "Customer feedback...",
        "categories": "Positive, Negative, Neutral, Feature Request"
    }
)
```

### Conversation Signatures

```python
# Respond to user query
response = executor.execute_signature(
    "RespondToUser",
    inputs={
        "user_query": "How do I reset my password?",
        "context": "Customer support chatbot",
        "tone": "helpful and friendly"
    }
)

# Clarify ambiguous intent
clarification = executor.execute_signature(
    "ClarifyIntent",
    inputs={
        "user_input": "I need help with the thing",
        "possible_intents": "Technical support, Sales, Account management"
    }
)
```

## Integration with MLflow

### Automatic Tracking

```python
import mlflow
from hokusai.integrations.mlflow_dspy import autolog

# Enable DSPy autologging
autolog()

# All executions are now tracked
with mlflow.start_run():
    result = executor.execute_signature(
        "EmailDraft",
        inputs=inputs
    )
    
    # Automatically logs:
    # - Input parameters
    # - Output text
    # - Execution time
    # - Token usage
    # - Model version
```

### Custom Metrics

```python
# Log custom metrics
with mlflow.start_run():
    result = executor.execute_signature(
        "SummarizeText",
        inputs={"document": long_document}
    )
    
    # Log quality metrics
    mlflow.log_metric("summary_length", len(result["summary"]))
    mlflow.log_metric("compression_ratio", 
        len(result["summary"]) / len(long_document))
    
    # Log as artifact
    mlflow.log_text(result["summary"], "summary.txt")
```

## Advanced Features

### Chaining Signatures

Build complex pipelines by chaining signatures:

```python
from hokusai.services.dspy_pipeline_executor import SignatureChain

# Create a chain
chain = SignatureChain()

chain.add("ExtractInfo", {
    "document": "input_document",
    "info_types": "Key facts and figures"
})

chain.add("SummarizeText", {
    "document": "ExtractInfo.extracted_info",  # Use previous output
    "max_length": "100 words"
})

chain.add("EmailDraft", {
    "recipient": "stakeholders",
    "subject": "Weekly Summary",
    "key_points": "SummarizeText.summary"
})

# Execute chain
result = executor.execute_chain(
    chain,
    initial_inputs={"input_document": report_text}
)
```

### Conditional Execution

```python
from hokusai.services.dspy_pipeline_executor import ConditionalPipeline

pipeline = ConditionalPipeline()

# Define conditions
pipeline.add_condition(
    name="needs_clarification",
    condition=lambda x: x["confidence"] < 0.8
)

# Define branches
pipeline.when("needs_clarification").execute("ClarifyIntent")
pipeline.otherwise().execute("RespondToUser")

# Execute with conditions
result = executor.execute_conditional(
    pipeline,
    inputs={
        "user_query": "Help with thing",
        "confidence": 0.6
    }
)
```

### Parallel Signatures

Execute multiple signatures in parallel:

```python
from hokusai.services.dspy_pipeline_executor import ParallelExecutor

parallel = ParallelExecutor()

# Define parallel tasks
tasks = [
    ("SummarizeText", {"document": document}),
    ("ExtractInfo", {"document": document, "info_types": "dates"}),
    ("ClassifyText", {"text": document, "categories": "Technical, Business"})
]

# Execute in parallel
results = parallel.execute_all(tasks)

summary = results[0]["summary"]
dates = results[1]["extracted_info"]
category = results[2]["classification"]
```

## Best Practices

### 1. Signature Design

Keep signatures focused and modular:

```python
# Good: Single responsibility
class ExtractDates(BaseSignature):
    """Extract all dates from text."""
    text = SignatureField()
    dates = SignatureField(description="List of dates found")

# Avoid: Multiple responsibilities
class AnalyzeEverything(BaseSignature):
    """Extract dates, summarize, and classify."""
    # Too broad!
```

### 2. Input Validation

Always validate inputs:

```python
from hokusai.services.dspy.validators import SignatureValidator

validator = SignatureValidator()

# Validate before execution
if validator.validate_inputs("EmailDraft", inputs):
    result = executor.execute_signature("EmailDraft", inputs)
else:
    errors = validator.get_errors()
    print(f"Invalid inputs: {errors}")
```

### 3. Error Handling

Handle failures gracefully:

```python
try:
    result = executor.execute_signature(
        "ComplexAnalysis",
        inputs=data,
        retry_on_failure=True,
        max_retries=3
    )
except TimeoutError:
    # Fallback to simpler signature
    result = executor.execute_signature("SimpleAnalysis", inputs=data)
except Exception as e:
    logger.error(f"DSPy execution failed: {e}")
    result = {"error": str(e)}
```

### 4. Performance Optimization

Use caching and batching:

```python
# Enable caching for repeated calls
executor = DSPyPipelineExecutor(
    cache_enabled=True,
    cache_ttl=3600  # 1 hour
)

# Batch similar requests
results = executor.execute_batch(
    signature_name="ClassifyText",
    inputs_list=documents,
    batch_size=10,
    parallel=True
)
```

## Troubleshooting

### Common Issues

**"Signature not found"**
```python
# List available signatures
available = executor.list_signatures()
print(f"Available signatures: {available}")

# Register missing signature
executor.register_signature("MySignature", MySignatureClass)
```

**"Timeout during execution"**
```python
# Increase timeout
executor = DSPyPipelineExecutor(timeout=60)

# Or use async execution
result_future = executor.execute_async(
    "LongRunningTask",
    inputs=data
)
result = result_future.result(timeout=120)
```

**"Poor quality outputs"**
```python
# Collect examples and retrain
examples = collect_good_examples()
optimized = finetuner.compile(
    signature=YourSignature,
    examples=examples,
    metric="quality_score"
)
```

## Related Topics

- [Teleprompt Fine-tuning](../guides/teleprompt-finetuning.md) - Advanced optimization
- [Signature Development](../guides/signature-development.md) - Creating custom signatures
- [MLflow Integration](./mlflow-integration.md) - Tracking DSPy experiments