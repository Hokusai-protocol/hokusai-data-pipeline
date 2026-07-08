from __future__ import annotations

import json
import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from src.api.dependencies import get_contributor_logger
from src.api.endpoints import model_serving
from src.api.middleware.validation_logging import (
    classify_client_ip,
    redact_pydantic_errors,
    validation_422_exception_handler,
)
from src.middleware.auth import require_auth
from tests.unit.test_model_serving import FakeContributorLogger


def _build_app(*, register_validation_handler: bool) -> FastAPI:
    app = FastAPI()
    app.include_router(model_serving.router)
    app.dependency_overrides[require_auth] = lambda: {
        "user_id": "test-user",
        "api_key_id": "test-key",
        "scopes": ["model:read", "model:write"],
    }
    app.dependency_overrides[get_contributor_logger] = lambda: FakeContributorLogger()
    if register_validation_handler:
        app.add_exception_handler(RequestValidationError, validation_422_exception_handler)
    return app


def _flat_benchmark_payload(value: str = "technical_task_router_row/v1") -> dict[str, object]:
    return {
        "inputs": {
            "schema_version": value,
            "task_descriptor": {"task_type": "feature"},
            "allowed_models": ["fast-coder-v1"],
            "max_cost_usd": 0.5,
        }
    }


def _validation_records(caplog) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if getattr(record, "event_type", None) == "validation_422"
    ]


def test_outer_missing_inputs_emits_validation_422_log(caplog) -> None:
    client = TestClient(_build_app(register_validation_handler=True))

    with caplog.at_level(logging.WARNING):
        response = client.post("/api/v1/models/30/predict", json={})

    assert response.status_code == 422
    records = _validation_records(caplog)
    assert len(records) == 1
    record = records[0]
    message_payload = json.loads(record.getMessage())
    assert message_payload["event_type"] == "validation_422"
    assert message_payload["endpoint"] == "/api/v1/models/30/predict"
    assert message_payload["validation_errors"]
    assert message_payload["validation_error_summary"]
    assert record.event_type == "validation_422"
    assert record.endpoint == "/api/v1/models/30/predict"
    assert record.validation_errors
    assert all(sorted(error) == ["loc", "msg", "type"] for error in record.validation_errors)


def test_outer_422_response_body_unchanged() -> None:
    instrumented_client = TestClient(_build_app(register_validation_handler=True))
    default_client = TestClient(_build_app(register_validation_handler=False))

    instrumented_response = instrumented_client.post("/api/v1/models/30/predict", json={})
    default_response = default_client.post("/api/v1/models/30/predict", json={})

    assert instrumented_response.status_code == 422
    assert instrumented_response.json() == default_response.json()


def test_outer_422_includes_x_request_id_header() -> None:
    client = TestClient(_build_app(register_validation_handler=True))

    response = client.post("/api/v1/models/30/predict", json={})

    assert response.status_code == 422
    assert response.headers["X-Request-ID"]


def test_no_sensitive_values_in_log(caplog) -> None:
    client = TestClient(_build_app(register_validation_handler=True))
    payload = _flat_benchmark_payload("SENTINEL_xyzzy")

    with caplog.at_level(logging.WARNING):
        response = client.post("/api/v1/models/30/predict", json=payload)

    assert response.status_code == 422
    combined_log_output = "\n".join(
        [
            record.getMessage()
            + str(getattr(record, "validation_errors", ""))
            + str(getattr(record, "validation_error_summary", ""))
            for record in caplog.records
        ]
    )
    assert "SENTINEL_xyzzy" not in combined_log_output


def test_inner_model30_flat_payload_emits_validation_422_log(caplog) -> None:
    client = TestClient(_build_app(register_validation_handler=True))

    with caplog.at_level(logging.WARNING):
        response = client.post("/api/v1/models/30/predict", json=_flat_benchmark_payload())

    assert response.status_code == 422
    record = _validation_records(caplog)[0]
    message_payload = json.loads(record.getMessage())
    assert record.event_type == "validation_422"
    assert record.endpoint == "/api/v1/models/30/predict"
    assert record.validation_errors
    assert record.caller_fingerprint == {
        "user_id": "test-user",
        "api_key_id": "test-key",
        "user_agent": "testclient",
        "client_ip_class": "unknown",
    }
    assert message_payload["caller_fingerprint"] == record.caller_fingerprint
    assert message_payload["model_id"] == "30"


def test_inner_model30_422_has_x_request_id_header() -> None:
    client = TestClient(_build_app(register_validation_handler=True))

    response = client.post("/api/v1/models/30/predict", json=_flat_benchmark_payload())

    assert response.status_code == 422
    assert response.headers["X-Request-ID"]


def test_classify_client_ip() -> None:
    assert classify_client_ip("10.0.1.2") == "ipv4_private"
    assert classify_client_ip("172.16.0.1") == "ipv4_private"
    assert classify_client_ip("192.168.1.1") == "ipv4_private"
    assert classify_client_ip("8.8.8.8") == "ipv4_public"
    assert classify_client_ip("127.0.0.1") == "loopback"
    assert classify_client_ip(None) == "unknown"


def test_redact_pydantic_errors_strips_input_and_ctx() -> None:
    errors = [
        {
            "loc": ("inputs", "task"),
            "type": "missing",
            "msg": "Field required",
            "input": "SECRET",
            "ctx": {"limit": 5},
        }
    ]

    assert redact_pydantic_errors(errors) == [
        {
            "loc": ("inputs", "task"),
            "type": "missing",
            "msg": "Field required",
        }
    ]
