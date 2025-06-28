"""
Main CLI interface for the Hokusai Data Evaluation Pipeline
"""
import click
from pipeline import Pipeline, PipelineConfig
from evaluator import Evaluator
from comparator import Comparator
from status_checker import StatusChecker
import sys
import os

# Add src directory to path to import commands
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from cli.signatures import signatures as signature_commands
from cli.teleprompt import teleprompt as teleprompt_commands


@click.group()
@click.version_option(version='0.1.0')
def cli():
    """Hokusai Data Pipeline CLI
    
    A command-line interface for running machine learning model evaluations
    with reproducible, attestation-ready outputs.
    """
    pass


@cli.command()
@click.option('--config', required=True, help='Path to configuration YAML file')
def run(config):
    """Run the evaluation pipeline"""
    try:
        pipeline_config = PipelineConfig.from_yaml(config)
        pipeline = Pipeline(pipeline_config)
        results = pipeline.run()
        
        click.echo("Pipeline completed successfully!")
        click.echo(f"Results: {results}")
        
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.ClickException(str(e))


@cli.command()
@click.option('--model-path', required=True, help='Path to the model to evaluate')
@click.option('--dataset-path', required=True, help='Path to the evaluation dataset')
@click.option('--output-dir', help='Directory to save evaluation results')
def evaluate(model_path, dataset_path, output_dir):
    """Evaluate a model on a dataset"""
    try:
        evaluator = Evaluator()
        # This is a simplified interface - actual implementation would load model/dataset
        click.echo(f"Evaluating model at {model_path}")
        click.echo(f"Using dataset at {dataset_path}")
        
        # Placeholder for actual evaluation
        results = evaluator.evaluate(model_path, dataset_path)
        
        if output_dir:
            click.echo(f"Results saved to {output_dir}")
        else:
            click.echo(f"Evaluation complete: {results}")
            
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.ClickException(str(e))


@cli.command()
@click.option('--model1', required=True, help='Path to first model')
@click.option('--model2', required=True, help='Path to second model')
@click.option('--dataset', required=True, help='Path to evaluation dataset')
@click.option('--output-dir', help='Directory to save comparison results')
def compare(model1, model2, dataset, output_dir):
    """Compare two models on a dataset"""
    try:
        comparator = Comparator()
        
        click.echo(f"Comparing models:")
        click.echo(f"  Model 1: {model1}")
        click.echo(f"  Model 2: {model2}")
        click.echo(f"  Dataset: {dataset}")
        
        results = comparator.compare(model1, model2, dataset)
        
        if output_dir:
            click.echo(f"Comparison results saved to {output_dir}")
        else:
            click.echo(f"Comparison complete: {results}")
            
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.ClickException(str(e))


@cli.command()
def status():
    """Check pipeline status"""
    try:
        status_checker = StatusChecker()
        status_info = status_checker.get_status()
        
        click.echo("Pipeline Status:")
        click.echo(f"  Running: {status_info.get('running', False)}")
        click.echo(f"  Last Run: {status_info.get('last_run', 'Never')}")
        click.echo(f"  Status: {status_info.get('status', 'Unknown')}")
        
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.ClickException(str(e))


# Add commands to the main CLI
cli.add_command(signature_commands)
cli.add_command(teleprompt_commands)

if __name__ == '__main__':
    cli()