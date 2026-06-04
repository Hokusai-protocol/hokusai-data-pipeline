"""Regression tests for StopIteration surfaced through auth middleware coroutines."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from starlette.responses import Response

from src.middleware.auth import APIKeyAuthMiddleware, ValidationResult


@pytest.fixture
def mock_app():
    async def app(scope, receive, send):
        pass

    return app


@pytest.fixture
def middleware(mock_app):
    return APIKeyAuthMiddleware(
        app=mock_app,
        auth_service_url="http://test-auth-service",
        cache=None,
        excluded_paths=["/health"],
    )


@pytest.fixture
def mock_request():
    request = MagicMock(spec=Request)
    request.url.path = "/api/v1/models/test-model/predict"
    request.method = "POST"
    request.headers = {"authorization": "Bearer test-api-key"}
    request.query_params = {}
    request.client = MagicMock(host="127.0.0.1")
    request.state = SimpleNamespace()
    return request


@pytest.fixture
def validation_result():
    return ValidationResult(
        is_valid=True,
        user_id="user123",
        key_id="key123",
        service_id="platform",
        scopes=["model:read"],
        rate_limit_per_hour=1000,
        has_sufficient_balance=True,
        balance=10.0,
    )


@pytest.mark.asyncio
async def test_dispatch_does_not_propagate_runtime_error_from_debit_usage(
    middleware, mock_request, validation_result
):
    """Debit failures must not crash the request path with a generic 500."""
    downstream_response = Response(content="OK", status_code=200)
    call_next = AsyncMock(return_value=downstream_response)

    with (
        patch.object(middleware, "validate_with_auth_service", return_value=validation_result),
        patch.object(middleware, "_debit_usage", new_callable=AsyncMock) as mock_debit,
    ):
        mock_debit.side_effect = RuntimeError("coroutine raised StopIteration")

        response = await middleware.dispatch(mock_request, call_next)

    call_next.assert_awaited_once_with(mock_request)
    assert response is downstream_response
