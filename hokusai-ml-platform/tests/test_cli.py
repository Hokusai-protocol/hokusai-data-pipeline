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

from hokusai.cli import _log_model_artifact, cli  # noqa: E402


def test_model_register_uses_packaged_registry(tmp_path: Path) -> None:
    """The packaged CLI should register without any repo-local imports."""
    runner = CliRunner()
    artifact_path = tmp_path / "model.pkl"
    artifact_path.write_text("test-model")

    mock_registry = Mock()
    mock_registry.tracking_uri = "file:///tmp/mlruns"
    mock_registry.register_tokenized_model.return_value = {
        "model_name": "hokusai-MSG-AI",
        "version": "7",
        "token_id": "MSG-AI",
        "proposal_identifier": "MSG-AI",
        "mlflow_run_id": "run-123",
        "status": "registered",
    }

    with (
        patch("hokusai.cli._load_model_registry", return_value=lambda **_: mock_registry),
        patch("hokusai.cli._log_model_artifact", return_value="runs:/run-123/model") as log_model,
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
    log_model.assert_called_once()
    # Verify api_key is forwarded so MLFLOW_TRACKING_TOKEN can be set
    _, kwargs = log_model.call_args
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

    with patch(
        "hokusai.cli._load_model_registry",
        side_effect=click.ClickException(
            "Model registration requires ML dependencies. "
            "Install them with: pip install 'hokusai-ml-platform[ml]'"
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


def test_model_register_uses_webhook_url_env_fallback(tmp_path: Path) -> None:
    """The packaged CLI should honor WEBHOOK_URL when site-specific env vars are unset."""
    runner = CliRunner()
    artifact_path = tmp_path / "model.pkl"
    artifact_path.write_text("test-model")

    mock_registry = Mock()
    mock_registry.tracking_uri = "file:///tmp/mlruns"
    mock_registry.register_tokenized_model.return_value = {
        "model_name": "hokusai-MSG-AI",
        "version": "7",
        "token_id": "MSG-AI",
        "proposal_identifier": "MSG-AI",
        "mlflow_run_id": "run-123",
        "status": "registered",
    }

    response = Mock()
    response.status = 200
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with (
        patch.dict(
            os.environ,
            {
                "WEBHOOK_URL": "https://configured.example/webhook",
                "WEBHOOK_SECRET": "test-secret",
            },
            clear=False,
        ),
        patch.dict(
            os.environ,
            {
                "HOKUSAI_SITE_WEBHOOK_URL": "",
                "HOKUSAI_SITE_WEBHOOK_SECRET": "",
            },
            clear=False,
        ),
        patch("hokusai.cli._load_model_registry", return_value=lambda **_: mock_registry),
        patch("hokusai.cli._log_model_artifact", return_value="runs:/run-123/model"),
        patch("hokusai.cli.urllib.request.urlopen", return_value=response) as urlopen,
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
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://configured.example/webhook"
