"""Unit tests for shared registration-event notification behavior."""

from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

SDK_SRC = Path(__file__).parent.parent.parent / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))
for _mod in list(sys.modules):
    if _mod == "hokusai" or _mod.startswith("hokusai."):
        del sys.modules[_mod]

from hokusai.core.notification import (  # noqa: E402
    build_pipeline_registration_event_url,
    build_registration_event_payload,
    notify_pipeline_of_registration,
    resolve_registration_event_api_endpoint,
)
import hokusai.core.registry as registry_module  # noqa: E402
from hokusai.core.registry import ModelRegistry, RegistryException  # noqa: E402
from hokusai.exceptions import NotificationError  # noqa: E402
from mlflow.exceptions import MlflowException  # noqa: E402


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


@pytest.fixture
def registry() -> ModelRegistry:
    """Create a registry with a mocked MLflow client."""
    registry = object.__new__(ModelRegistry)
    registry.client = Mock()
    registry._auth = Mock(api_key="test-key")
    registry.tracking_uri = "http://test:5000"
    yield registry


def test_notification_helpers_build_expected_urls() -> None:
    """Endpoint helpers should preserve the legacy CLI contract."""
    assert resolve_registration_event_api_endpoint("https://api.hokus.ai/api/") == (
        "https://api.hokus.ai/api"
    )
    assert build_pipeline_registration_event_url("https://api.hokus.ai/api") == (
        "https://api.hokus.ai/api/models/tokenized-registration-events"
    )
    assert build_pipeline_registration_event_url("https://registry.hokus.ai") == (
        "https://registry.hokus.ai/api/models/tokenized-registration-events"
    )


def test_notify_pipeline_posts_expected_payload() -> None:
    """Shared helper should use the same payload shape as the legacy CLI."""
    captured: dict[str, object] = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"event_emitted": true}'

    payload = build_registration_event_payload(SAMPLE_RESULT, model_uri="models:/hokusai-HLEAD/7")

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.data)
        captured["timeout"] = timeout
        return Response()

    with patch("hokusai.core.notification.urllib.request.urlopen", side_effect=fake_urlopen):
        response = notify_pipeline_of_registration(payload, api_key="test-key")

    assert captured["url"] == "https://api.hokus.ai/api/models/tokenized-registration-events"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["body"]["version"] == "7"
    assert captured["body"]["model_uri"] == "models:/hokusai-HLEAD/7"
    assert response == {"event_emitted": True}


def test_register_tokenized_model_success_emits_event(registry: ModelRegistry) -> None:
    """Successful registration should emit the site event by default."""
    mock_version = Mock()
    mock_version.version = "1"
    registry.client.create_model_version.return_value = mock_version
    registry.client.create_registered_model.return_value = None
    registry.client.set_model_version_tag.return_value = None

    with patch.object(
        registry_module,
        "notify_pipeline_of_registration",
        return_value={"event_emitted": True},
    ) as notify_mock:
        result = registry.register_tokenized_model(
            model_uri="runs:/abc123/model",
            model_name="MSG-AI",
            token_id="msg-ai",
            metric_name="reply_rate",
            baseline_value=0.1342,
        )

    notify_mock.assert_called_once()
    payload = notify_mock.call_args.args[0]
    assert payload["version"] == "1"
    assert payload["model_uri"] == "models:/MSG-AI/1"
    assert result["event_emitted"] is True
    assert result["site_status_update"] == "succeeded"


