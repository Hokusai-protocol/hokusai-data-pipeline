"""Unit tests for POST /api/v1/models/{model_id}/contributions.

The route accepts both the Wavemill envelope (``{ rows, metadata }``) and the
hokusai-site envelope (``{ modelId, benchmarkSpecId, rows, ... }``). These tests
exercise both envelopes plus auth, error, and validation paths without hitting
production services.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from src.api.endpoints import contributions
from src.api.middleware.validation_logging import validation_422_exception_handler
from src.api.utils.config import get_settings
from src.middleware.auth import APIKeyAuthMiddleware, require_auth


def _make_router_app() -> FastAPI:
    app = FastAPI()
    app.include_router(contributions.router)
    app.add_exception_handler(RequestValidationError, validation_422_exception_handler)
    app.dependency_overrides[require_auth] = lambda: {
        "user_id": "test-user",
        "api_key_id": "test-key",
        "scopes": ["model:write"],
    }
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_router_app())


def _wavemill_row() -> dict[str, object]:
    return {
        "schema_version": "technical_task_router_row/v1",
        "task_descriptor": {"task_type": "feature"},
        "allowed_models": ["fast-coder-v1", "deep-coder-v2"],
        "selected_models": {"coder": "fast-coder-v1", "reviewer": "deep-coder-v2"},
        "success_under_budget": True,
        "completion_result": "success",
        "observed_at": "2026-01-15T12:00:00Z",
    }


def _submit_data_row() -> dict[str, object]:
    return {
        "success_under_budget": True,
        "actual_cost_usd": 0.25,
        "wall_clock_seconds": 3.5,
        "task_id": "task-abc",
        "harness": "wavemill",
    }


class TestWavemillEnvelope:
    """Wavemill drain sends ``{ rows, metadata: { idempotency_key } }``."""

    def test_accepts_technical_task_router_row(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/models/30/contributions",
            json={
                "rows": [_wavemill_row()],
                "metadata": {"idempotency_key": "batch-001"},
            },
            headers={"Idempotency-Key": "batch-001"},
        )

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "accepted"
        assert body["submittedRows"] == 1
        assert body["modelId"] == 30
        assert body["submissionId"]
        assert body["jobId"]
        assert body["jobIds"] == [body["jobId"]]
        assert body["idempotencyKey"] == "batch-001"
        assert response.headers["X-Request-ID"]

    def test_accepts_submit_data_row(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/models/21/contributions",
            json={"rows": [_submit_data_row()]},
        )
        assert response.status_code == 202
        body = response.json()
        assert body["submittedRows"] == 1
        assert body["modelId"] == 21
        assert body["rowSchemaCounts"]["submit_data_row"] == 1


class TestSiteEnvelope:
    """hokusai-site forwards ``{ modelId, benchmarkSpecId, rows, ... }``."""

    def test_accepts_matching_model_id(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/models/30/contributions",
            json={
                "modelId": 30,
                "benchmarkSpecId": "spec-abc",
                "schemaVersion": "technical_task_router_row/v1",
                "templateId": "tmpl-1",
                "rows": [_wavemill_row()],
            },
        )
        assert response.status_code == 202
        body = response.json()
        assert body["modelId"] == 30
        assert body["submittedRows"] == 1

    def test_rejects_model_id_mismatch(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/models/30/contributions",
            json={
                "modelId": 21,
                "benchmarkSpecId": "spec-abc",
                "rows": [_wavemill_row()],
            },
        )
        assert response.status_code == 400
        assert "modelId" in response.json()["detail"]


class TestRouteErrors:
    def test_unknown_model_id_returns_404(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/models/9999/contributions",
            json={"rows": [_wavemill_row()]},
        )
        assert response.status_code == 404
        assert "9999" in response.json()["detail"]

    def test_empty_rows_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/models/30/contributions",
            json={"rows": []},
        )
        assert response.status_code == 422

    def test_missing_rows_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/models/30/contributions",
            json={},
        )
        assert response.status_code == 422

    def test_forbidden_row_key_returns_422(self, client: TestClient) -> None:
        bad_row = dict(_wavemill_row())
        bad_row["prompt"] = "raw user prompt should be redacted upstream"
        response = client.post(
            "/api/v1/models/30/contributions",
            json={"rows": [bad_row]},
        )
        assert response.status_code == 422

    def test_validation_422_emits_structured_log(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            response = client.post("/api/v1/models/30/contributions", json={})

        assert response.status_code == 422
        assert response.headers["X-Request-ID"]
        records = [record for record in caplog.records if record.msg == "validation_422"]
        assert records
        record = records[0]
        assert record.endpoint == "/api/v1/models/30/contributions"


class TestAuthEnforcement:
    """The route depends on ``require_auth``; missing API key returns 401."""

    @pytest.fixture
    def auth_app(self, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
        monkeypatch.setenv("DB_PASSWORD", "test-password")
        get_settings.cache_clear()

        app = FastAPI()
        app.add_middleware(APIKeyAuthMiddleware, excluded_paths=["/health"])
        app.include_router(contributions.router)
        return app

    def test_missing_api_key_returns_401(self, auth_app: FastAPI) -> None:
        client = TestClient(auth_app)
        response = client.post(
            "/api/v1/models/30/contributions",
            json={"rows": [_wavemill_row()]},
        )
        assert response.status_code == 401
        assert "API key required" in response.json()["detail"]

    def test_valid_api_key_passes(self, auth_app: FastAPI) -> None:
        client = TestClient(auth_app)
        from src.middleware.auth import ValidationResult

        async def fake_validate(self, api_key, client_ip=None):  # type: ignore[no-untyped-def]
            return ValidationResult(
                is_valid=True,
                user_id="user-1",
                key_id="key-1",
                scopes=["model:write"],
            )

        with patch(
            "src.middleware.auth.APIKeyAuthMiddleware.validate_with_auth_service",
            new=fake_validate,
        ):
            response = client.post(
                "/api/v1/models/30/contributions",
                headers={"Authorization": "Bearer hk_test"},
                json={"rows": [_wavemill_row()]},
            )
        assert response.status_code == 202


class TestRowSchemaCounting:
    def test_mixed_row_schemas_are_counted(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/models/30/contributions",
            json={
                "rows": [
                    _wavemill_row(),
                    _submit_data_row(),
                    {"foo": "bar"},
                ]
            },
        )
        assert response.status_code == 202
        counts = response.json()["rowSchemaCounts"]
        assert counts.get("technical_task_router_row_v1") == 1
        assert counts.get("submit_data_row") == 1
        assert counts.get("generic") == 1
