"""Unit tests for dataset arrival API routes."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from fastapi import Request
from fastapi.testclient import TestClient
from starlette.responses import Response

from src.api.dependencies import get_dataset_arrival_handler
from src.api.main import app


async def _passthrough_middleware_dispatch(self: Any, request: Request, call_next: Any) -> Response:
    """Middleware dispatch that bypasses auth and sets user state."""
    request.state.user_id = "test-user"
    request.state.api_key_id = "key-1"
    request.state.service_id = "test"
    request.state.scopes = []
    request.state.rate_limit_per_hour = None
    return await call_next(request)


def _override_handler(arrivals: list | None = None) -> MagicMock:
    mock = MagicMock()
    mock.list_arrivals.return_value = arrivals or []
    return mock


@patch(
    "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
    _passthrough_middleware_dispatch,
)
def test_list_arrivals_empty() -> None:
    mock = _override_handler()
    app.dependency_overrides[get_dataset_arrival_handler] = lambda: mock
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/dataset-arrivals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["count"] == 0
    finally:
        app.dependency_overrides.clear()


@patch(
    "src.middleware.auth.APIKeyAuthMiddleware.dispatch",
    _passthrough_middleware_dispatch,
)
def test_list_arrivals_with_results() -> None:
    mock = _override_handler(
        arrivals=[
            {
                "id": "arr-1",
                "model_id": "model-a",
                "bucket": "b",
                "object_key": "k",
                "reeval_triggered": False,
            }
        ]
    )
    app.dependency_overrides[get_dataset_arrival_handler] = lambda: mock
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/dataset-arrivals?model_id=model-a&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        mock.list_arrivals.assert_called_once_with(model_id="model-a", limit=10)
    finally:
        app.dependency_overrides.clear()