@pytest.mark.parametrize("status_code", [400, 503])
def test_register_tokenized_model_raises_notification_error_on_http_failure(
    registry: ModelRegistry, status_code: int
) -> None:
    """HTTP failures should surface as NotificationError after MLflow succeeds."""
    mock_version = Mock()
    mock_version.version = "1"
    registry.client.create_model_version.return_value = mock_version
    registry.client.set_model_version_tag.return_value = None

    with patch.object(
        registry_module,
        "notify_pipeline_of_registration",
        side_effect=NotificationError(
            "notification failed",
            status_code=status_code,
            response_body="bad response",
            mlflow_registered=True,
        ),
    ):
        with pytest.raises(NotificationError) as exc_info:
            registry.register_tokenized_model(
                model_uri="runs:/abc123/model",
                model_name="MSG-AI",
                token_id="msg-ai",
                metric_name="reply_rate",
                baseline_value=0.1342,
            )

    assert exc_info.value.status_code == status_code
    assert exc_info.value.mlflow_registered is True
    registry.client.create_model_version.assert_called_once()


def test_notify_pipeline_transport_failure_sets_empty_status_code() -> None:
    """Transport failures should not report an HTTP status code."""
    payload = build_registration_event_payload(SAMPLE_RESULT)

    with patch(
        "hokusai.core.notification.urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        with pytest.raises(NotificationError) as exc_info:
            notify_pipeline_of_registration(payload, api_key="test-key")

    assert exc_info.value.status_code is None
    assert exc_info.value.mlflow_registered is True


def test_register_tokenized_model_skips_notification_when_requested(
    registry: ModelRegistry,
) -> None:
    """notify_site=False should bypass the event emission step."""
    mock_version = Mock()
    mock_version.version = "1"
    registry.client.create_model_version.return_value = mock_version
    registry.client.set_model_version_tag.return_value = None

    with patch.object(registry_module, "notify_pipeline_of_registration") as notify_mock:
        result = registry.register_tokenized_model(
            model_uri="runs:/abc123/model",
            model_name="MSG-AI",
            token_id="msg-ai",
            metric_name="reply_rate",
            baseline_value=0.1342,
            notify_site=False,
        )

    notify_mock.assert_not_called()
    assert result["event_emitted"] is False
    assert result["site_status_update"] == "skipped"


def test_register_tokenized_model_best_effort_notification_logs_warning(
    registry: ModelRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    """best_effort_notification should return partial success instead of raising."""
    mock_version = Mock()
    mock_version.version = "1"
    registry.client.create_model_version.return_value = mock_version
    registry.client.set_model_version_tag.return_value = None

    with patch.object(
        registry_module,
        "notify_pipeline_of_registration",
        side_effect=NotificationError("notification failed", mlflow_registered=True),
    ):
        result = registry.register_tokenized_model(
            model_uri="runs:/abc123/model",
            model_name="MSG-AI",
            token_id="msg-ai",
            metric_name="reply_rate",
            baseline_value=0.1342,
            best_effort_notification=True,
        )

    assert "Registration event notification failed" in caplog.text
    assert result["event_emitted"] is False
    assert result["site_status_update"] == "failed"
    assert result["notification_error"] == "notification failed"


def test_register_tokenized_model_does_not_notify_when_mlflow_fails(
    registry: ModelRegistry,
) -> None:
    """Notification should not run if MLflow registration failed."""
    registry.client.create_model_version.side_effect = MlflowException("MLflow error")

    with patch.object(registry_module, "notify_pipeline_of_registration") as notify_mock:
        with pytest.raises(RegistryException, match="Failed to register tokenized model"):
            registry.register_tokenized_model(
                model_uri="runs:/abc123/model",
                model_name="MSG-AI",
                token_id="msg-ai",
                metric_name="reply_rate",
                baseline_value=0.1342,
            )

    notify_mock.assert_not_called()


def test_notify_pipeline_http_error_truncates_response_body() -> None:
    """HTTP error bodies should be captured with a bounded size."""
    payload = build_registration_event_payload(SAMPLE_RESULT)
    long_body = "x" * 1200

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url,
            400,
            "Bad Request",
            None,
            io.BytesIO(long_body.encode("utf-8")),
        )

    with patch("hokusai.core.notification.urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(NotificationError) as exc_info:
            notify_pipeline_of_registration(payload, api_key="test-key")

    assert exc_info.value.status_code == 400
    assert exc_info.value.response_body == long_body[:1000]
