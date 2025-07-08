"""CLI tools for DSPy Signature Library management."""

import click
import json
import yaml
import os
import sys
from typing import Optional, List

# Add parent directory to path for imports
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    from tabulate import tabulate
except ImportError:
    print("Warning: tabulate not installed, using basic formatting")
    tabulate = None

from src.dspy_signatures import get_global_registry
from src.dspy_signatures.loader import SignatureLoader
from src.services.dspy_pipeline_executor import DSPyPipelineExecutor


@click.group()
def signatures():
    """Manage DSPy signatures in the Hokusai platform."""
    pass


@signatures.command()
@click.option('--category', help='Filter by category')
@click.option('--tags', help='Filter by tags (comma-separated)')
@click.option('--format', type=click.Choice(['table', 'json', 'yaml']), default='table')
def list(category: Optional[str], tags: Optional[str], format: str):
    """List available DSPy signatures."""
    registry = get_global_registry()
    
    # Get signatures based on filters
    if category or tags:
        tag_list = tags.split(',') if tags else None
        signatures = registry.search(category=category, tags=tag_list)
    else:
        signatures = registry.list_signatures()
    
    # Get metadata for each signature
    sig_data = []
    for sig_name in signatures:
        metadata = registry.get_metadata(sig_name)
        sig_data.append({
            'name': sig_name,
            'category': metadata.category,
            'description': metadata.description[:50] + '...' if len(metadata.description) > 50 else metadata.description,
            'tags': ', '.join(metadata.tags),
            'version': metadata.version
        })
    
    # Format output
    if format == 'table':
        headers = ['Name', 'Category', 'Description', 'Tags', 'Version']
        rows = [[s['name'], s['category'], s['description'], s['tags'], s['version']] for s in sig_data]
        click.echo(tabulate(rows, headers=headers, tablefmt='grid'))
    elif format == 'json':
        click.echo(json.dumps(sig_data, indent=2))
    elif format == 'yaml':
        click.echo(yaml.dump(sig_data, default_flow_style=False))


@signatures.command()
@click.argument('signature_name')
@click.option('--format', type=click.Choice(['text', 'json', 'yaml']), default='text')
def show(signature_name: str, format: str):
    """Show detailed information about a signature."""
    registry = get_global_registry()
    
    try:
        signature = registry.get(signature_name)
        metadata = registry.get_metadata(signature_name)
        
        # Collect signature details
        details = {
            'name': signature_name,
            'description': metadata.description,
            'category': metadata.category,
            'tags': metadata.tags,
            'version': metadata.version,
            'author': metadata.author,
            'input_fields': [
                {
                    'name': f.name,
                    'description': f.description,
                    'type': str(f.type_hint),
                    'required': f.required,
                    'default': f.default
                }
                for f in signature.input_fields
            ],
            'output_fields': [
                {
                    'name': f.name,
                    'description': f.description,
                    'type': str(f.type_hint),
                    'required': f.required
                }
                for f in signature.output_fields
            ],
            'examples': signature.get_examples() if hasattr(signature, 'get_examples') else []
        }
        
        # Format output
        if format == 'text':
            click.echo(f"\n{click.style(signature_name, bold=True, fg='blue')}")
            click.echo(f"{metadata.description}\n")
            
            click.echo(click.style("Category:", bold=True) + f" {metadata.category}")
            click.echo(click.style("Tags:", bold=True) + f" {', '.join(metadata.tags)}")
            click.echo(click.style("Version:", bold=True) + f" {metadata.version}")
            
            if metadata.author:
                click.echo(click.style("Author:", bold=True) + f" {metadata.author}")
            
            click.echo(f"\n{click.style('Input Fields:', bold=True, fg='green')}")
            for field in details['input_fields']:
                req = click.style("*", fg='red') if field['required'] else " "
                click.echo(f"  {req} {field['name']} ({field['type']}): {field['description']}")
                if field['default'] is not None:
                    click.echo(f"      Default: {field['default']}")
            
            click.echo(f"\n{click.style('Output Fields:', bold=True, fg='green')}")
            for field in details['output_fields']:
                req = click.style("*", fg='red') if field['required'] else " "
                click.echo(f"  {req} {field['name']} ({field['type']}): {field['description']}")
            
            if details['examples']:
                click.echo(f"\n{click.style('Examples:', bold=True, fg='green')}")
                for i, example in enumerate(details['examples']):
                    click.echo(f"\n  Example {i+1}:")
                    click.echo(f"    Inputs: {json.dumps(example, indent=6)}")
                    
        elif format == 'json':
            click.echo(json.dumps(details, indent=2))
        elif format == 'yaml':
            click.echo(yaml.dump(details, default_flow_style=False))
            
    except KeyError:
        click.echo(f"Error: Signature '{signature_name}' not found", err=True)
        click.echo("\nUse 'hokusai signatures list' to see available signatures", err=True)


