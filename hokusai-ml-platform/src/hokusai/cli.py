"""Packaged CLI for the Hokusai SDK."""

from __future__ import annotations

from pathlib import Path

import click


@click.group()
def cli() -> None:
    """Hokusai SDK command-line interface."""


@cli.group()
def model() -> None:
    """Model management commands."""


@model.command("register")
@click.option("--token-id", required=True, help="Token ID created on Hokusai site (e.g. MSG-AI).")
@click.option(
    "--model-path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to the local model artifact file or directory.",
)
@click.option("--metric", required=True, help="Benchmark metric name (e.g. accuracy, auroc).")
@click.option(
    "--baseline",
    required=True,
    type=float,
    help="Baseline value for the benchmark metric.",
)
@click.option(
    "--model-name",
    default=None,
    help="MLflow registered model name. Defaults to hokusai-<token-id>.",
)
@click.option(
    "--proposal-identifier",
    default=None,
    help="Canonical proposal identifier to store alongside the token ID.",
)
@click.option(
    "--mlflow-uri",
    default=None,
    help="MLflow tracking URI. Defaults to the SDK configuration.",
)
@click.option("--api-key", default=None, help="Hokusai API key. Defaults to HOKUSAI_API_KEY.")
@click.option(
    "--api-endpoint",
    default=None,
    help="Hokusai API endpoint. Defaults to HOKUSAI_API_ENDPOINT.",
)
def register_model(
    token_id: str,
    model_path: Path,
    metric: str,
    baseline: float,
    model_name: str | None,
    proposal_identifier: str | None,
    mlflow_uri: str | None,
    api_key: str | None,
    api_endpoint: str | None,
) -> None:
    """Register a local model artifact without requiring a repository checkout."""
    ModelRegistry = _load_model_registry()

    registry = ModelRegistry(tracking_uri=mlflow_uri, api_key=api_key, api_endpoint=api_endpoint)
    resolved_model_name = model_name or f"hokusai-{token_id}"

    click.echo(f"Uploading model artifact from {model_path}...")
    model_uri = _log_model_artifact(
        model_path=model_path,
        token_id=token_id,
        metric=metric,
        baseline=baseline,
        tracking_uri=registry.tracking_uri,
        api_key=registry._auth.api_key,
    )

    additional_tags = {}
    if proposal_identifier:
        additional_tags["proposal_identifier"] = proposal_identifier

    click.echo(f"Registering {resolved_model_name} for token {token_id}...")
    result = registry.register_tokenized_model(
        model_uri=model_uri,
        model_name=resolved_model_name,
        token_id=token_id,
        metric_name=metric,
        baseline_value=baseline,
        additional_tags=additional_tags or None,
    )

    click.echo("Model registration complete.")
    click.echo(f"  Model name: {result['model_name']}")
    click.echo(f"  Version: {result['version']}")
    click.echo(f"  Token ID: {result['token_id']}")
    click.echo(f"  Proposal ID: {result['proposal_identifier']}")
    click.echo(f"  MLflow run ID: {result['mlflow_run_id']}")
    click.echo(f"  Status: {result['status']}")


def _log_model_artifact(
    *,
    model_path: Path,
    token_id: str,
    metric: str,
    baseline: float,
    tracking_uri: str,
    api_key: str | None = None,
) -> str:
    """Log a local artifact as an MLflow pyfunc model and return its URI."""
    import os

    import mlflow

    class _ArtifactReferenceModel(mlflow.pyfunc.PythonModel):
        """Minimal pyfunc wrapper that preserves the original artifact."""

        def load_context(self, context: object) -> None:  # type: ignore[override]  # noqa: ANN101
            self.model_artifact_path = context.artifacts["model_artifact"]  # type: ignore[attr-defined]

        def predict(self, context: object, model_input: object, params: object = None) -> None:  # type: ignore[override]  # noqa: ANN101
            raise NotImplementedError(
                "This registered artifact is intended for registry/deployment workflows."
            )

    resolved_path = model_path.resolve()
    mlflow.set_tracking_uri(tracking_uri)
    if api_key:
        os.environ["MLFLOW_TRACKING_TOKEN"] = api_key

    with mlflow.start_run() as run:
        mlflow.log_param("hokusai_token_id", token_id)
        mlflow.log_param("benchmark_metric", metric)
        mlflow.log_param("benchmark_value", baseline)
        mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=_ArtifactReferenceModel(),
            artifacts={"model_artifact": str(resolved_path)},
        )

        return f"runs:/{run.info.run_id}/model"


def _load_model_registry() -> type:
    """Import ModelRegistry lazily so the CLI stays importable without [ml]."""
    try:
        from hokusai.core.registry import ModelRegistry
    except ImportError as exc:
        raise click.ClickException(
            "Model registration requires ML dependencies. "
            "Install them with: pip install 'hokusai-ml-platform[ml]'"
        ) from exc

    return ModelRegistry
