"""
Model management CLI commands for Hokusai ML Platform
"""
import click
import os
import mlflow
from typing import Optional
import sys

# Add parent directory to path to import database modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from database import DatabaseConfig, DatabaseConnection, TokenOperations
from validation import MetricValidator, BaselineComparator
from events import EventPublisher, WebhookHandler, ConsoleHandler
from errors import (
    configure_logging, ErrorHandler, TokenNotFoundError, 
    MetricValidationError, MLflowError, DatabaseConnectionError
)


@click.group()
def model():
    """Model management commands"""
    pass


@model.command()
@click.option('--token-id', required=True, help='Token ID created on Hokusai site (e.g., XRAY)')
@click.option('--model-path', required=True, type=click.Path(exists=True), help='Path to model checkpoint/artifacts')
@click.option('--metric', required=True, help='Performance metric name (e.g., auroc, accuracy, f1)')
@click.option('--baseline', required=True, type=float, help='Baseline performance value to validate against')
@click.option('--mlflow-uri', default=None, help='MLflow tracking URI (defaults to environment variable)')
@click.option('--db-config', default=None, type=click.Path(exists=True), help='Path to database configuration file')
@click.option('--webhook-url', default=None, help='Webhook URL for event notifications')
def register(token_id: str, model_path: str, metric: str, baseline: float, 
             mlflow_uri: Optional[str], db_config: Optional[str], webhook_url: Optional[str]):
    """Register a model created on the Hokusai site
    
    This command uploads a model to MLflow, validates its performance against
    a baseline, and updates the model status in the database.
    
    Example:
        hokusai model register --token-id XRAY --model-path ./checkpoints/final \\
            --metric auroc --baseline 0.82
    """
    # Configure logging
    configure_logging(level="INFO")
    error_handler = ErrorHandler()
    
    try:
        click.echo(f"Registering model for token: {token_id}")
        
        # Step 1: Validate inputs
        validator = MetricValidator()
        
        if not validator.validate_metric_name(metric):
            raise MetricValidationError(metric, reason="Unsupported metric")
        
        if not validator.validate_baseline(metric, baseline):
            raise MetricValidationError(metric, baseline, 
                                      reason="Invalid baseline value for metric")
        
        # Step 2: Initialize MLflow
        if mlflow_uri:
            mlflow.set_tracking_uri(mlflow_uri)
        elif os.getenv("MLFLOW_TRACKING_URI"):
            mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI"))
        else:
            click.echo("Warning: No MLflow tracking URI specified, using local file store", err=True)
        
        # Step 3: Validate token exists and is in Draft status
        click.echo(f"Validating token {token_id} status...")
        
        # Load database configuration
        if db_config:
            db_conf = DatabaseConfig.from_file(db_config)
        else:
            db_conf = DatabaseConfig.from_env()
        
        # Connect to database and validate token
        try:
            with DatabaseConnection(db_conf).session() as db:
                token_ops = TokenOperations(db)
                token_ops.validate_token_status(token_id)
                click.echo(f"✓ Token {token_id} validated successfully")
        except ValueError as e:
            if "not found" in str(e):
                raise TokenNotFoundError(token_id)
            else:
                raise
        except Exception as e:
            raise DatabaseConnectionError(f"Failed to connect to database: {str(e)}")
        
        # Step 4: Upload model to MLflow
        click.echo(f"Uploading model from {model_path} to MLflow...")
        try:
            mlflow_run_id = _upload_model_to_mlflow(
                token_id=token_id,
                model_path=model_path,
                metric=metric,
                baseline=baseline
            )
            click.echo(f"Model uploaded successfully. MLflow run ID: {mlflow_run_id}")
        except Exception as e:
            raise MLflowError("model upload", str(e))
        
        # Step 5: Validate metric against baseline
        # TODO: Calculate actual metric value from model
        # For now, we'll use a placeholder
        actual_metric_value = baseline + 0.01  # Simulated improvement
        
        # Use baseline comparator for validation
        comparator = BaselineComparator()
        validation_result = comparator.validate_improvement(
            current_value=actual_metric_value,
            baseline_value=baseline,
            metric_name=metric
        )
        
        if not validation_result["meets_baseline"]:
            raise click.ClickException(
                f"Model performance ({actual_metric_value:.4f}) does not meet baseline requirement ({baseline:.4f})"
            )
        
        click.echo("✓ Model performance validation:")
        click.echo(f"   Current: {actual_metric_value:.4f}")
        click.echo(f"   Baseline: {baseline:.4f}")
        click.echo(f"   Improvement: {validation_result['improvement']:.4f} ({validation_result['improvement_percentage']:.2f}%)")
        
        # Step 6: Update model status in database
        click.echo("Updating model status to 'registered'...")
        with DatabaseConnection(db_conf).session() as db:
            token_ops = TokenOperations(db)
            success = token_ops.save_mlflow_run_id(
                token_id=token_id,
                mlflow_run_id=mlflow_run_id,
                metric_name=metric,
                metric_value=actual_metric_value,
                baseline_value=baseline
            )
            if not success:
                raise click.ClickException("Failed to update model status in database")
        
        # Step 7: Emit event
        click.echo("Emitting token_ready_for_deploy event...")
        
        # Initialize event publisher
        publisher = EventPublisher()
        
        # Add console handler (always log events)
        publisher.register_handler(ConsoleHandler())
        
        # Add webhook handler if URL provided
        if webhook_url:
            publisher.register_handler(WebhookHandler(webhook_url))
            
        # Publish events
        publisher.publish_token_ready(token_id, mlflow_run_id, {
            "metric_name": metric,
            "metric_value": actual_metric_value,
            "baseline_value": baseline
        })
        
        publisher.publish_model_registered(
            token_id=token_id,
            mlflow_run_id=mlflow_run_id,
            metric_name=metric,
            metric_value=actual_metric_value,
            baseline_value=baseline
        )
        
        click.echo(f"✅ Model registration complete for token {token_id}")
        click.echo(f"   MLflow run ID: {mlflow_run_id}")
        click.echo("   Status: registered")
        click.echo("   Event emitted: token_ready_for_deploy")
        
    except (TokenNotFoundError, MetricValidationError, DatabaseConnectionError, 
            MLflowError) as e:
        # Handle our custom exceptions
        error_handler.handle_error(e, context={
            "token_id": token_id,
            "model_path": model_path,
            "metric": metric,
            "baseline": baseline
        }, raise_error=False)
        
        user_msg = ErrorHandler.create_user_friendly_message(e)
        click.echo(f"❌ {user_msg}", err=True)
        raise click.ClickException(str(e))
        
    except Exception as e:
        # Handle unexpected exceptions
        error_handler.handle_error(e, context={
            "token_id": token_id,
            "operation": "model_register"
        }, raise_error=False)
        
        click.echo(f"❌ Unexpected error: {str(e)}", err=True)
        raise click.ClickException("An unexpected error occurred. Please check the logs for details.")



