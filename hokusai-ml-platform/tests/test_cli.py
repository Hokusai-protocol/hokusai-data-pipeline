"""Tests for the packaged Hokusai CLI."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import click
from click.testing import CliRunner

SDK_SRC = Path(__file__).parent.parent / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))
for _mod in list(sys.modules):
    if _mod == "hokusai" or _mod.startswith("hokusai."):
        del sys.modules[_mod]

import hokusai.cli as cli_module  # noqa: E402

_log_model_artifact = cli_module._log_model_artifact
cli = cli_module.cli
_REGISTER_CALLBACK = cli.commands["model"].commands["register"].callback
_REGISTER_GLOBALS = _REGISTER_CALLBACK.__globals__

SAMPLE_API_SCHEMA = {
    "inputSchema": {
        "type": "object",
        "properties": {"prompt": {"type": "string"}},
        "required": ["prompt"],
    }
}


def test_model_register_uses_packaged_registry(tmp_path: Path) -> None:
    """The packaged CLI should register without any repo-local imports."""
    runner = CliRunner()
    artifact_path = tmp_path / "model.pkl"
    artifact_path.write_text("test-model")

    mock_registry = Mock()
    mock_registry.tracking_uri = "file:///tmp/mlruns"
    mock_registry._auth = Mock(api_key="test-key", api_endpoint="https://registry.hokus.ai/api")
    mock_registry.register_tokenized_model.return_value = {
        "model_name": "hokusai-MSG-AI",
        "version": "7",
        "token_id": "MSG-AI",
        "proposal_identifier": "MSG-AI",
        "metric_name": "reply_rate",
        "baseline_value": 0.1342,
        "mlflow_run_id": "run-123",
        "status": "registered",
    }
    mock_log_model = Mock(return_value="runs:/run-123/model")

    with (
        patch.dict(
            _REGISTER_GLOBALS,
            {
                "_load_model_registry": Mock(return_value=lambda **_: mock_registry),
                "_log_model_artifact": mock_log_model,
                "_derive_api_schema_from_uri": Mock(return_value=None),
            },
        ),
        patch.dict(os.environ, {"HOKUSAI_API_KEY": "test-key"}, clear=False),
    ):
        result = runner.invoke(
            cli,
            [
                "model",
                "register",
                "--token-id",
                "MSG-AI",
                "--model-path",
                str(artifact_path),
                "--metric",
                "reply_rate",
                "--baseline",
                "0.1342",
                "--proposal-identifier",
                "MSG-AI",
            ],
        )

    assert result.exit_code == 0, result.output
    mock_log_model.assert_called_once()
    # Verify api_key is forwarded so MLFLOW_TRACKING_TOKEN can be set
    _, kwargs = mock_log_model.call_args
    assert "api_key" in kwargs
    mock_registry.register_tokenized_model.assert_called_once_with(
        model_uri="runs:/run-123/model",
        model_name="hokusai-MSG-AI",
        token_id="MSG-AI",
        metric_name="reply_rate",
        baseline_value=0.1342,
        additional_tags={"proposal_identifier": "MSG-AI"},
        eval_spec=None,
        scorer_ref=None,
        primary_metric=None,
        benchmark_spec_id=None,
        notify_site=True,
        best_effort_notification=False,
        api_schema=None,
        notification_api_endpoint=None,
    )
    assert "Model registration complete." in result.output


def test_model_register_surfaces_missing_ml_extra(tmp_path: Path) -> None:
    """Users should get an actionable install command when ML deps are absent."""
    runner = CliRunner()
    artifact_path = tmp_path / "model.pkl"
    artifact_path.write_text("test-model")

    with patch.dict(
        _REGISTER_GLOBALS,
        {
            "_load_model_registry": Mock(
                side_effect=click.ClickException(
                    "Model registration requires ML dependencies. "
                    "Install them with: pip install 'hokusai-ml-platform[ml]'"
                )
            ),
            "_derive_api_schema_from_uri": Mock(return_value=None),
        },
    ):
        result = runner.invoke(
            cli,
            [
                "model",
                "register",
                "--token-id",
                "MSG-AI",
                "--model-path",
                str(artifact_path),
                "--metric",
                "reply_rate",
                "--baseline",
                "0.1342",
            ],
        )

    assert result.exit_code != 0
    assert "pip install 'hokusai-ml-platform[ml]'" in result.output


def test_log_model_artifact_sets_mlflow_tracking_token(tmp_path: Path) -> None:
    """_log_model_artifact must set MLFLOW_TRACKING_TOKEN before mlflow.start_run()."""
    artifact_path = tmp_path / "model.pkl"
    artifact_path.write_text("test-model")

    token_seen: list[str | None] = []

    def fake_start_run():
        token_seen.append(os.environ.get("MLFLOW_TRACKING_TOKEN"))
        return Mock(
            __enter__=lambda s: Mock(info=Mock(run_id="run-abc")),
            __exit__=Mock(return_value=False),
        )

    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.start_run", side_effect=fake_start_run),
        patch("mlflow.log_param"),
        patch("mlflow.pyfunc.log_model"),
    ):
        _log_model_artifact(
            model_path=artifact_path,
            token_id="MSG-AI",
            metric="reply_rate",
            baseline=0.5,
            tracking_uri="https://registry.hokus.ai/api/mlflow",
            api_key="test-key-123",
        )

    assert token_seen == [
        "test-key-123"
    ], "MLFLOW_TRACKING_TOKEN must be set before mlflow.start_run()"


def test_model_register_notifies_pipeline_by_default(tmp_path: Path) -> None:
    """The packaged CLI should rely on registry notification by default."""
    runner = CliRunner()
    artifact_path = tmp_path / "model.pkl"
    artifact_path.write_text("test-model")

    mock_registry = Mock()
    mock_registry.tracking_uri = "file:///tmp/mlruns"
    mock_registry._auth = Mock(api_key="test-key", api_endpoint="https://registry.hokus.ai/api")
    mock_registry.register_tokenized_model.return_value = {
        "model_name": "hokusai-MSG-AI",
        "version": "7",
        "token_id": "MSG-AI",
        "proposal_identifier": "MSG-AI",
        "metric_name": "reply_rate",
        "baseline_value": 0.1342,
        "mlflow_run_id": "run-123",
        "status": "registered",
        "event_emitted": True,
        "site_status_update": "succeeded",
    }

    with (
        patch.dict(
            _REGISTER_GLOBALS,
            {
                "_load_model_registry": Mock(return_value=lambda **_: mock_registry),
                "_log_model_artifact": Mock(return_value="runs:/run-123/model"),
                "_derive_api_schema_from_uri": Mock(return_value=None),
            },
        ),
        patch.object(cli_module, "_notify_site_of_registration") as notify_site,
    ):
        result = runner.invoke(
            cli,
            [
                "model",
                "register",
                "--token-id",
                "MSG-AI",
                "--model-path",
                str(artifact_path),
                "--metric",
                "reply_rate",
                "--baseline",
                "0.1342",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Data pipeline notified successfully." in result.output
    notify_site.assert_not_called()
    mock_registry.register_tokenized_model.assert_called_once()


def test_model_register_forwards_derived_api_schema_to_registry(tmp_path: Path) -> None:
    """CLI registration should pass derived api_schema into the shared registry path."""
    runner = CliRunner()
    artifact_path = tmp_path / "model.pkl"
    artifact_path.write_text("test-model")

    mock_registry = Mock()
    mock_registry.tracking_uri = "file:///tmp/mlruns"
    mock_registry._auth = Mock(api_key="test-key", api_endpoint="https://registry.hokus.ai/api")
    mock_registry.register_tokenized_model.return_value = {
        "model_name": "hokusai-MSG-AI",
        "version": "7",
        "token_id": "MSG-AI",
        "proposal_identifier": "MSG-AI",
        "metric_name": "reply_rate",
        "baseline_value": 0.1342,
        "mlflow_run_id": "run-123",
        "status": "registered",
        "event_emitted": True,
        "site_status_update": "succeeded",
    }

    with (
        patch.dict(
            _REGISTER_GLOBALS,
            {
                "_load_model_registry": Mock(return_value=lambda **_: mock_registry),
                "_log_model_artifact": Mock(return_value="runs:/run-123/model"),
                "_derive_api_schema_from_uri": Mock(return_value=SAMPLE_API_SCHEMA),
            },
        ),
        patch.object(cli_module, "_notify_site_of_registration") as notify_site,
    ):
        result = runner.invoke(
            cli,
            [
                "model",
                "register",
                "--token-id",
                "MSG-AI",
                "--model-path",
                str(artifact_path),
                "--metric",
                "reply_rate",
                "--baseline",
                "0.1342",
            ],
        )

    assert result.exit_code == 0, result.output
    assert (
        mock_registry.register_tokenized_model.call_args.kwargs["api_schema"] == SAMPLE_API_SCHEMA
    )
    notify_site.assert_not_called()


def test_model_register_forwards_richer_registration_metadata(tmp_path: Path) -> None:
    """CLI flags should forward richer benchmark identity fields to the registry."""
    runner = CliRunner()
    artifact_path = tmp_path / "model.pkl"
    artifact_path.write_text("test-model")

    mock_registry = Mock()
    mock_registry.tracking_uri = "file:///tmp/mlruns"
    mock_registry._auth = Mock(api_key="test-key", api_endpoint="https://registry.hokus.ai/api")
    mock_registry.register_tokenized_model.return_value = {
        "model_name": "hokusai-MSG-AI",
        "version": "7",
        "token_id": "MSG-AI",
        "proposal_identifier": "MSG-AI",
        "metric_name": "reply_rate",
        "baseline_value": 0.1342,
        "mlflow_run_id": "run-123",
        "status": "registered",
        "event_emitted": True,
        "site_status_update": "succeeded",
    }

    with patch.dict(
        _REGISTER_GLOBALS,
        {
            "_load_model_registry": Mock(return_value=lambda **_: mock_registry),
            "_log_model_artifact": Mock(return_value="runs:/run-123/model"),
            "_derive_api_schema_from_uri": Mock(return_value=None),
        },
    ):
        result = runner.invoke(
            cli,
            [
                "model",
                "register",
                "--token-id",
                "MSG-AI",
                "--model-path",
                str(artifact_path),
                "--metric",
                "reply_rate",
                "--baseline",
                "0.1342",
                "--eval-spec",
                "technical_task_router/v1",
                "--scorer-ref",
                "technical_task_router.success_under_budget/v1",
                "--primary-metric",
                "success_under_budget",
                "--benchmark-spec-id",
                "technical_task_router.success_under_budget/v1",
            ],
        )

    assert result.exit_code == 0, result.output
    call_kwargs = mock_registry.register_tokenized_model.call_args.kwargs
    assert call_kwargs["eval_spec"] == "technical_task_router/v1"
    assert call_kwargs["scorer_ref"] == "technical_task_router.success_under_budget/v1"
    assert call_kwargs["primary_metric"] == "success_under_budget"
    assert call_kwargs["benchmark_spec_id"] == "technical_task_router.success_under_budget/v1"


def test_model_register_fails_without_api_key(tmp_path: Path) -> None:
    """Notification failures after MLflow registration should surface cleanly."""
    runner = CliRunner()
    artifact_path = tmp_path / "model.pkl"
    artifact_path.write_text("test-model")

    mock_registry = Mock()
    mock_registry.tracking_uri = "file:///tmp/mlruns"
    mock_registry._auth = Mock(api_key=None, api_endpoint="https://registry.hokus.ai/api")
    mock_registry.register_tokenized_model.side_effect = cli_module.NotificationError(
        "HOKUSAI_API_KEY is required to emit the registration event.",
        mlflow_registered=True,
    )

    with (
        patch.dict(os.environ, {}, clear=True),
        patch.dict(
            _REGISTER_GLOBALS,
            {
                "_load_model_registry": Mock(return_value=lambda **_: mock_registry),
                "_log_model_artifact": Mock(return_value="runs:/run-123/model"),
                "_derive_api_schema_from_uri": Mock(return_value=None),
            },
        ),
    ):
        result = runner.invoke(
            cli,
            [
                "model",
                "register",
                "--token-id",
                "MSG-AI",
                "--model-path",
                str(artifact_path),
                "--metric",
                "reply_rate",
                "--baseline",
                "0.1342",
            ],
        )

    assert result.exit_code != 0
    assert "HOKUSAI_API_KEY is required" in result.output


def test_model_register_surfaces_pipeline_http_error(tmp_path: Path) -> None:
    """Notification failures should bubble up as non-zero CLI exits."""
    runner = CliRunner()
    artifact_path = tmp_path / "model.pkl"
    artifact_path.write_text("test-model")

    mock_registry = Mock()
    mock_registry.tracking_uri = "file:///tmp/mlruns"
    mock_registry._auth = Mock(api_key="test-key", api_endpoint="https://registry.hokus.ai/api")
    mock_registry.register_tokenized_model.side_effect = cli_module.NotificationError(
        "Pipeline registration notification failed with HTTP 503.",
        status_code=503,
        mlflow_registered=True,
    )

    with (
        patch.dict(
            _REGISTER_GLOBALS,
            {
                "_load_model_registry": Mock(return_value=lambda **_: mock_registry),
                "_log_model_artifact": Mock(return_value="runs:/run-123/model"),
                "_derive_api_schema_from_uri": Mock(return_value=None),
            },
        ),
    ):
        result = runner.invoke(
            cli,
            [
                "model",
                "register",
                "--token-id",
                "MSG-AI",
                "--model-path",
                str(artifact_path),
                "--metric",
                "reply_rate",
                "--baseline",
                "0.1342",
            ],
        )

    assert result.exit_code != 0
    assert "HTTP 503" in result.output


def test_model_register_help_hides_legacy_webhook_options() -> None:
    """Normal help output should not advertise direct site webhook configuration."""
    runner = CliRunner()
    result = runner.invoke(cli, ["model", "register", "--help"])

    assert result.exit_code == 0
    assert "--webhook-secret" not in result.output
    assert "HOKUSAI_SITE_WEBHOOK_SECRET" not in result.output


def test_model_register_can_skip_site_notification(tmp_path: Path) -> None:
    """The CLI should expose the explicit notification opt-out."""
    runner = CliRunner()
    artifact_path = tmp_path / "model.pkl"
    artifact_path.write_text("test-model")

    mock_registry = Mock()
    mock_registry.tracking_uri = "file:///tmp/mlruns"
    mock_registry._auth = Mock(api_key="test-key", api_endpoint="https://registry.hokus.ai/api")
    mock_registry.register_tokenized_model.return_value = {
        "model_name": "hokusai-MSG-AI",
        "version": "7",
        "token_id": "MSG-AI",
        "proposal_identifier": "MSG-AI",
        "metric_name": "reply_rate",
        "baseline_value": 0.1342,
        "mlflow_run_id": "run-123",
        "status": "registered",
        "event_emitted": False,
        "site_status_update": "skipped",
    }

    with patch.dict(
        _REGISTER_GLOBALS,
        {
            "_load_model_registry": Mock(return_value=lambda **_: mock_registry),
            "_log_model_artifact": Mock(return_value="runs:/run-123/model"),
            "_derive_api_schema_from_uri": Mock(return_value=None),
        },
    ):
        result = runner.invoke(
            cli,
            [
                "model",
                "register",
                "--token-id",
                "MSG-AI",
                "--model-path",
                str(artifact_path),
                "--metric",
                "reply_rate",
                "--baseline",
                "0.1342",
                "--no-notify-site",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Site notification skipped." in result.output
    assert mock_registry.register_tokenized_model.call_args.kwargs["notify_site"] is False
