"""Unit tests for evaluation schedule CRUD API routes."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from fastapi import Request
from fastapi.testclient import TestClient
from starlette.responses import Response

from src.api.main import app
from src.api.services.governance.audit_logger import AuditLogger
from src.api.services.governance.evaluation_schedule import (
    EvaluationScheduleService,
    NoBenchmarkSpecError,
    ScheduleAlreadyExistsError,
)
from src.middleware.auth import require_auth

VALID_AUTH = {"user_id": "test-user", "api_key_id": "key-1", "scopes": []}

SAMPLE_SCHEDULE = {
    "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "model_id": "model-123",
    "cron_expression": "0 */6 * * *",
    "enabled": True,
    "last_run_at": None,
    "next_run_at": None,
    "created_at": "2024-01-01T00:00:00+00:00",
    "updated_at": "2024-01-01T00:00:00+00:00",
}

BASE_URL = "/api/v1/models/model-123/evaluation-schedule"


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
    mock_service = MagicMock(spec=EvaluationScheduleService)
    mock_audit = MagicMock(spec=AuditLogger)

    from src.api.dependencies import get_audit_logger, get_evaluation_schedule_service

    app.dependency_overrides[get_evaluation_schedule_service] = lambda: mock_service
    app.dependency_overrides[get_audit_logger] = lambda: mock_audit

    return TestClient(app, raise_server_exceptions=False), mock_service, mock_audit


def _cleanup_overrides() -> None:
    app.dependency_overrides.clear()


class TestCreateEvaluationSchedule:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_create_returns_201(self) -> None:
        client, svc, audit = _make_authed_client()
        try:
            svc.create_schedule.return_value = SAMPLE_SCHEDULE
            resp = client.post(BASE_URL, json={"cron_expression": "0 */6 * * *"})
            assert resp.status_code == 201
            body = resp.json()
            assert body["id"] == SAMPLE_SCHEDULE["id"]
            assert body["model_id"] == "model-123"
            assert body["cron_expression"] == "0 */6 * * *"
            assert body["enabled"] is True
            audit.log.assert_called_once()
            assert audit.log.call_args.kwargs["action"] == "evaluation_schedule.created"
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_create_with_enabled_false(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.create_schedule.return_value = {**SAMPLE_SCHEDULE, "enabled": False}
            resp = client.post(BASE_URL, json={"cron_expression": "0 0 * * 1", "enabled": False})
            assert resp.status_code == 201
            assert resp.json()["enabled"] is False
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_create_no_benchmark_returns_409(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.create_schedule.side_effect = NoBenchmarkSpecError("no BenchmarkSpec")
            resp = client.post(BASE_URL, json={"cron_expression": "0 */6 * * *"})
            assert resp.status_code == 409
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_create_duplicate_returns_409(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.create_schedule.side_effect = ScheduleAlreadyExistsError("already exists")
            resp = client.post(BASE_URL, json={"cron_expression": "0 0 * * *"})
            assert resp.status_code == 409
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_create_invalid_cron_returns_422(self) -> None:
        client, _, _ = _make_authed_client()
        try:
            resp = client.post(BASE_URL, json={"cron_expression": "not a cron"})
            assert resp.status_code == 422
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_create_missing_cron_returns_422(self) -> None:
        client, _, _ = _make_authed_client()
        try:
            resp = client.post(BASE_URL, json={})
            assert resp.status_code == 422
        finally:
            _cleanup_overrides()


class TestGetEvaluationSchedule:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_get_returns_200(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.get_schedule.return_value = SAMPLE_SCHEDULE
            resp = client.get(BASE_URL)
            assert resp.status_code == 200
            assert resp.json()["model_id"] == "model-123"
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_get_not_found_returns_404(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.get_schedule.return_value = None
            resp = client.get("/api/v1/models/model-999/evaluation-schedule")
            assert resp.status_code == 404
            assert "model-999" in resp.json()["detail"]
        finally:
            _cleanup_overrides()


class TestUpdateEvaluationSchedule:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_update_returns_200(self) -> None:
        updated = {**SAMPLE_SCHEDULE, "cron_expression": "0 0 * * *", "enabled": False}
        client, svc, audit = _make_authed_client()
        try:
            svc.update_schedule.return_value = updated
            resp = client.put(
                BASE_URL,
                json={"cron_expression": "0 0 * * *", "enabled": False},
            )
            assert resp.status_code == 200
            assert resp.json()["cron_expression"] == "0 0 * * *"
            assert resp.json()["enabled"] is False
            audit.log.assert_called_once()
            assert audit.log.call_args.kwargs["action"] == "evaluation_schedule.updated"
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_update_not_found_returns_404(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.update_schedule.return_value = None
            resp = client.put(BASE_URL, json={"enabled": False})
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
            svc.update_schedule.return_value = SAMPLE_SCHEDULE
            resp = client.put(BASE_URL, json={})
            assert resp.status_code == 200
        finally:
            _cleanup_overrides()


class TestDeleteEvaluationSchedule:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_delete_returns_204(self) -> None:
        client, svc, audit = _make_authed_client()
        try:
            svc.delete_schedule.return_value = True
            resp = client.delete(BASE_URL)
            assert resp.status_code == 204
            audit.log.assert_called_once()
            assert audit.log.call_args.kwargs["action"] == "evaluation_schedule.deleted"
        finally:
            _cleanup_overrides()

    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_delete_not_found_returns_404(self) -> None:
        client, svc, _ = _make_authed_client()
        try:
            svc.delete_schedule.return_value = False
            resp = client.delete("/api/v1/models/nonexistent/evaluation-schedule")
            assert resp.status_code == 404
        finally:
            _cleanup_overrides()


class TestAuthEnforcement:
    @patch(
        "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
        _passthrough_middleware_dispatch,
    )
    def test_returns_401_when_auth_fails(self) -> None:
        from fastapi import HTTPException

        async def _reject_auth(request: Request) -> dict[str, Any]:
            raise HTTPException(status_code=401, detail="Authentication required")

        app.dependency_overrides[require_auth] = _reject_auth
        try:
            c = TestClient(app, raise_server_exceptions=False)
            assert c.post(BASE_URL, json={"cron_expression": "0 0 * * *"}).status_code == 401
            assert c.get(BASE_URL).status_code == 401
            assert c.put(BASE_URL, json={}).status_code == 401
            assert c.delete(BASE_URL).status_code == 401
        finally:
            _cleanup_overrides()

    def test_require_auth_dependency_present_on_all_routes(self) -> None:
        from src.api.routes.evaluation_schedule import router as es_router

        for route in es_router.routes:
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