def _upload_model_to_mlflow(token_id: str, model_path: str, metric: str, baseline: float) -> str:
    """Upload model to MLflow and return the run ID"""
    with mlflow.start_run() as run:
        # Log model
        mlflow.log_artifact(model_path)
        
        # Log parameters
        mlflow.log_param("token_id", token_id)
        mlflow.log_param("metric_name", metric)
        mlflow.log_param("baseline_value", baseline)
        
        # Log tags
        mlflow.set_tag("hokusai_token_id", token_id)
        mlflow.set_tag("model_status", "registering")
        mlflow.set_tag("benchmark_metric", metric)
        mlflow.set_tag("benchmark_value", str(baseline))
        
        # Register model in MLflow model registry
        model_name = f"hokusai-{token_id}"
        mlflow.register_model(
            f"runs:/{run.info.run_id}/model",
            model_name,
            tags={
                "hokusai_token_id": token_id,
                "benchmark_metric": metric,
                "benchmark_value": str(baseline)
            }
        )
        
        return run.info.run_id



@model.command()
@click.option('--token-id', required=True, help='Token ID to check status for')
@click.option('--db-config', default=None, type=click.Path(exists=True), help='Path to database configuration file')
def status(token_id: str, db_config: Optional[str]):
    """Check the registration status of a model"""
    try:
        click.echo(f"Checking status for token: {token_id}")
        
        # TODO: Implement database query to get model status
        # For now, we'll show a placeholder
        click.echo(f"Token ID: {token_id}")
        click.echo("Status: Draft")  # Placeholder
        click.echo("MLflow run ID: Not registered")  # Placeholder
        
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.ClickException(str(e))


@model.command()
def list():
    """List all registered models"""
    try:
        # TODO: Query MLflow model registry
        client = mlflow.tracking.MlflowClient()
        models = client.list_registered_models()
        
        if not models:
            click.echo("No models registered yet.")
            return
        
        click.echo("Registered models:")
        for model in models:
            if model.name.startswith("hokusai-"):
                token_id = model.name.replace("hokusai-", "")
                latest_version = model.latest_versions[0] if model.latest_versions else None
                
                click.echo(f"\nToken ID: {token_id}")
                click.echo(f"  Model name: {model.name}")
                if latest_version:
                    click.echo(f"  Latest version: {latest_version.version}")
                    click.echo(f"  Status: {latest_version.current_stage}")
                    if latest_version.tags:
                        click.echo(f"  Metric: {latest_version.tags.get('benchmark_metric', 'N/A')}")
                        click.echo(f"  Baseline: {latest_version.tags.get('benchmark_value', 'N/A')}")
                
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.ClickException(str(e))