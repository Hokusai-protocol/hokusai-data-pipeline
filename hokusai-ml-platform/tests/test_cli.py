"""Tests for the packaged Hokusai CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import click
from click.testing import CliRunner

SDK_SRC = Path(__file__).parent.parent / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from hokusai.cli import cli


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
