"""Unit tests for benchmark spec CRUD API routes."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from fastapi import Request
from fastapi.testclient import TestClient
from starlette.responses import Response

from src.api.main import app
from src.api.services.governance.audit_logger import AuditLogger
from src.api.services.governance.benchmark_specs import (
    BenchmarkSpecConflictError,
    BenchmarkSpecService,
)
from src.middleware.auth import require_auth

VALID_AUTH = {"user_id": "test-user", "api_key_id": "key-1", "scopes": []}

SAMPLE_SPEC = {
    "spec_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "provider": "hokusai",
    "model_id": "model-123",
    "dataset_id": "s3://bucket/dataset.csv",
    "dataset_version": "latest",
    "eval_split": "test",
    "metric_name": "accuracy",
    "metric_direction": "higher_is_better",
    "tiebreak_rules": None,
    "input_schema": {"columns": ["text"]},
    "output_schema": {"target_column": "label"},
    "eval_container_digest": None,
    "baseline_value": None,
    "eval_spec": None,
    "created_at": "2024-01-01T00:00:00+00:00",
    "is_active": True,
}

EVAL_SPEC_PAYLOAD = {
    "primary_metric": {"name": "accuracy", "direction": "higher_is_better"},
    "secondary_metrics": [],
    "guardrails": [],
    "min_examples": 200,
}

CREATE_PAYLOAD = {
    "model_id": "model-123",
    "provider": "hokusai",
    "dataset_reference": "s3://bucket/dataset.csv",
    "eval_split": "test",
    "target_column": "label",
    "input_columns": ["text"],
    "metric_name": "accuracy",
    "metric_direction": "higher_is_better",
}


async def _passthrough_middleware_dispatch(self: Any, request: Request, call_next: Any) -> Response:
    """Middleware dispatch that bypasses auth and sets user state."""
    request.state.user_id = "test-user"
    request.state.api_key_id = "key-1"
    request.state.service_id = "test"
    request.state.scopes = []
    request.state.rate_limit_per_hour = None
    return await call_next(request)


def _make_authed_client() -> tuple[TestClient, MagicMock, MagicMock]:
    """Create a test client with auth bypassed and mocked service/audit deps."""
    mock_service = MagicMock(spec=BenchmarkSpecService)
    mock_audit = MagicMock(spec=AuditLogger)

    from src.api.dependencies import get_audit_logger, get_benchmark_spec_service

    app.dependency_overrides[get_benchmark_spec_service] = lambda: mock_service
    app.dependency_overrides[get_audit_logger] = lambda: mock_audit

    return TestClient(app, raise_server_exceptions=False), mock_service, mock_audit


def _cleanup_overrides() -> None:
    app.dependency_overrides.clear()


class TestCreateBenchmarkSpec:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_create_returns_201(self) -> None:
        client, svc, audit = _make_authed_client()
        try:
            svc.register_spec.return_value = SAMPLE_SPEC
            resp = client.post("/api/v1/benchmarks", json=CREATE_PAYLOAD)
            assert resp.status_code == 201
            body = resp.json()
            assert body["spec_id"] == SAMPLE_SPEC["spec_id"]
            assert body["model_id"] == "model-123"
            assert body["dataset_reference"] == "s3://bucket/dataset.csv"
            assert body["input_columns"] == ["text"]
            assert body["target_column"] == "label"
            audit.log.assert_called_once()
            assert audit.log.call_args.kwargs["action"] == "benchmark_spec.created"
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_create_conflict_returns_409(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.register_spec.side_effect = BenchmarkSpecConflictError("duplicate")
            resp = client.post("/api/v1/benchmarks", json=CREATE_PAYLOAD)
            assert resp.status_code == 409
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_create_missing_field_returns_422(self) -> None:
        client, _, _ = _make_authed_client()
        try:
            payload = {k: v for k, v in CREATE_PAYLOAD.items() if k != "model_id"}
            resp = client.post("/api/v1/benchmarks", json=payload)
            assert resp.status_code == 422
        finally:
            _cleanup_overrides()


class TestGetBenchmarkSpec:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_get_returns_200(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.get_spec.return_value = SAMPLE_SPEC
            resp = client.get(f"/api/v1/benchmarks/{SAMPLE_SPEC['spec_id']}")
            assert resp.status_code == 200
            assert resp.json()["spec_id"] == SAMPLE_SPEC["spec_id"]
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_get_not_found_returns_404(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.get_spec.return_value = None
            resp = client.get("/api/v1/benchmarks/nonexistent-id")
            assert resp.status_code == 404
            assert resp.json()["detail"] == "BenchmarkSpec not found"
        finally:
            _cleanup_overrides()


class TestListBenchmarkSpecs:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_list_returns_paginated(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.list_specs_paginated.return_value = ([SAMPLE_SPEC], 1)
            resp = client.get("/api/v1/benchmarks?model_id=model-123&page=1&page_size=10")
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 1
            assert body["page"] == 1
            assert body["page_size"] == 10
            assert len(body["items"]) == 1
            svc.list_specs_paginated.assert_called_once_with(
                model_id="model-123", page=1, page_size=10
            )
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_list_empty(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.list_specs_paginated.return_value = ([], 0)
            resp = client.get("/api/v1/benchmarks?model_id=no-specs")
            assert resp.status_code == 200
            body = resp.json()
            assert body["items"] == []
            assert body["total"] == 0
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_list_without_model_id(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.list_specs_paginated.return_value = ([SAMPLE_SPEC], 1)
            resp = client.get("/api/v1/benchmarks")
            assert resp.status_code == 200
            svc.list_specs_paginated.assert_called_once_with(model_id=None, page=1, page_size=20)
        finally:
            _cleanup_overrides()


class TestUpdateBenchmarkSpec:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_update_returns_200(self) -> None:
        updated = {**SAMPLE_SPEC, "dataset_id": "s3://bucket/new-dataset.csv"}
        client, svc, audit = _make_authed_client()
        try:
            svc.update_spec_fields.return_value = updated
            resp = client.put(
                f"/api/v1/benchmarks/{SAMPLE_SPEC['spec_id']}",
                json={"dataset_reference": "s3://bucket/new-dataset.csv"},
            )
            assert resp.status_code == 200
            assert resp.json()["dataset_reference"] == "s3://bucket/new-dataset.csv"
            audit.log.assert_called_once()
            assert audit.log.call_args.kwargs["action"] == "benchmark_spec.updated"
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_update_not_found_returns_404(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.update_spec_fields.return_value = None
            resp = client.put(
                "/api/v1/benchmarks/nonexistent-id",
                json={"dataset_reference": "new-ref"},
            )
            assert resp.status_code == 404
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_update_empty_body_returns_200(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.update_spec_fields.return_value = SAMPLE_SPEC
            resp = client.put(f"/api/v1/benchmarks/{SAMPLE_SPEC['spec_id']}", json={})
            assert resp.status_code == 200
        finally:
            _cleanup_overrides()


class TestDeleteBenchmarkSpec:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_delete_returns_204(self) -> None:
        client, svc, audit = _make_authed_client()
        try:
            svc.delete_spec.return_value = True
            resp = client.delete(f"/api/v1/benchmarks/{SAMPLE_SPEC['spec_id']}")
            assert resp.status_code == 204
            audit.log.assert_called_once()
            assert audit.log.call_args.kwargs["action"] == "benchmark_spec.deleted"
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_delete_not_found_returns_404(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.delete_spec.return_value = False
            resp = client.delete("/api/v1/benchmarks/nonexistent-id")
            assert resp.status_code == 404
        finally:
            _cleanup_overrides()


class TestBaselineValue:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_create_with_baseline_value_roundtrip(self) -> None:
        spec_with_baseline = {**SAMPLE_SPEC, "baseline_value": 0.85}
        client, svc, _ = _make_authed_client()
        try:
            svc.register_spec.return_value = spec_with_baseline
            payload = {**CREATE_PAYLOAD, "baseline_value": 0.85}
            resp = client.post("/api/v1/benchmarks", json=payload)
            assert resp.status_code == 201
            assert resp.json()["baseline_value"] == 0.85
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_create_without_baseline_value_returns_null(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.register_spec.return_value = SAMPLE_SPEC
            resp = client.post("/api/v1/benchmarks", json=CREATE_PAYLOAD)
            assert resp.status_code == 201
            assert resp.json()["baseline_value"] is None
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_update_baseline_value(self) -> None:
        updated = {**SAMPLE_SPEC, "baseline_value": 0.9}
        client, svc, _ = _make_authed_client()
        try:
            svc.update_spec_fields.return_value = updated
            resp = client.put(
                f"/api/v1/benchmarks/{SAMPLE_SPEC['spec_id']}",
                json={"baseline_value": 0.9},
            )
            assert resp.status_code == 200
            assert resp.json()["baseline_value"] == 0.9
        finally:
            _cleanup_overrides()

    def test_create_schema_rejects_infinite_baseline_value(self) -> None:
        import math

        import pytest
        from pydantic import ValidationError

        from src.api.schemas.benchmark_spec import BenchmarkSpecCreate

        with pytest.raises(ValidationError, match="finite"):
            BenchmarkSpecCreate(
                model_id="m",
                provider="hokusai",
                dataset_reference="s3://b/f.csv",
                eval_split="test",
                target_column="label",
                input_columns=[],
                metric_name="accuracy",
                metric_direction="higher_is_better",
                baseline_value=math.inf,
            )


class TestEvalSpecRoutes:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_create_with_eval_spec_round_trip(self) -> None:
        spec_with_eval = {**SAMPLE_SPEC, "eval_spec": EVAL_SPEC_PAYLOAD}
        client, svc, _ = _make_authed_client()
        try:
            svc.register_spec.return_value = spec_with_eval
            payload = {**CREATE_PAYLOAD, "eval_spec": EVAL_SPEC_PAYLOAD}
            resp = client.post("/api/v1/benchmarks", json=payload)
            assert resp.status_code == 201
            body = resp.json()
            assert body["eval_spec"]["primary_metric"]["name"] == "accuracy"
            assert body["eval_spec"]["min_examples"] == 200
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_create_without_eval_spec_synthesizes_legacy_response(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.register_spec.return_value = SAMPLE_SPEC
            resp = client.post("/api/v1/benchmarks", json=CREATE_PAYLOAD)
            assert resp.status_code == 201
            body = resp.json()
            assert body["eval_spec"] is not None
            assert body["eval_spec"]["primary_metric"]["name"] == "accuracy"
            assert body["eval_spec"]["secondary_metrics"] == []
            assert body["eval_spec"]["guardrails"] == []
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_legacy_row_get_synthesizes_eval_spec(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.get_spec.return_value = SAMPLE_SPEC
            resp = client.get(f"/api/v1/benchmarks/{SAMPLE_SPEC['spec_id']}")
            assert resp.status_code == 200
            body = resp.json()
            assert body["eval_spec"] is not None
            assert body["eval_spec"]["primary_metric"]["name"] == "accuracy"
            assert body["eval_spec"]["primary_metric"]["direction"] == "higher_is_better"
            assert body["eval_spec"]["primary_metric"]["threshold"] is None
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_update_eval_spec_passes_through(self) -> None:
        updated = {**SAMPLE_SPEC, "eval_spec": EVAL_SPEC_PAYLOAD}
        client, svc, _ = _make_authed_client()
        try:
            svc.update_spec_fields.return_value = updated
            resp = client.put(
                f"/api/v1/benchmarks/{SAMPLE_SPEC['spec_id']}",
                json={"eval_spec": EVAL_SPEC_PAYLOAD},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["eval_spec"]["primary_metric"]["name"] == "accuracy"
            call_kwargs = svc.update_spec_fields.call_args
            changes = call_kwargs[0][1] if call_kwargs[0] else call_kwargs[1].get("changes", {})
            assert "eval_spec" in changes
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_legacy_row_with_baseline_synthesizes_threshold(self) -> None:
        spec_with_baseline = {**SAMPLE_SPEC, "baseline_value": 0.75}
        client, svc, _ = _make_authed_client()
        try:
            svc.get_spec.return_value = spec_with_baseline
            resp = client.get(f"/api/v1/benchmarks/{SAMPLE_SPEC['spec_id']}")
            assert resp.status_code == 200
            body = resp.json()
            assert body["eval_spec"]["primary_metric"]["threshold"] == 0.75
        finally:
            _cleanup_overrides()


class TestAuthEnforcement:
    """Verify all endpoints enforce auth via require_auth dependency."""

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_create_returns_401_when_auth_fails(self) -> None:
        """require_auth raises 401 when request.state has no user_id."""
        from fastapi import HTTPException

        async def _reject_auth(request: Request) -> dict[str, Any]:
            raise HTTPException(status_code=401, detail="Authentication required")

        app.dependency_overrides[require_auth] = _reject_auth
        try:
            c = TestClient(app, raise_server_exceptions=False)
            assert c.post("/api/v1/benchmarks", json=CREATE_PAYLOAD).status_code == 401
            assert c.get("/api/v1/benchmarks/some-id").status_code == 401
            assert c.get("/api/v1/benchmarks").status_code == 401
            assert c.put("/api/v1/benchmarks/some-id", json={}).status_code == 401
            assert c.delete("/api/v1/benchmarks/some-id").status_code == 401
        finally:
            _cleanup_overrides()

    def test_require_auth_dependency_present_on_all_routes(self) -> None:
        """Structural check: all benchmark routes use require_auth."""
        from src.api.routes.benchmarks import router as benchmarks_router

        for route in benchmarks_router.routes:
            endpoint = getattr(route, "endpoint", None)
            if endpoint is None:
                continue
            import inspect

            sig = inspect.signature(endpoint)
            param_defaults = [p.default for p in sig.parameters.values()]
            has_auth = any(
                hasattr(d, "dependency") and d.dependency is require_auth
                for d in param_defaults
                if hasattr(d, "dependency")
            )
            assert has_auth, f"Route {route.path} missing require_auth dependency"
