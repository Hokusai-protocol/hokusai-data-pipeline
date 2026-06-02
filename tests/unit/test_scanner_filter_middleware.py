from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI, Query
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from src.api.middleware.scanner_filter import ScannerFilterMiddleware
from src.api.middleware.validation_logging import validation_422_exception_handler
from src.api.utils.config import get_settings


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DB_PASSWORD", "test-password")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _register_allowlist_routes(app: FastAPI) -> None:
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/__ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/2.0/mlflow/experiments/list")
    async def mlflow_list() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/docs")
    async def docs() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/openapi.json")
    async def openapi() -> dict[str, str]:
        return {"status": "ok"}


def _register_probe_routes(app: FastAPI) -> None:
    @app.get("/custom-scanner-path")
    async def custom_scanner_path() -> tuple[str, int]:
        return ("teapot", 418)

    @app.get("/foo")
    async def foo() -> tuple[str, int]:
        return ("teapot", 418)

    @app.get("/bar")
    async def bar() -> tuple[str, int]:
        return ("teapot", 418)

    @app.get("/mgmt/tm/util/bash")
    async def mgmt_probe() -> tuple[str, int]:
        return ("teapot", 418)

    @app.get("/login.action")
    async def login_action(required: int = Query(...)) -> dict[str, int]:
        return {"required": required}

    @app.post("/api/jsonws/invoke")
    async def jsonws_invoke() -> tuple[str, int]:
        return ("teapot", 418)


def _build_app(*, register_validation_handler: bool = False) -> FastAPI:
    app = FastAPI()
    _register_allowlist_routes(app)
    _register_probe_routes(app)

    if register_validation_handler:
        app.add_exception_handler(RequestValidationError, validation_422_exception_handler)

    app.add_middleware(ScannerFilterMiddleware)
    return app


def test_seed_scanner_paths_rejected() -> None:
    client = TestClient(_build_app())

    for method, path in [
        ("get", "/mgmt/tm/util/bash"),
        ("get", "/ui/login"),
        ("get", "/login.action"),
        ("post", "/api/jsonws/invoke"),
    ]:
        response = getattr(client, method)(path)
        assert response.status_code == 404
        assert response.content == b""
        assert response.headers["Cache-Control"] == "no-store"


def test_query_string_preserved_suppression() -> None:
    client = TestClient(_build_app())

    response = client.get("/login.action?cmd=whoami")

    assert response.status_code == 404
    assert response.content == b""


def test_case_insensitive_path_match() -> None:
    client = TestClient(_build_app())

    response = client.get("/Login.Action")

    assert response.status_code == 404


def test_allowlist_precedence() -> None:
    client = TestClient(_build_app())

    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
    assert client.get("/metrics").status_code == 200
    assert client.get("/api/v1/__ping").status_code == 200
    assert client.post("/api/2.0/mlflow/experiments/list").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_overlap_deny_and_allowlist() -> None:
    client = TestClient(_build_app())

    assert client.post("/api/jsonws/invoke").status_code == 404
    assert client.get("/api/v1/foo").status_code == 404
    assert client.get("/api/v1/__ping").status_code == 200


def test_disable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCANNER_FILTER_ENABLED", "false")
    get_settings.cache_clear()
    client = TestClient(_build_app())

    response = client.get("/mgmt/tm/util/bash")

    assert response.status_code == 200
    assert response.json() == ["teapot", 418]


def test_extra_patterns_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCANNER_FILTER_EXTRA_PATTERNS", " /custom-scanner-path , /foo , /bar ")
    get_settings.cache_clear()
    client = TestClient(_build_app())

    assert client.get("/custom-scanner-path").status_code == 404
    assert client.get("/foo").status_code == 404
    assert client.get("/bar").status_code == 404


def test_structured_log_emission(caplog) -> None:
    client = TestClient(_build_app())

    with caplog.at_level(logging.INFO):
        response = client.get(
            "/ui/login",
            headers={
                "X-Forwarded-For": "10.0.102.142, 10.0.0.1",
                "User-Agent": "ScannerProbe/1.0",
                "Authorization": "Bearer sentinel-secret",
            },
        )

    assert response.status_code == 404
    records = [record for record in caplog.records if record.msg == "scanner_request_rejected"]
    assert len(records) == 1
    record = records[0]
    assert record.event_type == "scanner_request_rejected"
    assert record.path == "/ui/login"
    assert record.method == "GET"
    assert record.client_ip == "10.0.102.142"
    assert record.user_agent == "ScannerProbe/1.0"
    assert "sentinel-secret" not in str(record.__dict__)


def test_client_ip_fallback_without_forwarded_for(caplog) -> None:
    client = TestClient(_build_app())

    with caplog.at_level(logging.INFO):
        response = client.get("/ui/login")

    assert response.status_code == 404
    record = next(record for record in caplog.records if record.msg == "scanner_request_rejected")
    assert record.client_ip == "testclient"


def test_validation_logging_cooperation(caplog) -> None:
    client = TestClient(_build_app(register_validation_handler=True))

    with caplog.at_level(logging.INFO):
        response = client.get("/login.action")

    assert response.status_code == 404
    scanner_records = [
        record
        for record in caplog.records
        if getattr(record, "event_type", None) == "scanner_request_rejected"
    ]
    validation_records = [
        record
        for record in caplog.records
        if getattr(record, "event_type", None) == "validation_422"
    ]
    assert len(scanner_records) == 1
    assert validation_records == []
