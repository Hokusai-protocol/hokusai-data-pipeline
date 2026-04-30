"""Integration tests for benchmark spec API routes."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from fastapi import Request
from fastapi.testclient import TestClient
from starlette.responses import Response

from src.api.dependencies import get_audit_logger, get_benchmark_spec_service
from src.api.main import app
from src.api.services.governance.audit_logger import AuditLogger
from src.api.services.governance.benchmark_specs import BenchmarkSpecService

VALID_CREATE = {
    "model_id": "integ-model-a",
    "provider": "hokusai",
    "dataset_reference": "s3://bucket/dataset.csv",
    "eval_split": "test",
    "target_column": "label",
    "input_columns": ["feature_a"],
    "metric_name": "accuracy",
    "metric_direction": "higher_is_better",
}

EVAL_SPEC = {
    "primary_metric": {"name": "accuracy", "direction": "higher_is_better"},
    "secondary_metrics": [],
    "guardrails": [],
    "min_examples": 100,
}


async def _passthrough_middleware_dispatch(self: Any, request: Request, call_next: Any) -> Response:
    request.state.user_id = "test-user"
    request.state.api_key_id = "key-1"
    request.state.service_id = "test"
    request.state.scopes = []
    request.state.rate_limit_per_hour = None
    return await call_next(request)


def _build_integration_client() -> tuple[TestClient, BenchmarkSpecService]:
    service = BenchmarkSpecService()
    audit = AuditLogger()
    app.dependency_overrides[get_benchmark_spec_service] = lambda: service
    app.dependency_overrides[get_audit_logger] = lambda: audit
    return TestClient(app, raise_server_exceptions=False), service


def _cleanup() -> None:
    app.dependency_overrides.clear()


@patch(
    "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
    _passthrough_middleware_dispatch,
)
def test_create_and_get_with_eval_spec() -> None:
    client, _ = _build_integration_client()
    try:
        payload = {**VALID_CREATE, "eval_spec": EVAL_SPEC}
        resp = client.post("/api/v1/benchmarks", json=payload)
        assert resp.status_code == 201
        created = resp.json()
        assert created["eval_spec"]["primary_metric"]["name"] == "accuracy"
        assert created["eval_spec"]["min_examples"] == 100

        get_resp = client.get(f"/api/v1/benchmarks/{created['spec_id']}")
        assert get_resp.status_code == 200
        fetched = get_resp.json()
        assert fetched["eval_spec"]["primary_metric"]["name"] == "accuracy"
        assert fetched["eval_spec"]["min_examples"] == 100
    finally:
        _cleanup()


@patch(
    "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
    _passthrough_middleware_dispatch,
)
def test_legacy_spec_remains_readable() -> None:
    client, _ = _build_integration_client()
    try:
        resp = client.post("/api/v1/benchmarks", json=VALID_CREATE)
        assert resp.status_code == 201
        created = resp.json()

        assert created["eval_spec"] is not None
        assert created["eval_spec"]["primary_metric"]["name"] == "accuracy"
        assert created["eval_spec"]["primary_metric"]["direction"] == "higher_is_better"
        assert created["eval_spec"]["secondary_metrics"] == []
        assert created["eval_spec"]["guardrails"] == []

        get_resp = client.get(f"/api/v1/benchmarks/{created['spec_id']}")
        assert get_resp.status_code == 200
        fetched = get_resp.json()
        assert fetched["eval_spec"]["primary_metric"]["name"] == "accuracy"
    finally:
        _cleanup()


@patch(
    "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
    _passthrough_middleware_dispatch,
)
def test_create_and_get_benchmark_spec() -> None:
    client, _ = _build_integration_client()
    try:
        resp = client.post("/api/v1/benchmarks", json=VALID_CREATE)
        assert resp.status_code == 201
        created = resp.json()

        get_resp = client.get(f"/api/v1/benchmarks/{created['spec_id']}")
        assert get_resp.status_code == 200
        fetched = get_resp.json()
        assert fetched["spec_id"] == created["spec_id"]
        assert fetched["metric_name"] == "accuracy"
    finally:
        _cleanup()
