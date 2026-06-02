"""Unit tests for 402 balance check and debit usage in auth middleware."""

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest
from fastapi import Request
from starlette.responses import Response

from src.middleware.auth import APIKeyAuthMiddleware, ValidationResult


class TestBalanceCheck:
    """Test 402 balance enforcement in dispatch()."""

    @pytest.fixture
    def mock_app(self):
        async def app(scope, receive, send):
            pass

        return app

    @pytest.fixture
    def middleware(self, mock_app):
        return APIKeyAuthMiddleware(
            app=mock_app,
            auth_service_url="http://test-auth-service",
            cache=None,
            excluded_paths=["/health"],
        )

    @pytest.fixture
    def mock_request(self):
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/models/test-model/predict"
        request.method = "POST"
        request.headers = {"authorization": "Bearer test-api-key"}
        request.query_params = {}
        request.client = MagicMock(host="127.0.0.1")
        request.state = SimpleNamespace()
        return request

    @pytest.mark.asyncio
    async def test_402_when_insufficient_balance(self, middleware, mock_request):
        """Test that 402 is returned when has_sufficient_balance is False."""
        with (
            patch.object(middleware, "validate_with_auth_service") as mock_validate,
            patch.object(
                middleware, "_debit_usage", new_callable=AsyncMock, return_value="accepted"
            ),
        ):
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read"],
                rate_limit_per_hour=1000,
                has_sufficient_balance=False,
                balance=0.0,
            )

            call_next_called = False

            async def mock_call_next(request):
                nonlocal call_next_called
                call_next_called = True
                return Response(content="Should not reach here", status_code=200)

            response = await middleware.dispatch(mock_request, mock_call_next)

            assert response.status_code == 402
            body = json.loads(response.body.decode())
            assert body["detail"] == "Insufficient balance"
            assert not call_next_called, "Route handler should not be called for 402"

    @pytest.mark.asyncio
    async def test_request_passes_with_sufficient_balance(self, middleware, mock_request):
        """Test that requests pass through when has_sufficient_balance is True."""
        with (
            patch.object(middleware, "validate_with_auth_service") as mock_validate,
            patch.object(
                middleware, "_debit_usage", new_callable=AsyncMock, return_value="accepted"
            ),
        ):
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read"],
                rate_limit_per_hour=1000,
                has_sufficient_balance=True,
                balance=50.0,
            )

            async def mock_call_next(request):
                return Response(content="Success", status_code=200)

            response = await middleware.dispatch(mock_request, mock_call_next)
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_default_balance_fields_allow_requests(self, middleware, mock_request):
        """Test that default ValidationResult fields (backwards compat) allow requests."""
        with (
            patch.object(middleware, "validate_with_auth_service") as mock_validate,
            patch.object(
                middleware, "_debit_usage", new_callable=AsyncMock, return_value="accepted"
            ),
        ):
            # Simulate auth service that hasn't been updated yet (no balance fields)
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read"],
                rate_limit_per_hour=1000,
                # has_sufficient_balance defaults to True
                # balance defaults to 0.0
            )

            async def mock_call_next(request):
                return Response(content="Success", status_code=200)

            response = await middleware.dispatch(mock_request, mock_call_next)
            assert response.status_code == 200


