# DSPy Signature CLI Tools

The Hokusai platform includes comprehensive CLI tools for managing DSPy signatures.

## Installation

The CLI tools are automatically available when you install the Hokusai data pipeline. Make sure to set your PYTHONPATH:

```bash
export PYTHONPATH=.
```

## Usage

Access signature management commands through the main Hokusai CLI:

```bash
python cli/src/cli.py signatures <command>
```

## Available Commands

### List Signatures

List all available signatures in the library:

```bash
# List all signatures
python cli/src/cli.py signatures list

# Filter by category
python cli/src/cli.py signatures list --category text_generation

# Filter by tags
python cli/src/cli.py signatures list --tags writing,generation

# Output as JSON
python cli/src/cli.py signatures list --format json
```

### Show Signature Details

View detailed information about a specific signature:

```bash
python cli/src/cli.py signatures show EmailDraft
```

This displays:
- Full description
- Input/output fields with types
- Default values
- Usage examples

### Test a Signature

Test a signature with sample inputs:

```bash
python cli/src/cli.py signatures test DraftText \
  --inputs '{"topic": "climate change", "requirements": "500 words"}'
```

### Export Signatures

Export signature configurations:

```bash
# Export single signature
python cli/src/cli.py signatures export EmailDraft --format yaml

# Export entire catalog
python cli/src/cli.py signatures export-catalog --format json
```

### Create New Signatures

Generate a scaffold for a new signature:

```bash
python cli/src/cli.py signatures create MyNewSignature \
  --category task_specific \
  --description "My custom signature"
```

### Manage Aliases

Create aliases for commonly used signatures:

```bash
python cli/src/cli.py signatures alias QuickEmail EmailDraft
```

## Integration with DSPy Programs

The signatures discovered through the CLI can be used directly in your DSPy programs:

```python
from src.dspy_signatures import get_global_registry

# Get the registry
registry = get_global_registry()

# Load a signature by name
email_sig = registry.get("EmailDraft")

# Use in a DSPy program
class EmailAssistant(dspy.Module):
    def __init__(self):
        super().__init__()
        self.email_generator = dspy.Predict(email_sig)
    
    def forward(self, recipient, subject, key_points):
        return self.email_generator(
            recipient=recipient,
            subject=subject,
            purpose="inform",
            key_points=key_points
        )
```

## Examples

### Finding Signatures for Email Tasks

```bash
# Search for email-related signatures
python cli/src/cli.py signatures list --tags email

# Get details on EmailDraft
python cli/src/cli.py signatures show EmailDraft

# Test with sample data
python cli/src/cli.py signatures test EmailDraft \
  --inputs '{
    "recipient": "team@company.com",
    "subject": "Weekly Update",
    "purpose": "inform",
    "key_points": ["Project on track", "Budget approved"]
  }'
```

### Exporting for Documentation

```bash
# Export all signatures to a YAML file
python cli/src/cli.py signatures export-catalog --format yaml > signatures.yaml

# Export specific signature for sharing
python cli/src/cli.py signatures export DraftText --format json > draft_text_signature.json
```

## Tips

1. **Use tab completion**: The CLI supports tab completion for signature names
2. **Filter effectively**: Combine category and tag filters to find relevant signatures
3. **Test before use**: Always test signatures with your specific inputs before integration
4. **Export for sharing**: Use export commands to share signature configurations with team members