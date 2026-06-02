from __future__ import annotations

import importlib
import sys
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.endpoints.model_30_adapter import Model30WarmupState
from src.api.utils.config import get_settings


@pytest.fixture
def health_module(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DB_PASSWORD", "test-password")
    get_settings.cache_clear()
    sys.modules.pop("src.api.routes.health", None)
    module = importlib.import_module("src.api.routes.health")
    yield module
    sys.modules.pop("src.api.routes.health", None)
    get_settings.cache_clear()


def _client(health_module) -> TestClient:
    app = FastAPI()
    app.include_router(health_module.router)
    return TestClient(app)


def test_ready_returns_503_when_model_30_warming(health_module) -> None:
    with (
        patch("src.api.routes.health.check_database_connection", return_value=(True, None)),
        patch(
            "src.api.routes.health.check_mlflow_connection",
            return_value=(True, None, {"health": {"status": "healthy"}}),
        ),
        patch(
            "src.utils.mlflow_config.get_mlflow_status",
            return_value={"connected": True, "circuit_breaker_state": "CLOSED", "error": None},
        ),
        patch.object(health_module.settings, "model_30_prewarm_enabled", True),
        patch(
            "src.api.routes.health.get_model_30_warmup_state",
            return_value={
                "warmed": False,
                "state": Model30WarmupState.WARMING.value,
                "warmed_at": None,
                "last_error": None,
                "duration_ms": None,
            },
        ),
    ):
        response = _client(health_module).get("/ready")

    assert response.status_code == 503
    assert response.json()["model_30"]["state"] == Model30WarmupState.WARMING.value


def test_ready_returns_200_when_model_30_warmed(health_module) -> None:
    with (
        patch("src.api.routes.health.check_database_connection", return_value=(True, None)),
        patch(
            "src.api.routes.health.check_mlflow_connection",
            return_value=(True, None, {"health": {"status": "healthy"}}),
        ),
        patch(
            "src.utils.mlflow_config.get_mlflow_status",
            return_value={"connected": True, "circuit_breaker_state": "CLOSED", "error": None},
        ),
        patch(
            "src.api.routes.health.get_model_30_warmup_state",
            return_value={
                "warmed": True,
                "state": Model30WarmupState.WARMED.value,
                "warmed_at": "2026-06-01T00:00:00+00:00",
                "last_error": None,
                "duration_ms": 100,
            },
        ),
    ):
        response = _client(health_module).get("/ready")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["warmup_duration_ms"] == 100


def test_ready_returns_degraded_when_model_30_failed(health_module) -> None:
    with (
        patch("src.api.routes.health.check_database_connection", return_value=(True, None)),
        patch(
            "src.api.routes.health.check_mlflow_connection",
            return_value=(True, None, {"health": {"status": "healthy"}}),
        ),
        patch(
            "src.utils.mlflow_config.get_mlflow_status",
            return_value={"connected": True, "circuit_breaker_state": "CLOSED", "error": None},
        ),
        patch(
            "src.api.routes.health.get_model_30_warmup_state",
            return_value={
                "warmed": False,
                "state": Model30WarmupState.FAILED.value,
                "warmed_at": None,
                "last_error": "boom",
                "duration_ms": 100,
            },
        ),
    ):
        response = _client(health_module).get("/ready")

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["degraded_mode"] is True


def test_ready_includes_model_30_in_checks(health_module) -> None:
    with (
        patch("src.api.routes.health.check_database_connection", return_value=(True, None)),
        patch(
            "src.api.routes.health.check_mlflow_connection",
            return_value=(True, None, {"health": {"status": "healthy"}}),
        ),
        patch(
            "src.utils.mlflow_config.get_mlflow_status",
            return_value={"connected": True, "circuit_breaker_state": "CLOSED", "error": None},
        ),
        patch(
            "src.api.routes.health.get_model_30_warmup_state",
            return_value={
                "warmed": True,
                "state": Model30WarmupState.WARMED.value,
                "warmed_at": "2026-06-01T00:00:00+00:00",
                "last_error": None,
                "duration_ms": 100,
            },
        ),
    ):
        response = _client(health_module).get("/ready")

    checks = response.json()["checks"]
    assert any(check["name"] == "model_30_warmed" for check in checks)
