# DSPy Model Loader Documentation

## Overview

The DSPy Model Loader is a comprehensive utility within the Hokusai ML Platform that enables loading, validation, and management of DSPy (Declarative Self-Prompting) programs. DSPy is a framework for programming with language models that allows developers to create sophisticated prompt-based programs with composable modules.

## Features

- **Multiple Loading Sources**: Load DSPy programs from local files, Python classes, or remote repositories (HuggingFace Hub)
- **Configuration-Based Loading**: Use YAML or JSON configuration files to define DSPy programs
- **Validation**: Comprehensive validation of DSPy program structure, signatures, and chains
- **Registry Integration**: Seamless integration with Hokusai's model registry for versioning and tracking
- **Model Abstraction**: DSPy models work with Hokusai's unified model interface for A/B testing and deployment

## Installation

The DSPy loader is included in the main Hokusai ML Platform package. To enable full functionality:

```bash
# Install with DSPy support
pip install dspy-ai>=2.0.0

# For HuggingFace Hub support
pip install huggingface-hub>=0.19.0
```

## Quick Start

### Loading from Configuration File

```python
from src.services.dspy_model_loader import DSPyModelLoader

# Initialize the loader
loader = DSPyModelLoader()

# Load from YAML configuration
program_data = loader.load_from_config("examples/dspy/basic_config.yaml")

# Register with Hokusai
model_id = loader.register_dspy_model(
    program_data,
    model_name="email-assistant",
    token_id="email-assistant-v1"
)
```

### Loading from Python Class

```python
# Load directly from a Python class
program_data = loader.load_from_class(
    module_path="examples.dspy.example_dspy_program",
    class_name="EmailAssistant"
)
```

### Loading from HuggingFace Hub

```python
# Load from HuggingFace
program_data = loader.load_from_huggingface(
    repo_id="hokusai/email-assistant",
    filename="model.pkl",
    token=os.getenv("HF_TOKEN")  # For private repos
)
```

## Configuration Schema

DSPy models can be configured using YAML files with the following structure:

```yaml
name: model-name
version: 1.0.0
description: Model description
author: Author name

# Source configuration
source:
  type: local|huggingface|github
  # Type-specific fields...

# Signature definitions
signatures:
  signature_name:
    inputs: [input1, input2]
    outputs: [output1]
    description: What this signature does
    examples:  # Optional
      - input: {input1: value1}
        output: {output1: result1}

# Chain definitions (optional)
chains:
  chain_name:
    steps: [signature1, signature2]
    description: Chain description

# Dependencies
dependencies:
  - dspy>=2.0.0
  - transformers>=4.30.0
```

## Signature Definitions

Signatures define the input/output interface for DSPy modules:

```python
class EmailSignature(dspy.Signature):
    """Signature for email generation."""
    
    recipient: str = dspy.InputField(desc="Email recipient")
    subject: str = dspy.InputField(desc="Subject line")
    context: str = dspy.InputField(desc="Email context")
    
    email_body: str = dspy.OutputField(desc="Generated email")
```

## Validation

The loader performs comprehensive validation:

1. **Configuration Validation**: Ensures all required fields are present
2. **Signature Validation**: Validates input/output specifications
3. **Chain Validation**: Ensures chain steps reference valid signatures
4. **Program Validation**: Verifies the DSPy program has required methods

```python
# Get validation report
validator = DSPyValidator()
report = validator.create_validation_report(program, config)
print(report)
```

## Integration with Model Abstraction

DSPy models are wrapped in the `DSPyHokusaiModel` class for compatibility:

```python
from src.services.model_abstraction import ModelFactory, ModelMetadata, ModelType

# Create metadata
metadata = ModelMetadata(
    model_id="email-v1",
    model_family="dspy-email",
    version="1.0.0",
    model_type=ModelType.DSPY,
    # ... other fields
)

# Create DSPy model wrapper
dspy_model = ModelFactory.create_model(
    model_type="dspy",
    model_instance=program,
    metadata=metadata
)

# Use like any other Hokusai model
predictions = dspy_model.predict(input_df)
```

## API Endpoints

The platform provides RESTful endpoints for DSPy models:

### Load DSPy Model
```
POST /api/v1/models/dspy/load
Content-Type: application/json

{
  "config_path": "/path/to/config.yaml",
  "register": true,
  "model_name": "my-dspy-model"
}
```

### Register DSPy Model
```
POST /api/v1/models/dspy/register
Content-Type: application/json

{
  "source": {
    "type": "huggingface",
    "repo_id": "user/model",
    "filename": "model.pkl"
  },
  "model_name": "imported-model",
  "token_id": "model-token-v1"
}
```

### Get DSPy Model Info
```
GET /api/v1/models/dspy/{model_id}
```

## Best Practices

1. **Version Control**: Always specify versions in configurations
2. **Validation**: Validate programs before deployment
3. **Documentation**: Document signatures with clear descriptions
4. **Testing**: Include example inputs/outputs in configurations
5. **Dependencies**: List all required dependencies explicitly

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure DSPy and dependencies are installed
2. **Validation Failures**: Check signature definitions match program
3. **Loading Errors**: Verify file paths and permissions
4. **HuggingFace Auth**: Set HF_TOKEN environment variable for private repos

### Debug Mode

Enable debug logging:

```python
import logging
logging.getLogger("src.services.dspy").setLevel(logging.DEBUG)
```

## Examples

See the `examples/dspy/` directory for:

- `basic_config.yaml`: Simple DSPy configuration
- `multi_signature_config.yaml`: Complex multi-stage pipeline
- `example_dspy_program.py`: Complete DSPy program implementation
- `huggingface_config.yaml`: Loading from HuggingFace Hub

## Advanced Features

### Custom Validators

Extend validation for specific use cases:

```python
class CustomDSPyValidator(DSPyValidator):
    def validate_custom_rules(self, program):
        # Add custom validation logic
        pass
```

### Contributor Attribution

The loader supports contributor tracking for reward distribution:

```python
program_data = loader.load_from_config("config.yaml")
program_data["metadata"]["contributor_address"] = "0x742d35Cc..."

model_id = loader.register_dspy_model(
    program_data,
    model_name="contributed-model",
    tags={"contributor": "0x742d35Cc..."}
)
```

## Future Enhancements

- GitHub repository support
- Automatic dependency installation
- DSPy program composition tools
- Visual chain builder
- Performance profiling for DSPy programs