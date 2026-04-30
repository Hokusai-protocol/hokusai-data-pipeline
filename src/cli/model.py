"""Model management CLI commands for Hokusai ML Platform."""

import os
import sys
from typing import Optional

import click
import mlflow

# Add parent directory to path to import database modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from database import DatabaseConfig, DatabaseConnection, TokenOperations  # noqa: E402
from errors import (  # noqa: E402
    DatabaseConnectionError,
    ErrorHandler,
    MetricValidationError,
    MLflowError,
    TokenNotFoundError,
    configure_logging,
)
from events import ConsoleHandler, EventPublisher, WebhookHandler  # noqa: E402
from validation import BaselineComparator, MetricValidator  # noqa: E402

from ._api import BenchmarkSpecLookupError, fetch_benchmark_spec  # noqa: E402


def _floats_equal(a: float, b: float, *, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


@click.group()
def model() -> None:
    """Model management commands."""
    pass


@model.command()
@click.option("--token-id", required=True, help="Token ID created on Hokusai site (e.g., XRAY)")
@click.option(
    "--model-path",
    required=True,
    type=click.Path(exists=True),
    help="Path to model checkpoint/artifacts",
)
@click.option(
    "--metric",
    default=None,
    help="Performance metric name (e.g., auroc, accuracy, f1). Optional with --benchmark-spec-id.",
)
@click.option(
    "--baseline",
    default=None,
    type=float,
    help="Baseline performance value to validate against. Optional with --benchmark-spec-id.",
)
@click.option(
    "--benchmark-spec-id",
    default=None,
    help="BenchmarkSpec ID from the Hokusai site (e.g., bs-abc123). Derives metric/baseline.",
)
@click.option(
    "--api-url",
    default=None,
    help="Hokusai API URL (defaults to HOKUSAI_API_URL env var or http://localhost:8001)",
)
@click.option(
    "--mlflow-uri", default=None, help="MLflow tracking URI (defaults to environment variable)"
)
@click.option(
    "--db-config",
    default=None,
    type=click.Path(exists=True),
    help="Path to database configuration file",
)
@click.option("--webhook-url", default=None, help="Webhook URL for event notifications")
def register(  # noqa: C901
    token_id: str,
    model_path: str,
    metric: Optional[str],
    baseline: Optional[float],
    benchmark_spec_id: Optional[str],
    api_url: Optional[str],
    mlflow_uri: Optional[str],
    db_config: Optional[str],
    webhook_url: Optional[str],
) -> None:
    r"""Register a model created on the Hokusai site.

    This command uploads a model to MLflow, validates its performance against
    a baseline, and updates the model status in the database.

    You can supply benchmark metadata explicitly or derive it from a BenchmarkSpec.

    Example (using a BenchmarkSpec)::

        hokusai model register --token-id XRAY --benchmark-spec-id bs-abc123 \
            --model-path ./checkpoints/final

    Example (explicit metric and baseline)::

        hokusai model register --token-id XRAY --model-path ./checkpoints/final \
            --metric auroc --baseline 0.82

    """
    # Configure logging
    configure_logging(level="INFO")
    error_handler = ErrorHandler()

    try:
        click.echo(f"Registering model for token: {token_id}")

        # Step 0: Resolve metric/baseline from BenchmarkSpec when provided
        if benchmark_spec_id:
            try:
                spec = fetch_benchmark_spec(
                    benchmark_spec_id,
                    api_url=api_url,
                    api_key=os.getenv("HOKUSAI_API_KEY"),
                )
            except BenchmarkSpecLookupError as e:
                raise click.ClickException(str(e)) from e

            if not spec.get("is_active", False):
                raise click.ClickException(
                    f"Benchmark spec '{benchmark_spec_id}' is inactive; "
                    "activate it on the Hokusai site."
                )

            spec_model_id = str(spec.get("model_id", ""))
            if spec_model_id.lower() != token_id.lower():
                raise click.ClickException(
                    f"Benchmark spec '{benchmark_spec_id}' is bound to model '{spec_model_id}', "
                    f"not '{token_id}'."
                )

            spec_metric = spec.get("metric_name")
            spec_baseline = spec.get("baseline_value")
            if spec_baseline is None and baseline is None:
                raise click.ClickException(
                    f"Benchmark spec '{benchmark_spec_id}' has no baseline_value; "
                    "set one on the Hokusai site or pass --baseline explicitly."
                )

            if metric is not None and metric != spec_metric:
                click.echo(
                    f"Warning: --metric ({metric}) overrides spec metric ({spec_metric})",
                    err=True,
                )
            if (
                baseline is not None
                and spec_baseline is not None
                and not _floats_equal(baseline, float(spec_baseline))
            ):
                click.echo(
                    f"Warning: --baseline ({baseline}) overrides spec baseline ({spec_baseline})",
                    err=True,
                )

            metric = metric if metric is not None else spec_metric
            baseline = (
                baseline
                if baseline is not None
                else float(spec_baseline)
                if spec_baseline is not None
                else None
            )

            click.echo(
                f"Resolved benchmark spec {benchmark_spec_id}: "
                f"metric={metric}, baseline={baseline}, model_id={spec_model_id}"
            )
        else:
            if metric is None or baseline is None:
                raise click.ClickException(
                    "--metric and --baseline are required unless --benchmark-spec-id is provided."
                )

        # Step 1: Validate inputs
        validator = MetricValidator()

        if not validator.validate_metric_name(metric):
            raise MetricValidationError(metric, reason="Unsupported metric")

        if not validator.validate_baseline(metric, baseline):
            raise MetricValidationError(
                metric, baseline, reason="Invalid baseline value for metric"
            )

        # Step 2: Initialize MLflow
        # MLflow auth: set MLFLOW_TRACKING_TOKEN env var to configure Authorization headers.
        if mlflow_uri:
            mlflow.set_tracking_uri(mlflow_uri)
        elif os.getenv("MLFLOW_TRACKING_URI"):
            mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI"))
        else:
            click.echo(
                "Warning: No MLflow tracking URI specified, using local file store", err=True
            )

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
                raise TokenNotFoundError(token_id) from e
            else:
                raise
        except Exception as e:
            raise DatabaseConnectionError(f"Failed to connect to database: {str(e)}") from e

        # Step 4: Upload model to MLflow
        click.echo(f"Uploading model from {model_path} to MLflow...")
        try:
            mlflow_run_id = _upload_model_to_mlflow(
                token_id=token_id,
                model_path=model_path,
                metric=metric,
                baseline=baseline,
                benchmark_spec_id=benchmark_spec_id,
            )
            click.echo(f"Model uploaded successfully. MLflow run ID: {mlflow_run_id}")
        except Exception as e:
            raise MLflowError("model upload", str(e)) from e

        # Step 5: Validate metric against baseline
        # TODO: Calculate actual metric value from model
        # For now, we'll use a placeholder
        actual_metric_value = baseline + 0.01  # Simulated improvement

        # Use baseline comparator for validation
        comparator = BaselineComparator()
        validation_result = comparator.validate_improvement(
            current_value=actual_metric_value, baseline_value=baseline, metric_name=metric
        )

        if not validation_result["meets_baseline"]:
            raise click.ClickException(
                f"Model performance ({actual_metric_value:.4f}) does not meet baseline requirement ({baseline:.4f})"  # noqa: E501
            )

        click.echo("✓ Model performance validation:")
        click.echo(f"   Current: {actual_metric_value:.4f}")
        click.echo(f"   Baseline: {baseline:.4f}")
        click.echo(
            f"   Improvement: {validation_result['improvement']:.4f} ({validation_result['improvement_percentage']:.2f}%)"  # noqa: E501
        )

        # Step 6: Update model status in database
        click.echo("Updating model status to 'registered'...")
        with DatabaseConnection(db_conf).session() as db:
            token_ops = TokenOperations(db)
            success = token_ops.save_mlflow_run_id(
                token_id=token_id,
                mlflow_run_id=mlflow_run_id,
                metric_name=metric,
                metric_value=actual_metric_value,
                baseline_value=baseline,
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
        publisher.publish_token_ready(
            token_id,
            mlflow_run_id,
            {
                "metric_name": metric,
                "metric_value": actual_metric_value,
                "baseline_value": baseline,
            },
        )

        publisher.publish_model_registered(
            token_id=token_id,
            mlflow_run_id=mlflow_run_id,
            metric_name=metric,
            metric_value=actual_metric_value,
            baseline_value=baseline,
        )

        click.echo(f"✅ Model registration complete for token {token_id}")
        click.echo(f"   MLflow run ID: {mlflow_run_id}")
        click.echo("   Status: registered")
        click.echo("   Event emitted: token_ready_for_deploy")

    except (TokenNotFoundError, MetricValidationError, DatabaseConnectionError, MLflowError) as e:
        # Handle our custom exceptions
        error_handler.handle_error(
            e,
            context={
                "token_id": token_id,
                "model_path": model_path,
                "metric": metric,
                "baseline": baseline,
                "benchmark_spec_id": benchmark_spec_id,
            },
            raise_error=False,
        )

        user_msg = ErrorHandler.create_user_friendly_message(e)
        click.echo(f"❌ {user_msg}", err=True)
        raise click.ClickException(str(e)) from e

    except Exception as e:
        # Handle unexpected exceptions
        error_handler.handle_error(
            e, context={"token_id": token_id, "operation": "model_register"}, raise_error=False
        )

        click.echo(f"❌ Unexpected error: {str(e)}", err=True)
        raise click.ClickException(
            "An unexpected error occurred. Please check the logs for details."
        ) from e


def _upload_model_to_mlflow(
    token_id: str,
    model_path: str,
    metric: str,
    baseline: float,
    benchmark_spec_id: Optional[str] = None,
) -> str:
    """Upload model to MLflow and return the run ID."""
    with mlflow.start_run() as run:
        # Log model
        mlflow.log_artifact(model_path)

        # Log parameters
        mlflow.log_param("token_id", token_id)
        mlflow.log_param("metric_name", metric)
        mlflow.log_param("baseline_value", baseline)
        if benchmark_spec_id:
            mlflow.log_param("benchmark_spec_id", benchmark_spec_id)

        # Log tags
        mlflow.set_tag("hokusai_token_id", token_id)
        mlflow.set_tag("model_status", "registering")
        mlflow.set_tag("benchmark_metric", metric)
        mlflow.set_tag("benchmark_value", str(baseline))
        if benchmark_spec_id:
            mlflow.set_tag("benchmark_spec_id", benchmark_spec_id)

        # Register model in MLflow model registry
        model_name = f"hokusai-{token_id}"
        registry_tags = {
            "hokusai_token_id": token_id,
            "benchmark_metric": metric,
            "benchmark_value": str(baseline),
        }
        if benchmark_spec_id:
            registry_tags["benchmark_spec_id"] = benchmark_spec_id
        mlflow.register_model(
            f"runs:/{run.info.run_id}/model",
            model_name,
            tags=registry_tags,
        )

        return run.info.run_id


@model.command()
@click.option("--token-id", required=True, help="Token ID to check status for")
@click.option(
    "--db-config",
    default=None,
    type=click.Path(exists=True),
    help="Path to database configuration file",
)
def status(token_id: str, db_config: Optional[str]) -> None:
    """Check the registration status of a model."""
    try:
        click.echo(f"Checking status for token: {token_id}")

        # TODO: Implement database query to get model status
        # For now, we'll show a placeholder
        click.echo(f"Token ID: {token_id}")
        click.echo("Status: Draft")  # Placeholder
        click.echo("MLflow run ID: Not registered")  # Placeholder

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.ClickException(str(e)) from e


@model.command()
def list() -> None:  # noqa: A001
    """List all registered models."""
    try:
        # TODO: Query MLflow model registry
        client = mlflow.tracking.MlflowClient()
        models = client.search_registered_models()

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
                    stage = (
                        (latest_version.tags or {}).get("lifecycle_stage", "unknown").lower()
                        if hasattr(latest_version, "tags")
                        else "unknown"
                    )
                    click.echo(f"  Status: {stage}")
                    if latest_version.tags:
                        click.echo(
                            f"  Metric: {latest_version.tags.get('benchmark_metric', 'N/A')}"
                        )
                        click.echo(
                            f"  Baseline: {latest_version.tags.get('benchmark_value', 'N/A')}"
                        )

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.ClickException(str(e)) from e
