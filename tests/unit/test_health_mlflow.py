"""Unit tests for MLflow SDK-path health endpoints.

The production path authenticates via SDK env such as `MLFLOW_TRACKING_TOKEN`;
these tests patch the probe so no live auth is required.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.health_mlflow import router
from src.utils.mlflow_health import MLflowRegistryHealthResult, check_mlflow_registry_sdk

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_health_check_mlflow_sdk_success_with_sample_model() -> None:
    result = MLflowRegistryHealthResult(
        status="ok",
        tracking_uri="https://mlflow.test.local:5000",
        latency_ms=12.34,
        sample_model="Technical Task Router",
    )

    with patch(
        "src.api.routes.health_mlflow.check_mlflow_registry_sdk",
        AsyncMock(return_value=result),
    ):
        response = client.get("/mlflow")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "tracking_uri": "https://mlflow.test.local:5000",
        "latency_ms": 12.34,
        "sample_model": "Technical Task Router",
    }


def test_health_check_mlflow_sdk_success_with_empty_registry() -> None:
    result = MLflowRegistryHealthResult(
        status="ok",
        tracking_uri="https://mlflow.test.local:5000",
        latency_ms=9.87,
        sample_model=None,
    )

    with patch(
        "src.api.routes.health_mlflow.check_mlflow_registry_sdk",
        AsyncMock(return_value=result),
    ):
        response = client.get("/mlflow")

    assert response.status_code == 200
    assert response.json()["sample_model"] is None


def test_health_check_mlflow_sdk_failure_returns_503() -> None:
    result = MLflowRegistryHealthResult(
        status="error",
        tracking_uri="https://mlflow.test.local:5000",
        latency_ms=44.21,
        error_type="MlflowException",
        error="registry down",
    )

    with patch(
        "src.api.routes.health_mlflow.check_mlflow_registry_sdk",
        AsyncMock(return_value=result),
    ):
        response = client.get("/mlflow")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "tracking_uri": "https://mlflow.test.local:5000",
        "latency_ms": 44.21,
        "sample_model": None,
        "error_type": "MlflowException",
        "error": "registry down",
    }


def test_detailed_and_connectivity_routes_alias_sdk_probe() -> None:
    result = MLflowRegistryHealthResult(
        status="ok",
        tracking_uri="https://mlflow.test.local:5000",
        latency_ms=10.0,
        sample_model="Technical Task Router",
    )

    with patch(
        "src.api.routes.health_mlflow.check_mlflow_registry_sdk",
        AsyncMock(return_value=result),
    ) as sdk_probe:
        detailed = client.get("/mlflow/detailed")
        connectivity = client.get("/mlflow/connectivity")

    assert detailed.status_code == 200
    assert connectivity.status_code == 200
    assert sdk_probe.await_count == 2


def test_sdk_probe_ssl_error_returns_503_with_ssl_error_type(monkeypatch) -> None:
    """mTLS misconfiguration raises SSLError → health endpoint returns 503 with SSLError type."""
    import ssl

    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.test.local:5000")

    client_mock = Mock()
    client_mock.search_registered_models.side_effect = ssl.SSLError("CERTIFICATE_VERIFY_FAILED")

    with patch("src.utils.mlflow_health.MlflowClient", return_value=client_mock):
        result = asyncio.run(check_mlflow_registry_sdk(timeout_seconds=5)).to_dict()

    assert result["status"] == "error"
    assert result["error_type"] == "SSLError"


def test_sdk_probe_sanitizes_cert_paths(monkeypatch) -> None:
    cert_path = "/tmp/secret/client.key"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.test.local:5000")
    monkeypatch.setenv("MLFLOW_CLIENT_KEY_PATH", cert_path)

    client_mock = Mock()
    client_mock.search_registered_models.side_effect = RuntimeError(f"bad cert at {cert_path}")

    with patch("src.utils.mlflow_health.MlflowClient", return_value=client_mock):
        result = asyncio.run(check_mlflow_registry_sdk(timeout_seconds=0.05)).to_dict()

    assert result["status"] == "error"
    assert result["error_type"] == "RuntimeError"
    assert cert_path not in result["error"]
    assert "<redacted-path>" in result["error"]


def test_sdk_probe_timeout_returns_bounded_latency(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.test.local:5000")

    def _slow_search(*args, **kwargs):
        del args, kwargs
        import time

        time.sleep(0.03)
        return []

    client_mock = Mock()
    client_mock.search_registered_models.side_effect = _slow_search

    with patch("src.utils.mlflow_health.MlflowClient", return_value=client_mock):
        result = asyncio.run(check_mlflow_registry_sdk(timeout_seconds=0.01)).to_dict()

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"
    assert result["latency_ms"] >= 10
