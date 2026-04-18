"""Unit tests for CLI site notification after model registration."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from hokusai.cli import _notify_site_of_registration

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


class TestNotifySiteOfRegistration:
    """Tests for _notify_site_of_registration."""

    def test_sends_correct_event_type(self):
        """Payload must include event_type=model_registered."""
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            resp = MagicMock()
            resp.status = 200
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        with patch("hokusai.cli.urllib.request.urlopen", fake_urlopen):
            result = _notify_site_of_registration(
                SAMPLE_RESULT,
                site_webhook_url="https://hokus.ai/api/mlflow/registered",
                webhook_secret="secret",
            )

        assert result is True
        assert captured["body"]["event_type"] == "model_registered"

    def test_payload_contains_required_sdk_fields(self):
        """SDK format fields required by the site webhook schema are present."""
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            resp = MagicMock()
            resp.status = 200
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        with patch("hokusai.cli.urllib.request.urlopen", fake_urlopen):
            _notify_site_of_registration(
                SAMPLE_RESULT,
                site_webhook_url="https://hokus.ai/api/mlflow/registered",
                webhook_secret="secret",
            )

        body = captured["body"]
        for field in (
            "event_type",
            "token_id",
            "model_name",
            "model_version",
            "status",
            "timestamp",
        ):
            assert field in body, f"Missing field: {field}"

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
