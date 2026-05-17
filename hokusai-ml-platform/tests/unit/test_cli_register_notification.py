"""Tests for CLI notification routing through the data pipeline API."""

from __future__ import annotations

import json
import sys
import urllib.error
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


def test_notify_pipeline_posts_expected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """The helper should authenticate with the user API key and hit /api/models."""
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

    monkeypatch.setenv("HOKUSAI_API_KEY", "test-key")

    with patch.object(cli_module.urllib.request, "urlopen", side_effect=fake_urlopen):
        assert _notify_pipeline_of_registration(SAMPLE_RESULT) is True

    assert captured["url"] == "https://registry.hokus.ai/api/models/tokenized-registration-events"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["body"]["model_name"] == "hokusai-HLEAD"
    assert captured["body"]["proposal_identifier"] == "HLEAD"
    assert captured["body"]["model_uri"] == "models:/hokusai-HLEAD/7"


def test_notify_pipeline_uses_non_api_base_when_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bare domains should still route to /api/models."""
    captured_urls: list[str] = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req, timeout=None):
        captured_urls.append(req.full_url)
        return Response()

    monkeypatch.setenv("HOKUSAI_API_KEY", "test-key")

    with patch.object(cli_module.urllib.request, "urlopen", side_effect=fake_urlopen):
        _notify_pipeline_of_registration(SAMPLE_RESULT, api_endpoint="https://registry.hokus.ai")

    assert captured_urls == ["https://registry.hokus.ai/api/models/tokenized-registration-events"]


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

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            url=req.full_url,
            code=502,
            msg="Bad Gateway",
            hdrs=None,
            fp=None,
        )

    with (
        patch.object(cli_module.urllib.request, "urlopen", side_effect=fake_urlopen),
        pytest.raises(Exception) as exc_info,
    ):
        _notify_pipeline_of_registration(SAMPLE_RESULT)

    assert "HTTP 502" in str(exc_info.value)


def test_notify_pipeline_surfaces_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Transport failures should mention connectivity."""
    monkeypatch.setenv("HOKUSAI_API_KEY", "test-key")

    with (
        patch.object(
            cli_module.urllib.request,
            "urlopen",
            side_effect=urllib.error.URLError("connection refused"),
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
