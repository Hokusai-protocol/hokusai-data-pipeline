"""Unit tests for CLI site notification after model registration."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

# Ensure the worktree's local hokusai package takes precedence over any
# installed (editable) version that points to the main repo directory.
# Remove any cached modules so the fresh insert takes effect.
_WORKTREE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if _WORKTREE_SRC not in sys.path:
    sys.path.insert(0, _WORKTREE_SRC)
for _mod in list(sys.modules):
    if _mod == "hokusai" or _mod.startswith("hokusai."):
        del sys.modules[_mod]

from hokusai.cli import _notify_site_of_registration  # noqa: E402

SAMPLE_RESULT = {
    "model_name": "hokusai-MSG-AI",
    "version": "1",
    "token_id": "MSG-AI",
    "token_identifier": "MSG-AI",
    "proposal_identifier": "MSG-AI",
    "metric_name": "reply_rate",
    "baseline_value": 0.1342,
    "mlflow_run_id": "abc123",
    "status": "registered",
    "tags": {"hokusai_token_id": "MSG-AI"},
}

_SAMPLE_API_SCHEMA = {
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {"label": {"type": "string"}},
    },
}


def _fake_urlopen_ok(captured: dict):
    """Return a fake urlopen that stores the request body and simulates HTTP 200."""

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data)
        captured["headers"] = dict(req.headers)
        resp = MagicMock()
        resp.status = 200
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    return fake_urlopen


class TestNotifySiteOfRegistration:
    """Tests for _notify_site_of_registration."""

    def test_sends_correct_event_type(self):
        """Payload must include event_type=model_registered."""
        captured: dict = {}

        with patch("hokusai.cli.urllib.request.urlopen", _fake_urlopen_ok(captured)):
            result = _notify_site_of_registration(
                SAMPLE_RESULT,
                site_webhook_url="https://hokus.ai/api/mlflow/registered",
                webhook_secret="secret",
            )

        assert result is True
        assert captured["body"]["event_type"] == "model_registered"

    def test_payload_original_mlflow_format(self):
        """Payload uses the original MLflow event format so the site parser picks up api_schema."""
        captured: dict = {}

        with patch("hokusai.cli.urllib.request.urlopen", _fake_urlopen_ok(captured)):
            _notify_site_of_registration(
                SAMPLE_RESULT,
                site_webhook_url="https://hokus.ai/api/mlflow/registered",
                webhook_secret="secret",
            )

        body = captured["body"]
        # Required top-level fields
        for field in ("event_type", "model", "timestamp", "source"):
            assert field in body, f"Missing top-level field: {field}"

        assert body["source"] == "mlflow"
        assert body["event_type"] == "model_registered"

        # Required model sub-fields
        model = body["model"]
        for field in ("id", "name", "status", "version"):
            assert field in model, f"Missing model.{field}"

        assert model["id"] == "msg-ai"  # token_id.lower()
        assert model["name"] == SAMPLE_RESULT["model_name"]
        assert model["status"] == "registered"

    def test_no_top_level_token_id(self):
        """token_id must NOT appear at the top level (forces original-format parser on site)."""
        captured: dict = {}

        with patch("hokusai.cli.urllib.request.urlopen", _fake_urlopen_ok(captured)):
            _notify_site_of_registration(
                SAMPLE_RESULT,
                site_webhook_url="https://hokus.ai/api/mlflow/registered",
                webhook_secret="secret",
            )

        assert "token_id" not in captured["body"]

    def test_api_schema_included_when_provided(self):
        """api_schema in the model dict when explicitly provided."""
        captured: dict = {}

        with patch("hokusai.cli.urllib.request.urlopen", _fake_urlopen_ok(captured)):
            _notify_site_of_registration(
                SAMPLE_RESULT,
                site_webhook_url="https://hokus.ai/api/mlflow/registered",
                webhook_secret="secret",
                api_schema=_SAMPLE_API_SCHEMA,
            )

        assert captured["body"]["model"]["api_schema"] == _SAMPLE_API_SCHEMA

    def test_api_schema_absent_when_none(self):
        """api_schema key must be absent from model dict when not provided."""
        captured: dict = {}

        with patch("hokusai.cli.urllib.request.urlopen", _fake_urlopen_ok(captured)):
            _notify_site_of_registration(
                SAMPLE_RESULT,
                site_webhook_url="https://hokus.ai/api/mlflow/registered",
                webhook_secret="secret",
            )

        assert "api_schema" not in captured["body"]["model"]

    def test_mlflow_run_id_in_model_dict(self):
        """run_id from result appears in model.run_id."""
        captured: dict = {}

        with patch("hokusai.cli.urllib.request.urlopen", _fake_urlopen_ok(captured)):
            _notify_site_of_registration(
                SAMPLE_RESULT,
                site_webhook_url="https://hokus.ai/api/mlflow/registered",
                webhook_secret="secret",
            )

        assert captured["body"]["model"]["run_id"] == SAMPLE_RESULT["mlflow_run_id"]

    def test_hmac_signature_header_is_set(self):
        """X-Hokusai-Signature header is added when a secret is provided."""
        captured_headers: dict = {}

        def fake_urlopen(req, timeout=None):
            captured_headers.update(req.headers)
            resp = MagicMock()
            resp.status = 200
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        secret = "mysecret"
        with patch("hokusai.cli.urllib.request.urlopen", fake_urlopen):
            _notify_site_of_registration(
                SAMPLE_RESULT,
                site_webhook_url="https://hokus.ai/api/mlflow/registered",
                webhook_secret=secret,
            )

        sig_header = captured_headers.get("X-hokusai-signature")
        assert sig_header is not None
        assert sig_header.startswith("sha256=")

    def test_returns_false_on_http_error(self):
        """Non-2xx responses are treated as failures (non-fatal)."""
        import urllib.error

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                url="https://hokus.ai/api/mlflow/registered",
                code=401,
                msg="Unauthorized",
                hdrs=None,
                fp=None,
            )

        with patch("hokusai.cli.urllib.request.urlopen", fake_urlopen):
            result = _notify_site_of_registration(
                SAMPLE_RESULT,
                site_webhook_url="https://hokus.ai/api/mlflow/registered",
                webhook_secret="secret",
            )

        assert result is False

    def test_returns_false_on_connection_error(self):
        """Network errors are swallowed and reported as failure."""

        def fake_urlopen(req, timeout=None):
            raise OSError("Connection refused")

        with patch("hokusai.cli.urllib.request.urlopen", fake_urlopen):
            result = _notify_site_of_registration(
                SAMPLE_RESULT,
                site_webhook_url="https://hokus.ai/api/mlflow/registered",
                webhook_secret="secret",
            )

        assert result is False

    def test_uses_env_var_webhook_url(self, monkeypatch):
        """HOKUSAI_SITE_WEBHOOK_URL env var is used when no explicit URL is given."""
        monkeypatch.setenv("HOKUSAI_SITE_WEBHOOK_URL", "https://custom.hokus.ai/hook")
        monkeypatch.setenv("HOKUSAI_SITE_WEBHOOK_SECRET", "env-secret")
        captured_url: list[str] = []

        def fake_urlopen(req, timeout=None):
            captured_url.append(req.full_url)
            resp = MagicMock()
            resp.status = 200
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        with patch("hokusai.cli.urllib.request.urlopen", fake_urlopen):
            _notify_site_of_registration(SAMPLE_RESULT)

        assert captured_url[0] == "https://custom.hokus.ai/hook"
