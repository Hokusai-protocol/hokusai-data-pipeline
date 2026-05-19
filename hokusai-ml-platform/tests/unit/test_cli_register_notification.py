"""Tests for CLI notification wrappers and routing behavior."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

SDK_SRC = Path(__file__).parent.parent.parent / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))
for _mod in list(sys.modules):
    if _mod == "hokusai" or _mod.startswith("hokusai."):
        del sys.modules[_mod]

import hokusai.cli as cli_module  # noqa: E402

_notify_pipeline_of_registration = cli_module._notify_pipeline_of_registration
cli = cli_module.cli
_REGISTER_CALLBACK = cli.commands["model"].commands["register"].callback
_REGISTER_GLOBALS = _REGISTER_CALLBACK.__globals__


SAMPLE_RESULT = {
    "model_name": "hokusai-HLEAD",
    "version": "7",
    "token_id": "HLEAD",
    "proposal_identifier": "HLEAD",
    "metric_name": "accuracy",
    "baseline_value": 0.10,
    "mlflow_run_id": "run-123",
    "status": "registered",
    "tags": {"proposal_identifier": "HLEAD", "hokusai_token_id": "HLEAD"},
}

SAMPLE_API_SCHEMA = {
    "inputSchema": {
        "type": "object",
        "properties": {"prompt": {"type": "string"}},
        "required": ["prompt"],
    }
}


def test_notify_pipeline_posts_expected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI wrapper should delegate to the shared helper with the same payload."""
    monkeypatch.setenv("HOKUSAI_API_KEY", "test-key")

    with patch.object(
        cli_module, "notify_pipeline_of_registration", return_value={}
    ) as notify_mock:
        assert _notify_pipeline_of_registration(SAMPLE_RESULT) is True

    payload = notify_mock.call_args.args[0]
    assert payload["model_name"] == "hokusai-HLEAD"
    assert payload["proposal_identifier"] == "HLEAD"
    assert payload["model_uri"] == "models:/hokusai-HLEAD/7"
    assert notify_mock.call_args.kwargs["api_key"] == "test-key"


def test_notify_pipeline_uses_non_api_base_when_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bare domains should be passed through to the shared helper."""
    monkeypatch.setenv("HOKUSAI_API_KEY", "test-key")

    with patch.object(
        cli_module, "notify_pipeline_of_registration", return_value={}
    ) as notify_mock:
        _notify_pipeline_of_registration(SAMPLE_RESULT, api_endpoint="https://registry.hokus.ai")

    assert notify_mock.call_args.kwargs["api_endpoint"] == "https://registry.hokus.ai"


def test_notify_pipeline_forwards_explicit_api_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI compatibility wrapper should include explicit api_schema when provided."""
    monkeypatch.setenv("HOKUSAI_API_KEY", "test-key")

    with patch.object(
        cli_module, "notify_pipeline_of_registration", return_value={}
    ) as notify_mock:
        assert _notify_pipeline_of_registration(SAMPLE_RESULT, api_schema=SAMPLE_API_SCHEMA) is True

    payload = notify_mock.call_args.args[0]
    assert payload["api_schema"] == SAMPLE_API_SCHEMA


def test_notify_pipeline_omits_api_schema_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wrapper should preserve omission semantics for missing api_schema."""
    monkeypatch.setenv("HOKUSAI_API_KEY", "test-key")

    with patch.object(
        cli_module, "notify_pipeline_of_registration", return_value={}
    ) as notify_mock:
        assert _notify_pipeline_of_registration(SAMPLE_RESULT, api_schema=None) is True

    payload = notify_mock.call_args.args[0]
    assert "api_schema" not in payload


def test_notify_pipeline_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Normal notification should fail clearly without a user API key."""
    monkeypatch.delenv("HOKUSAI_API_KEY", raising=False)
    with pytest.raises(Exception) as exc_info:
        _notify_pipeline_of_registration(
            SAMPLE_RESULT, api_endpoint="https://registry.hokus.ai/api"
        )
    assert "HOKUSAI_API_KEY is required" in str(exc_info.value)


def test_notify_pipeline_surfaces_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-2xx responses should produce actionable failures."""
    monkeypatch.setenv("HOKUSAI_API_KEY", "test-key")

    with (
        patch.object(
            cli_module,
            "notify_pipeline_of_registration",
            side_effect=cli_module.NotificationError(
                "Pipeline failed with HTTP 502", status_code=502
            ),
        ),
        pytest.raises(Exception) as exc_info,
    ):
        _notify_pipeline_of_registration(SAMPLE_RESULT)

    assert "HTTP 502" in str(exc_info.value)


def test_notify_pipeline_surfaces_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Transport failures should mention connectivity."""
    monkeypatch.setenv("HOKUSAI_API_KEY", "test-key")

    with (
        patch.object(
            cli_module,
            "notify_pipeline_of_registration",
            side_effect=cli_module.NotificationError("could not connect to endpoint"),
        ),
        pytest.raises(Exception) as exc_info,
    ):
        _notify_pipeline_of_registration(SAMPLE_RESULT)

    assert "could not connect" in str(exc_info.value)


def test_register_cli_legacy_flag_uses_site_notification(tmp_path: Path) -> None:
    """The hidden fallback should still call the direct site webhook helper."""
    runner = CliRunner()
    artifact_path = tmp_path / "model.pkl"
    artifact_path.write_text("test-model")

    mock_registry = Mock()
    mock_registry.tracking_uri = "file:///tmp/mlruns"
    mock_registry._auth = Mock(api_key="test-key", api_endpoint="https://registry.hokus.ai/api")
    mock_registry.register_tokenized_model.return_value = dict(SAMPLE_RESULT)

    with (
        patch.dict(
            _REGISTER_GLOBALS,
            {
                "_load_model_registry": Mock(return_value=lambda **_: mock_registry),
                "_log_model_artifact": Mock(return_value="runs:/run-123/model"),
                "_derive_api_schema_from_uri": Mock(return_value=None),
            },
        ),
        patch.object(cli_module, "_notify_site_of_registration", return_value=True) as notify_site,
        patch.object(cli_module, "_notify_pipeline_of_registration") as notify_pipeline,
    ):
        result = runner.invoke(
            cli,
            [
                "model",
                "register",
                "--token-id",
                "HLEAD",
                "--model-path",
                str(artifact_path),
                "--metric",
                "accuracy",
                "--baseline",
                "0.10",
                "--use-legacy-webhook",
            ],
        )

    assert result.exit_code == 0, result.output
    notify_site.assert_called_once()
    notify_pipeline.assert_not_called()