@signatures.command()
@click.argument('signature_name')
@click.option('--input', '-i', multiple=True, help='Input key=value pairs')
@click.option('--input-file', type=click.Path(exists=True), help='JSON file with inputs')
@click.option('--dry-run', is_flag=True, help='Validate inputs without execution')
@click.option('--output', type=click.Choice(['json', 'yaml', 'text']), default='json')
def test(signature_name: str, input: List[str], input_file: Optional[str], dry_run: bool, output: str):
    """Test a signature with sample inputs."""
    registry = get_global_registry()
    
    try:
        signature = registry.get(signature_name)
        
        # Parse inputs
        inputs = {}
        if input_file:
            with open(input_file, 'r') as f:
                inputs = json.load(f)
        
        # Parse command line inputs
        for inp in input:
            key, value = inp.split('=', 1)
            # Try to parse as JSON first
            try:
                inputs[key] = json.loads(value)
            except json.JSONDecodeError:
                inputs[key] = value
        
        # Validate inputs
        try:
            signature.validate_inputs(inputs)
            click.echo(click.style("✓ Input validation passed", fg='green'))
        except ValueError as e:
            click.echo(click.style(f"✗ Input validation failed: {e}", fg='red'), err=True)
            return
        
        if not dry_run:
            # Execute with DSPy Pipeline Executor
            executor = DSPyPipelineExecutor(mlflow_tracking=False)
            result = executor.execute(program=signature, inputs=inputs)
            
            if result.success:
                click.echo(click.style("\n✓ Execution successful", fg='green'))
                
                # Format output
                if output == 'json':
                    click.echo(json.dumps(result.outputs, indent=2))
                elif output == 'yaml':
                    click.echo(yaml.dump(result.outputs, default_flow_style=False))
                else:
                    for key, value in result.outputs.items():
                        click.echo(f"\n{click.style(key + ':', bold=True)}")
                        click.echo(str(value))
            else:
                click.echo(click.style(f"\n✗ Execution failed: {result.error}", fg='red'), err=True)
                
    except KeyError:
        click.echo(f"Error: Signature '{signature_name}' not found", err=True)


@signatures.command()
@click.argument('signature_name')
@click.option('--format', type=click.Choice(['yaml', 'json']), default='yaml')
@click.option('--output', '-o', type=click.Path(), help='Output file path')
def export(signature_name: str, format: str, output: Optional[str]):
    """Export a signature configuration."""
    registry = get_global_registry()
    loader = SignatureLoader()
    
    try:
        signature = registry.get(signature_name)
        
        # Save configuration
        output_path = output or f"{signature_name.lower()}.{format}"
        loader.save_signature_config(signature, output_path, format)
        
        click.echo(f"Exported '{signature_name}' to {output_path}")
        
    except KeyError:
        click.echo(f"Error: Signature '{signature_name}' not found", err=True)


@signatures.command()
@click.option('--output', '-o', type=click.Path(), help='Output file path')
@click.option('--format', type=click.Choice(['json', 'yaml']), default='json')
@click.option('--category', help='Filter by category')
def export_catalog(output: Optional[str], format: str, category: Optional[str]):
    """Export the entire signature catalog."""
    registry = get_global_registry()
    
    # Get catalog
    catalog = registry.export_catalog()
    
    # Filter by category if specified
    if category:
        catalog = [s for s in catalog if s['metadata']['category'] == category]
    
    # Format output
    if format == 'json':
        content = json.dumps(catalog, indent=2)
    else:
        content = yaml.dump(catalog, default_flow_style=False)
    
    # Write to file or stdout
    if output:
        with open(output, 'w') as f:
            f.write(content)
        click.echo(f"Exported catalog to {output}")
    else:
        click.echo(content)


@signatures.command()
@click.argument('name')
@click.option('--category', default='custom', help='Signature category')
@click.option('--tags', help='Comma-separated tags')
@click.option('--template', help='Base template to use')
def create(name: str, category: str, tags: Optional[str], template: Optional[str]):
    """Create a new signature scaffold."""
    tag_list = tags.split(',') if tags else []
    
    # Generate scaffold
    scaffold = f'''"""Custom signature: {name}."""

from src.dspy_signatures.base import BaseSignature, SignatureField


class {name}(BaseSignature):
    """{name} signature for {category} tasks."""
    
    category = "{category}"
    tags = {tag_list}
    version = "1.0.0"
    
    @classmethod
    def get_input_fields(cls):
        return [
            SignatureField(
                name="input",
                description="Main input",
                type_hint=str,
                required=True
            ),
            # Add more input fields here
        ]
    
    @classmethod
    def get_output_fields(cls):
        return [
            SignatureField(
                name="output",
                description="Main output",
                type_hint=str,
                required=True
            ),
            # Add more output fields here
        ]
    
    @classmethod
    def get_examples(cls):
        return [
            {{
                "input": "Example input",
                "output": "Example output"
            }}
        ]
'''
    
    # Save to file
    filename = f"{name.lower()}_signature.py"
    with open(filename, 'w') as f:
        f.write(scaffold)
    
    click.echo(f"Created signature scaffold: {filename}")
    click.echo("\nNext steps:")
    click.echo("1. Edit the signature fields and examples")
    click.echo("2. Test with: hokusai signatures test " + name)
    click.echo("3. Register in your code or submit as contribution")


@signatures.command()
@click.argument('alias')
@click.argument('signature_name')
def alias(alias: str, signature_name: str):
    """Create an alias for a signature."""
    registry = get_global_registry()
    
    try:
        registry.create_alias(alias, signature_name)
        click.echo(f"Created alias '{alias}' -> '{signature_name}'")
    except KeyError as e:
        click.echo(f"Error: {e}", err=True)


if __name__ == '__main__':
    signatures()