class TestDebitUsage:
    """Test debit usage calls replacing old usage logging."""

    @pytest.fixture
    def mock_app(self):
        async def app(scope, receive, send):
            pass

        return app

    @pytest.fixture
    def middleware(self, mock_app):
        return APIKeyAuthMiddleware(
            app=mock_app,
            auth_service_url="http://test-auth-service",
            cache=None,
            excluded_paths=["/health"],
        )

    @pytest.mark.asyncio
    async def test_debit_called_before_successful_prediction(self, middleware):
        """Test that _debit_usage is awaited before the downstream handler."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/models/my-model/predict"
        request.method = "POST"
        request.headers = {"authorization": "Bearer test-key"}
        request.query_params = {}
        request.client = MagicMock(host="127.0.0.1")
        request.state = SimpleNamespace()

        with (
            patch.object(middleware, "validate_with_auth_service") as mock_validate,
            patch.object(middleware, "_debit_usage", new_callable=AsyncMock) as mock_debit,
        ):
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read"],
                rate_limit_per_hour=1000,
                has_sufficient_balance=True,
                balance=10.0,
            )

            call_order = []

            async def debit_side_effect(*args, **kwargs):
                call_order.append("debit")
                return "accepted"

            mock_debit.side_effect = debit_side_effect

            async def mock_call_next(req):
                call_order.append("call_next")
                return Response(content="OK", status_code=200)

            response = await middleware.dispatch(request, mock_call_next)

            assert response.status_code == 200
            mock_debit.assert_called_once_with(
                "key123",
                "my-model",
                "/api/v1/models/my-model/predict",
                0,
                0,
                request_id=None,
                account_id="user123",
                request_state=request.state,
            )
            assert call_order == ["debit", "call_next"]

    @pytest.mark.asyncio
    async def test_debit_called_even_when_downstream_returns_5xx(self, middleware):
        """Test that pre-request debit still runs when the handler returns 5xx."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/models/my-model/predict"
        request.method = "POST"
        request.headers = {"authorization": "Bearer test-key"}
        request.query_params = {}
        request.client = MagicMock(host="127.0.0.1")
        request.state = SimpleNamespace()

        with (
            patch.object(middleware, "validate_with_auth_service") as mock_validate,
            patch.object(
                middleware, "_debit_usage", new_callable=AsyncMock, return_value="accepted"
            ) as mock_debit,
        ):
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read"],
                rate_limit_per_hour=1000,
                has_sufficient_balance=True,
                balance=10.0,
            )

            async def mock_call_next(req):
                return Response(content="Internal Error", status_code=500)

            response = await middleware.dispatch(request, mock_call_next)

            assert response.status_code == 500
            mock_debit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_debit_includes_idempotency_key(self, middleware):
        """Test that debit request includes an idempotency key."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            outcome = await middleware._debit_usage("key123", "model-1", "/predict", 100, 200)

            mock_client.post.assert_called_once()
            assert outcome == "accepted"
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert "idempotency_key" in payload
            assert payload["idempotency_key"].startswith("key123-")
            assert payload["model_id"] == "model-1"
            assert payload["compute_ms"] == 100
            assert payload["predictions_count"] == 1

    @pytest.mark.asyncio
    async def test_debit_retries_on_transient_failure(self, middleware):
        """Test that pre-request debit does not retry transport failures."""

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection failed")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            outcome = await middleware._debit_usage("key123", "model-1", "/predict", 100, 200)

            assert outcome == "error"
            mock_client.post.assert_called_once()
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_debit_logs_warning_after_all_retries_fail(self, middleware):
        """Test that transport failures log once and fail open."""
        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("src.middleware.auth.logger") as mock_logger,
        ):
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection failed")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            outcome = await middleware._debit_usage("key123", "model-1", "/predict", 100, 200)

            assert outcome == "error"
            mock_logger.warning.assert_called_once()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "key_id=key123" in warning_msg
            assert "1 attempts" in warning_msg

    @pytest.mark.asyncio
    async def test_debit_logs_warning_on_422(self, middleware):
        """Test that debit logs 422 responses and does not retry them."""
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.text = '{"error":"invalid model_id"}'

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("src.middleware.auth.logger") as mock_logger,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            outcome = await middleware._debit_usage("key123", "model-1", "/predict", 100, 200)

            mock_client.post.assert_called_once()
            mock_sleep.assert_not_called()
            assert outcome == "error"
            mock_logger.warning.assert_called_once()

            payload = json.loads(mock_logger.warning.call_args[0][0])
            assert payload["event"] == "usage_debit_failure"
            assert payload["status_code"] == 422
            assert payload["response_body"] == '{"error":"invalid model_id"}'
            assert payload["key_id"] == "key123"
            assert payload["model_id"] == "model-1"
            assert payload["endpoint"] == "/predict"
            assert payload["idempotency_key"].startswith("key123-")

    @pytest.mark.asyncio
    async def test_debit_logs_rejection_on_402(self, middleware):
        """Test that debit emits a structured rejection log on 402."""
        mock_response = MagicMock()
        mock_response.status_code = 402
        mock_response.json.return_value = {
            "detail": {
                "error": "insufficient_balance",
                "message": "Balance too low",
            }
        }
        request_state = SimpleNamespace()

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("src.middleware.auth.logger") as mock_logger,
            patch("src.middleware.auth.sentry_sdk") as mock_sentry,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            outcome = await middleware._debit_usage(
                "key123",
                "model-1",
                "/predict",
                100,
                200,
                request_id="req-123",
                account_id="user-123",
                request_state=request_state,
            )

            mock_client.post.assert_called_once()
            mock_sleep.assert_not_called()
            assert outcome == "rejected"
            mock_logger.warning.assert_called_once()
            assert mock_logger.warning.call_args.args[0] == "usage debit rejected"
            assert mock_logger.warning.call_args.kwargs["extra"] == {
                "event": "usage.debit.rejected",
                "account_id": "user-123",
                "model_id": "model-1",
                "reason_code": "insufficient_balance",
                "request_id": "req-123",
            }
            assert request_state._debit_reject_reason == "Balance too low"
            assert request_state._debit_reject_reason_code == "insufficient_balance"
            mock_sentry.capture_message.assert_called_once_with(
                "usage.debit.rejected", level="warning"
            )

    @pytest.mark.asyncio
    async def test_debit_no_failure_log_on_2xx(self, middleware):
        """Test that successful debit responses are not logged as failures."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("src.middleware.auth.logger") as mock_logger,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            outcome = await middleware._debit_usage("key123", "model-1", "/predict", 100, 200)

            assert outcome == "accepted"
            mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_debit_response_body_truncated(self, middleware):
        """Test that logged debit failure bodies are truncated."""
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.text = "x" * 5000

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("src.middleware.auth.logger") as mock_logger,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            outcome = await middleware._debit_usage("key123", "model-1", "/predict", 100, 200)

            assert outcome == "error"
            payload = json.loads(mock_logger.warning.call_args[0][0])
            assert len(payload["response_body"]) == 2048

    @pytest.mark.asyncio
    async def test_debit_key_id_is_opaque_in_logs(self, middleware):
        """Test that the debit log includes only the opaque key_id."""
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.text = "invalid"

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("src.middleware.auth.logger") as mock_logger,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            outcome = await middleware._debit_usage("key123", "model-1", "/predict", 100, 200)

            assert outcome == "error"
            payload = json.loads(mock_logger.warning.call_args[0][0])
            assert payload["key_id"] == "key123"
            assert "Bearer test-api-key" not in mock_logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_debit_5xx_logs_warning_each_attempt(self, middleware):
        """Test that 5xx debit failures log once with no retries."""
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = '{"error":"upstream unavailable"}'

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("src.middleware.auth.logger") as mock_logger,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            outcome = await middleware._debit_usage("key123", "model-1", "/predict", 100, 200)

            assert outcome == "error"
            assert mock_client.post.call_count == 1
            assert mock_logger.warning.call_count == 1
            mock_sleep.assert_not_called()

            payload = json.loads(mock_logger.warning.call_args.args[0])
            assert payload["event"] == "usage_debit_failure"
            assert payload["status_code"] == 503

            mock_logger.error.assert_called_once()
            error_payload = json.loads(mock_logger.error.call_args[0][0])
            assert error_payload["event"] == "usage_debit_retry_exhausted"
            assert error_payload["status_code"] == 503
            assert error_payload["attempts"] == 1
            assert error_payload["key_id"] == "key123"
            assert error_payload["model_id"] == "model-1"
            assert error_payload["endpoint"] == "/predict"
            assert error_payload["idempotency_key"].startswith("key123-")

    @pytest.mark.asyncio
    async def test_debit_endpoint_url(self, middleware):
        """Test that debit calls the correct endpoint URL."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await middleware._debit_usage("key456", "model-1", "/predict", 100, 200)

            call_args = mock_client.post.call_args
            assert call_args[0][0] == "http://test-auth-service/api/v1/usage/key456/debit"

    @pytest.mark.asyncio
    async def test_debit_does_not_retry_on_client_error(self, middleware):
        """Test that debit does not retry on 4xx (client error) responses."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"error":"bad request"}'

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            outcome = await middleware._debit_usage("key123", "model-1", "/predict", 100, 200)

            assert outcome == "error"
            mock_client.post.assert_called_once()
            mock_sleep.assert_not_called()


