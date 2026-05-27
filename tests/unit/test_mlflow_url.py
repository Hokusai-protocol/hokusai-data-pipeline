"""Unit tests for canonical MLflow URL resolution."""

from __future__ import annotations

import logging

import pytest

from src.utils.mlflow_url import get_mlflow_url, reset_mlflow_url_warning_cache


@pytest.fixture(autouse=True)
def _reset_warning_cache() -> None:
    reset_mlflow_url_warning_cache()


def test_tracking_uri_wins_over_server_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://tracking.example:5000")
    monkeypatch.setenv("MLFLOW_SERVER_URL", "https://server.example:5000")

    assert get_mlflow_url() == "https://tracking.example:5000"


def test_server_url_used_when_tracking_uri_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.setenv("MLFLOW_SERVER_URL", "https://server.example:5000")

    assert get_mlflow_url() == "https://server.example:5000"


def test_empty_values_are_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "   ")
    monkeypatch.setenv("MLFLOW_SERVER_URL", "https://server.example:5000")

    assert get_mlflow_url() == "https://server.example:5000"


def test_missing_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.delenv("MLFLOW_SERVER_URL", raising=False)

    with pytest.raises(RuntimeError, match="MLFLOW_TRACKING_URI or MLFLOW_SERVER_URL"):
        get_mlflow_url()


def test_https_does_not_warn(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.example:5000")
    caplog.set_level(logging.WARNING)

    assert get_mlflow_url() == "https://mlflow.example:5000"
    assert not caplog.records


def test_http_warns_once_per_distinct_url(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://user:pass@mlflow.example:5000")
    caplog.set_level(logging.WARNING)

    assert get_mlflow_url() == "http://user:pass@mlflow.example:5000"
    assert get_mlflow_url() == "http://user:pass@mlflow.example:5000"

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "user:pass" not in warnings[0].message
    assert "http://mlflow.example:5000" in warnings[0].message


@pytest.mark.parametrize("invalid_url", ["file:///tmp/mlruns", "ftp://mlflow.example:21", "mlflow"])
def test_invalid_schemes_raise(monkeypatch: pytest.MonkeyPatch, invalid_url: str) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", invalid_url)

    with pytest.raises(ValueError):
        get_mlflow_url()
