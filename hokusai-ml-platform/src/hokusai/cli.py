"""Packaged CLI for the Hokusai SDK."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

import click
from hokusai.exceptions import NotificationError

from .core.notification import (
    build_registration_event_payload,
    notify_pipeline_of_registration,
)

logger = logging.getLogger(__name__)

_DEFAULT_SITE_WEBHOOK_URL = "https://hokus.ai/api/webhooks/model-registration"


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
@click.option("--eval-spec", default=None, help="Eval spec identifier to record on the model.")
@click.option("--scorer-ref", default=None, help="Canonical scorer reference for the model.")
@click.option(
    "--primary-metric",
    default=None,
    help="Primary metric name to record alongside benchmark metadata.",
)
@click.option(
    "--benchmark-spec-id",
    default=None,
    help="BenchmarkSpec identifier to record alongside the registration.",
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
@click.option(
    "--site-webhook-url",
    default=None,
    hidden=True,
    help=(
        "URL of the Hokusai site webhook endpoint. "
        f"Defaults to HOKUSAI_SITE_WEBHOOK_URL, WEBHOOK_URL, or {_DEFAULT_SITE_WEBHOOK_URL}."
    ),
)
@click.option(
    "--webhook-secret",
    default=None,
    hidden=True,
    help="HMAC secret for signing the site notification. Defaults to HOKUSAI_SITE_WEBHOOK_SECRET.",
)
@click.option(
    "--use-legacy-webhook",
    is_flag=True,
    hidden=True,
    help="Internal/debug fallback to notify the site directly instead of the data pipeline API.",
)
@click.option(
    "--no-notify-site",
    is_flag=True,
    help="Register in MLflow without emitting the Hokusai site registration event.",
)
@click.option(
    "--best-effort-notification",
    is_flag=True,
    help="Do not fail the command if the site notification step fails after MLflow registration.",
)
def register_model(
    token_id: str,
    model_path: Path,
    metric: str,
    baseline: float,
    model_name: str | None,
    proposal_identifier: str | None,
    eval_spec: str | None,
    scorer_ref: str | None,
    primary_metric: str | None,
    benchmark_spec_id: str | None,
    mlflow_uri: str | None,
    api_key: str | None,
    api_endpoint: str | None,
    site_webhook_url: str | None,
    webhook_secret: str | None,
    use_legacy_webhook: bool,
    no_notify_site: bool,
    best_effort_notification: bool,
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
    api_schema = _derive_api_schema_from_uri(model_uri)

    try:
        result = registry.register_tokenized_model(
            model_uri=model_uri,
            model_name=resolved_model_name,
            token_id=token_id,
            metric_name=metric,
            baseline_value=baseline,
            additional_tags=additional_tags or None,
            eval_spec=eval_spec,
            scorer_ref=scorer_ref,
            primary_metric=primary_metric,
            benchmark_spec_id=benchmark_spec_id,
            notify_site=not no_notify_site and not use_legacy_webhook,
            best_effort_notification=best_effort_notification,
            api_schema=api_schema,
            notification_api_endpoint=api_endpoint,
        )
    except NotificationError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("Model registration complete.")
    click.echo(f"  Model name: {result['model_name']}")
    click.echo(f"  Version: {result['version']}")
    click.echo(f"  Token ID: {result['token_id']}")
    click.echo(f"  Proposal ID: {result['proposal_identifier']}")
    click.echo(f"  MLflow run ID: {result['mlflow_run_id']}")
    click.echo(f"  Status: {result['status']}")

    model_uri = f"models:/{result['model_name']}/{result['version']}"
    if api_schema is None:
        api_schema = _derive_api_schema_from_uri(model_uri)
    if (site_webhook_url or webhook_secret) and not use_legacy_webhook:
        click.echo(
            "Warning: --site-webhook-url and --webhook-secret are ignored unless "
            "--use-legacy-webhook is set.",
            err=True,
        )

    if use_legacy_webhook:
        click.echo("Notifying Hokusai site of registration...")
        notified = _notify_site_of_registration(
            result,
            site_webhook_url=site_webhook_url,
            webhook_secret=webhook_secret,
            api_schema=api_schema,
        )
        if not notified:
            raise click.ClickException("Legacy site notification failed.")
        click.echo("  Site notified successfully.")
        return

    site_status = result.get("site_status_update")
    if site_status == "succeeded":
        click.echo("  Data pipeline notified successfully.")
    elif site_status == "failed":
        click.echo("  Data pipeline notification failed after MLflow registration.", err=True)
    elif site_status == "skipped":
        click.echo("  Site notification skipped.")


def _derive_api_schema_from_uri(model_uri: str) -> Optional[dict[str, Any]]:
    """Derive api_schema from an MLflow model URI's signature.

    This is a self-contained implementation (no shared module with the data
    pipeline service) so the CLI package stays independent. Returns None on
    any failure so callers can still send the webhook without api_schema.
    """
    try:
        import mlflow.models
        from mlflow.types import ColSpec

        info = mlflow.models.get_model_info(model_uri)
        sig = info.signature
        if sig is None:
            return None

        _type_map: dict[str, dict[str, str]] = {
            "string": {"type": "string"},
            "integer": {"type": "integer"},
            "long": {"type": "integer"},
            "float": {"type": "number"},
            "double": {"type": "number"},
            "boolean": {"type": "boolean"},
            "binary": {"type": "string", "format": "byte"},
            "datetime": {"type": "string", "format": "date-time"},
        }

        def _convert(schema: Any) -> Optional[dict[str, Any]]:
            if schema is None:
                return None
            try:
                inputs = schema.inputs
                if not inputs or not isinstance(inputs[0], ColSpec):
                    return None  # Tensor-based or empty schema
                props: dict[str, Any] = {}
                req: list[str] = []
                for col in inputs:
                    if not isinstance(col, ColSpec) or col.name is None:
                        return None
                    t = _type_map.get(getattr(col.type, "name", str(col.type)).lower())
                    if t:
                        props[col.name] = t
                    if getattr(col, "required", True):
                        req.append(col.name)
                if not props:
                    return None
                result: dict[str, Any] = {"type": "object", "properties": props}
                if req:
                    result["required"] = req
                return result
            except Exception:
                return None

        input_js = _convert(sig.inputs)
        output_js = _convert(sig.outputs)

        if input_js is None and output_js is None:
            return None

        api_schema: dict[str, Any] = {}
        if input_js is not None:
            api_schema["inputSchema"] = input_js
        if output_js is not None:
            api_schema["outputSchema"] = output_js
        return api_schema or None

    except Exception as exc:
        logger.warning("Could not derive api_schema from %s: %s", model_uri, exc)
        return None


def _notify_site_of_registration(
    result: dict[str, Any],
    *,
    site_webhook_url: str | None = None,
    webhook_secret: str | None = None,
    api_schema: Optional[dict[str, Any]] = None,
) -> bool:
    """POST a model_registered event to the Hokusai site webhook.

    Sends the original MLflow event format so the site's original-format Zod
    parser runs (the SDK parser is skipped because token_id is absent at the
    top level). This is the only format that surfaces model.api_schema.

    Returns True if the site acknowledged the event (HTTP 2xx), False otherwise.
    Never raises — failure is non-fatal to the overall registration.
    """
    url = (
        site_webhook_url
        or os.environ.get("HOKUSAI_SITE_WEBHOOK_URL")
        or os.environ.get("WEBHOOK_URL")
        or _DEFAULT_SITE_WEBHOOK_URL
    )
    secret = (
        webhook_secret
        or os.environ.get("HOKUSAI_SITE_WEBHOOK_SECRET")
        or os.environ.get("WEBHOOK_SECRET")
    )

    token_id: str = result["token_id"]

    model_dict: dict[str, Any] = {
        "id": token_id.lower(),
        "name": result["model_name"],
        "status": "registered",
        "version": str(result["version"]),
    }
    mlflow_run_id = result.get("mlflow_run_id")
    if mlflow_run_id:
        model_dict["run_id"] = mlflow_run_id
    if api_schema is not None:
        model_dict["api_schema"] = api_schema

    payload: dict[str, Any] = {
        "event_type": "model_registered",
        "model": model_dict,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "mlflow",
    }

    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    req = urllib.request.Request(url, data=body, method="POST")  # noqa: S310
    req.add_header("Content-Type", "application/json")

    if secret:
        sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        req.add_header("X-Hokusai-Signature", f"sha256={sig}")
    else:
        logger.warning(
            "No webhook secret configured — the site may reject unsigned notifications. "
            "Set HOKUSAI_SITE_WEBHOOK_SECRET or WEBHOOK_SECRET."
        )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        logger.warning("Site webhook returned HTTP %s: %s", exc.code, exc.reason)
        return False
    except Exception as exc:
        logger.warning("Site notification failed: %s", exc)
        return False


def _notify_pipeline_of_registration(
    result: dict[str, Any],
    *,
    api_key: str | None = None,
    api_endpoint: str | None = None,
    registry: Any | None = None,
    model_uri: str | None = None,
    api_schema: Optional[dict[str, Any]] = None,
) -> bool:
    """Backward-compatible wrapper around the shared notification helper."""
    resolved_api_key = (
        api_key
        or getattr(getattr(registry, "_auth", None), "api_key", None)
        or os.environ.get("HOKUSAI_API_KEY")
    )
    try:
        payload = build_registration_event_payload(
            result,
            model_uri=model_uri,
            api_schema=api_schema,
        )
        notify_pipeline_of_registration(
            payload,
            api_key=resolved_api_key or "",
            api_endpoint=api_endpoint,
            timeout=15,
        )
        return True
    except NotificationError as exc:
        raise click.ClickException(str(exc)) from exc


def _log_model_artifact(
    *,
    model_path: Path,
    token_id: str,
    metric: str,
    baseline: float,
    tracking_uri: str,
    api_key: str | None = None,
) -> str:
    """Log a local artifact as an MLflow pyfunc model and return its URI.

    MLflow authentication (MLFLOW_TRACKING_TOKEN / HOKUSAI_API_KEY) is configured by
    ModelRegistry.__init__ before this function is called, so no explicit auth headers
    are set here.
    """
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