class TestDebitRejected:
    """Test 402 rejection behavior in dispatch and debit logging."""

    @pytest.fixture
    def mock_app(self):
        async def app(scope, receive, send):
            pass

        return app

    @pytest.fixture
    def middleware(self, mock_app):
        return APIKeyAuthMiddleware(
            app=mock_app,
            auth_service_url="http://test-auth-service",
            cache=None,
            excluded_paths=["/health"],
        )

    @pytest.fixture
    def mock_request(self):
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/models/my-model/predict"
        request.method = "POST"
        request.headers = {"authorization": "Bearer test-key"}
        request.query_params = {}
        request.client = MagicMock(host="127.0.0.1")
        request.state = SimpleNamespace()
        return request

    @pytest.fixture
    def validation_result(self):
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
    async def test_usage_debit_rejected_returns_402_with_structured_body(
        self, middleware, mock_request, validation_result
    ):
        with (
            patch.object(middleware, "validate_with_auth_service", return_value=validation_result),
            patch.object(middleware, "_debit_usage", new_callable=AsyncMock) as mock_debit,
        ):

            async def debit_side_effect(*args, **kwargs):
                mock_request.state._debit_reject_reason = "Balance too low"
                mock_request.state._debit_reject_reason_code = "insufficient_balance"
                return "rejected"

            mock_debit.side_effect = debit_side_effect

            response = await middleware.dispatch(mock_request, AsyncMock())

        assert response.status_code == 402
        assert json.loads(response.body.decode()) == {
            "error": "usage_debit_rejected",
            "reason": "Balance too low",
            "reason_code": "insufficient_balance",
        }

    @pytest.mark.asyncio
    async def test_usage_debit_rejected_does_not_invoke_downstream_handler(
        self, middleware, mock_request, validation_result
    ):
        call_next = AsyncMock(return_value=Response(content="OK", status_code=200))

        with (
            patch.object(middleware, "validate_with_auth_service", return_value=validation_result),
            patch.object(
                middleware, "_debit_usage", new_callable=AsyncMock, return_value="rejected"
            ),
        ):
            response = await middleware.dispatch(mock_request, call_next)

        assert response.status_code == 402
        call_next.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_usage_debit_rejected_emits_structured_log(self, middleware, caplog):
        mock_response = MagicMock()
        mock_response.status_code = 402
        mock_response.json.return_value = {
            "detail": {
                "error": "insufficient_settled_balance",
                "message": "Settled balance 0.00 insufficient.",
            }
        }

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("src.middleware.auth.sentry_sdk") as mock_sentry,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with caplog.at_level(logging.WARNING):
                outcome = await middleware._debit_usage(
                    "key123",
                    "model-1",
                    "/predict",
                    0,
                    0,
                    request_id="req-1",
                    account_id="user-1",
                    request_state=SimpleNamespace(),
                )

        assert outcome == "rejected"
        record = next(record for record in caplog.records if record.msg == "usage debit rejected")
        assert record.event == "usage.debit.rejected"
        assert record.model_id == "model-1"
        assert record.reason_code == "insufficient_settled_balance"
        assert record.request_id == "req-1"
        mock_sentry.capture_message.assert_called_once_with("usage.debit.rejected", level="warning")

    @pytest.mark.asyncio
    async def test_usage_debit_rejected_with_missing_reason_fields(
        self, middleware, mock_request, validation_result
    ):
        mock_response = MagicMock()
        mock_response.status_code = 402
        mock_response.json.return_value = {}

        with (
            patch.object(middleware, "validate_with_auth_service", return_value=validation_result),
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("src.middleware.auth.sentry_sdk"),
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            response = await middleware.dispatch(mock_request, AsyncMock())

        assert response.status_code == 402
        assert json.loads(response.body.decode()) == {
            "error": "usage_debit_rejected",
            "reason": None,
            "reason_code": None,
        }


class TestDebitPayloadShape:
    """Test the exact debit payload sent to auth-service."""

    @pytest.fixture
    def mock_app(self):
        async def app(scope, receive, send):
            pass

        return app

    @pytest.fixture
    def middleware(self, mock_app):
        return APIKeyAuthMiddleware(
            app=mock_app,
            auth_service_url="http://test-auth-service",
            cache=None,
            excluded_paths=["/health"],
        )

    @pytest.fixture
    def mock_client(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client
            yield mock_client

    @pytest.mark.asyncio
    async def test_payload_includes_compute_ms(self, middleware, mock_client):
        await middleware._debit_usage("key123", "model-1", "/api/v1/models/30/predict", 100, 200)

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["compute_ms"] == 100

    @pytest.mark.asyncio
    async def test_payload_includes_predictions_count(self, middleware, mock_client):
        await middleware._debit_usage("key123", "model-1", "/api/v1/models/30/predict", 100, 200)

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["predictions_count"] == 1

    @pytest.mark.asyncio
    async def test_exact_payload_shape(self, middleware, mock_client):
        with patch("src.middleware.auth.time.time", return_value=1234.567):
            await middleware._debit_usage(
                "key123", "model-30", "/api/v1/models/30/predict", 321, 200
            )

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload == {
            "model_id": "model-30",
            "endpoint": "/api/v1/models/30/predict",
            "response_time_ms": 321,
            "status_code": 200,
            "service_id": middleware.settings.auth_service_id,
            "idempotency_key": "key123-1234567",
            "compute_ms": 321,
            "predictions_count": 1,
        }

    @pytest.mark.asyncio
    async def test_compute_ms_when_response_time_is_zero(self, middleware, mock_client):
        await middleware._debit_usage("key123", "model-1", "/api/v1/models/30/predict", 0, 200)

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["compute_ms"] == 0


class TestExtractModelId:
    """Test model ID extraction from URL paths."""

    @pytest.fixture
    def mock_app(self):
        async def app(scope, receive, send):
            pass

        return app

    @pytest.fixture
    def middleware(self, mock_app):
        return APIKeyAuthMiddleware(
            app=mock_app,
            auth_service_url="http://test-auth-service",
            cache=None,
            excluded_paths=["/health"],
        )

    def test_extract_model_id_from_predict_path(self, middleware):
        assert middleware._extract_model_id("/api/v1/models/my-model/predict") == "my-model"

    def test_extract_model_id_from_model_detail_path(self, middleware):
        assert middleware._extract_model_id("/api/v1/models/model-123") == "model-123"

    def test_extract_model_id_returns_none_for_non_model_path(self, middleware):
        assert middleware._extract_model_id("/api/v1/health") is None

    def test_extract_model_id_returns_none_for_models_list(self, middleware):
        # /api/v1/models has no model_id segment after it
        assert middleware._extract_model_id("/api/v1/models") is None


class TestCacheTTL:
    """Test that cache TTL is set to 60 seconds."""

    @pytest.fixture
    def mock_cache(self):
        cache = Mock()
        cache.get = Mock(return_value=None)
        cache.setex = Mock()
        cache.ping = Mock()
        return cache

    @pytest.fixture
    def mock_app(self):
        async def app(scope, receive, send):
            pass

        return app

    @pytest.fixture
    def middleware(self, mock_app, mock_cache):
        mw = APIKeyAuthMiddleware(
            app=mock_app,
            auth_service_url="http://test-auth-service",
            cache=mock_cache,
            excluded_paths=["/health"],
        )
        return mw

    @pytest.mark.asyncio
    async def test_cache_ttl_is_60_seconds(self, middleware, mock_cache):
        """Test that validation results are cached with 60 second TTL."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/models/test/predict"
        request.method = "POST"
        request.headers = {"authorization": "Bearer test-key"}
        request.query_params = {}
        request.client = MagicMock(host="127.0.0.1")
        request.state = SimpleNamespace()

        with (
            patch.object(middleware, "validate_with_auth_service") as mock_validate,
            patch.object(
                middleware, "_debit_usage", new_callable=AsyncMock, return_value="accepted"
            ),
        ):
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read"],
                rate_limit_per_hour=1000,
                has_sufficient_balance=True,
                balance=10.0,
            )

            async def mock_call_next(req):
                return Response(content="OK", status_code=200)

            await middleware.dispatch(request, mock_call_next)

        mock_cache.setex.assert_called_once()
        cache_call_args = mock_cache.setex.call_args
        assert cache_call_args[0][1] == 60

    @pytest.mark.asyncio
    async def test_cache_includes_balance_fields(self, middleware, mock_cache):
        """Test that cached data includes has_sufficient_balance and balance."""
        request = MagicMock(spec=Request)
        request.url.path = "/protected"
        request.method = "GET"
        request.headers = {"authorization": "Bearer test-key"}
        request.query_params = {}
        request.client = MagicMock(host="127.0.0.1")
        request.state = SimpleNamespace()

        with (
            patch.object(middleware, "validate_with_auth_service") as mock_validate,
            patch.object(
                middleware, "_debit_usage", new_callable=AsyncMock, return_value="accepted"
            ),
        ):
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                user_id="user123",
                key_id="key123",
                service_id="platform",
                scopes=["model:read"],
                rate_limit_per_hour=1000,
                has_sufficient_balance=True,
                balance=25.50,
            )

            async def mock_call_next(req):
                return Response(content="OK", status_code=200)

            await middleware.dispatch(request, mock_call_next)

        cache_call_args = mock_cache.setex.call_args
        cached_json = json.loads(cache_call_args[0][2])
        assert cached_json["has_sufficient_balance"] is True
        assert cached_json["balance"] == 25.50
