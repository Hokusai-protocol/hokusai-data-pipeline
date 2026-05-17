"""Tests for the packaged Hokusai CLI."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
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
                "_notify_pipeline_of_registration": Mock(return_value=True),
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
            __enter__=lambda s: Mock(info=Mock(run_id="run-abc")), __exit__=Mock(return_value=False)
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
    """The packaged CLI should post registration events to the data pipeline by default."""
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

    captured: dict[str, object] = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.data)
        return Response()

    with (
        patch.dict(
            os.environ,
            {
                "HOKUSAI_API_KEY": "test-key",
            },
            clear=False,
        ),
        patch.dict(
            _REGISTER_GLOBALS,
            {
                "_load_model_registry": Mock(return_value=lambda **_: mock_registry),
                "_log_model_artifact": Mock(return_value="runs:/run-123/model"),
                "_derive_api_schema_from_uri": Mock(return_value=None),
            },
        ),
        patch.object(cli_module.urllib.request, "urlopen", side_effect=fake_urlopen),
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
    assert captured["url"] == "https://registry.hokus.ai/api/models/tokenized-registration-events"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["body"]["model_name"] == "hokusai-MSG-AI"
    assert captured["body"]["version"] == "7"
    assert captured["body"]["token_id"] == "MSG-AI"
    assert captured["body"]["proposal_identifier"] == "MSG-AI"
    notify_site.assert_not_called()


def test_model_register_fails_without_api_key(tmp_path: Path) -> None:
    """Missing API key should fail after MLflow registration, before pipeline notification."""
    runner = CliRunner()
    artifact_path = tmp_path / "model.pkl"
    artifact_path.write_text("test-model")

    mock_registry = Mock()
    mock_registry.tracking_uri = "file:///tmp/mlruns"
    mock_registry._auth = Mock(api_key=None, api_endpoint="https://registry.hokus.ai/api")
    mock_registry.register_tokenized_model.return_value = {
        "model_name": "hokusai-MSG-AI",
        "version": "7",
        "token_id": "MSG-AI",
        "proposal_identifier": "MSG-AI",
        "metric_name": "reply_rate",
        "baseline_value": 0.1342,
        "mlflow_run_id": "run-123",
        "status": "registered",
        "tags": {},
    }

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
    """Pipeline failures should bubble up as non-zero CLI exits."""
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
        "tags": {},
    }

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 503, "Service Unavailable", None, None)

    with (
        patch.dict(
            _REGISTER_GLOBALS,
            {
                "_load_model_registry": Mock(return_value=lambda **_: mock_registry),
                "_log_model_artifact": Mock(return_value="runs:/run-123/model"),
                "_derive_api_schema_from_uri": Mock(return_value=None),
            },
        ),
        patch.object(cli_module.urllib.request, "urlopen", side_effect=fake_urlopen),
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
