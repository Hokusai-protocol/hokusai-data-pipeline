"""Tests for Sentry initialization and debug route registration."""

from __future__ import annotations

import importlib
import sys
from asyncio import run
from unittest.mock import patch

import pytest
from fastapi.routing import APIRoute


def _load_api_main(monkeypatch: pytest.MonkeyPatch, **env: str | None):
    monkeypatch.setenv("MLFLOW_SERVER_URL", "https://mlflow.test.local:5000")
    monkeypatch.setenv("MLFLOW_TRACKING_TOKEN", "test-token")
    monkeypatch.setenv("DB_PASSWORD", "test-password")

    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)

    sys.modules.pop("src.api.main", None)
    module = importlib.import_module("src.api.main")
    return module


def _get_route(module, path: str) -> APIRoute | None:
    for route in module.app.routes:
        if isinstance(route, APIRoute) and route.path == path:
            return route
    return None


def test_api_imports_without_sentry_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing the API should still work when Sentry is disabled."""
    module = _load_api_main(monkeypatch, SENTRY_DSN=None)

    assert module.app.title == "Hokusai MLOps API"


def test_init_sentry_uses_expected_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured Sentry values should be forwarded to sentry_sdk.init."""
    module = _load_api_main(
        monkeypatch,
        SENTRY_DSN="https://examplePublicKey@o0.ingest.sentry.io/0",
        SENTRY_TRACES_SAMPLE_RATE="0.25",
        SENTRY_RELEASE="hokusai-data-pipeline@test",
        ENVIRONMENT="staging",
    )

    with patch.object(module.sentry_sdk, "init") as init_mock:
        module._init_sentry()

    init_mock.assert_called_once()
    kwargs = init_mock.call_args.kwargs
    assert kwargs["dsn"] == "https://examplePublicKey@o0.ingest.sentry.io/0"
    assert kwargs["environment"] == "staging"
    assert kwargs["traces_sample_rate"] == 0.25
    assert kwargs["profiles_sample_rate"] == 0.0
    assert kwargs["send_default_pii"] is True
    assert kwargs["release"] == "hokusai-data-pipeline@test"
    assert kwargs["before_send"] is module._scrub_sensitive_headers


def test_init_sentry_logs_and_does_not_raise_on_sdk_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sentry init failures must not break API startup."""
    module = _load_api_main(
        monkeypatch,
        SENTRY_DSN="https://examplePublicKey@o0.ingest.sentry.io/0",
    )

    with (
        patch.object(module.sentry_sdk, "init", side_effect=RuntimeError("boom")),
        patch.object(module.logger, "exception") as logger_mock,
    ):
        module._init_sentry()

    logger_mock.assert_called_once_with("Failed to initialize Sentry")


def test_sentry_debug_route_not_registered_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production should not expose the debug endpoint by default."""
    module = _load_api_main(
        monkeypatch,
        ENVIRONMENT="production",
        SENTRY_DEBUG_ENABLED=None,
        SENTRY_DSN=None,
    )

    assert _get_route(module, "/sentry-debug") is None


def test_sentry_debug_route_can_be_enabled_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The debug endpoint can be force-enabled for verification."""
    module = _load_api_main(
        monkeypatch,
        ENVIRONMENT="production",
        SENTRY_DEBUG_ENABLED="true",
        SENTRY_DSN=None,
    )

    route = _get_route(module, "/sentry-debug")

    assert route is not None
    with pytest.raises(ZeroDivisionError):
        run(route.endpoint())


def test_scrub_sensitive_headers_filters_dict_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dict-shaped request headers should have credential fields filtered."""
    module = _load_api_main(monkeypatch, SENTRY_DSN=None)

    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer secret-token",
                "Cookie": "session=abc",
                "X-Api-Key": "live-key",
                "User-Agent": "pytest",
            },
        },
    }

    result = module._scrub_sensitive_headers(event, {})

    headers = result["request"]["headers"]
    assert headers["Authorization"] == "[Filtered]"
    assert headers["Cookie"] == "[Filtered]"
    assert headers["X-Api-Key"] == "[Filtered]"
    assert headers["User-Agent"] == "pytest"


def test_scrub_sensitive_headers_filters_list_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """List-shaped request headers should also have credential fields filtered."""
    module = _load_api_main(monkeypatch, SENTRY_DSN=None)

    event = {
        "request": {
            "headers": [
                ["authorization", "Bearer secret-token"],
                ["user-agent", "pytest"],
            ],
        },
    }

    result = module._scrub_sensitive_headers(event, {})

    headers = result["request"]["headers"]
    assert headers[0] == ["authorization", "[Filtered]"]
    assert headers[1] == ["user-agent", "pytest"]


def test_scrub_sensitive_headers_handles_missing_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Events without request data should pass through untouched."""
    module = _load_api_main(monkeypatch, SENTRY_DSN=None)

    event: dict = {"message": "boom"}

    result = module._scrub_sensitive_headers(event, {})

    assert result is event
