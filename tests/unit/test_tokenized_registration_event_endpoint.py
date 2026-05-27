"""Tests for tokenized registration event ingestion."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

os.environ.setdefault("DB_PASSWORD", "test-password")

from src.api.routes.models import router  # noqa: E402
from src.api.schemas import TokenizedRegistrationEventRequest  # noqa: E402
from src.evaluation.tags import (  # noqa: E402
    BENCHMARK_SPEC_ID_TAG,
    EVAL_SPEC_TAG,
    PRIMARY_METRIC_TAG,
    SCORER_REF_TAG,
)
from src.middleware.auth import APIKeyAuthMiddleware, ValidationResult  # noqa: E402


@pytest.fixture
def app() -> FastAPI:
    """Build a test app with auth middleware and both model route mounts."""
    test_app = FastAPI()
    test_app.add_middleware(APIKeyAuthMiddleware)
    test_app.include_router(router, prefix="/models")
    test_app.include_router(router, prefix="/api/models")
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Test client for model routes."""
    return TestClient(app)


@pytest.fixture
def payload() -> dict[str, object]:
    """Minimal valid request body."""
    return {
        "model_name": "Sales Lead Scoring",
        "version": "7",
        "token_id": "HLEAD",
        "proposal_identifier": "HLEAD",
        "metric_name": "accuracy",
        "baseline_value": 0.10,
        "mlflow_run_id": "run-123",
        "tags": {"user_id": "spoofed", "team": "growth"},
    }


def _validation_result(scopes: list[str] | None = None) -> ValidationResult:
    return ValidationResult(
        is_valid=True,
        user_id="user-123",
        key_id="key-123",
        scopes=scopes or ["mlflow:access"],
    )


def test_tokenized_registration_event_success(
    client: TestClient, payload: dict[str, object]
) -> None:
    """Authorized requests should emit the hook with server-owned tags and defaults."""
    hooks = Mock()
    hooks.on_model_registered_with_baseline.return_value = True

    with (
        patch(
            "src.middleware.auth.APIKeyAuthMiddleware.validate_with_auth_service",
            new=AsyncMock(return_value=_validation_result()),
        ),
        patch("src.api.routes.models.get_registry_hooks", return_value=hooks),
    ):
        response = client.post(
            "/api/models/tokenized-registration-events",
            json=payload,
            headers={"Authorization": "Bearer test-key"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "model_id": "Sales Lead Scoring/7/HLEAD",
        "model_name": "Sales Lead Scoring",
        "version": "7",
        "event_emitted": True,
        "detail": None,
    }
    hooks.on_model_registered_with_baseline.assert_called_once()
    _, kwargs = hooks.on_model_registered_with_baseline.call_args
    assert kwargs["current_value"] == 0.10
    assert kwargs["model_uri"] is None
    assert kwargs["tags"]["user_id"] == "user-123"
    assert kwargs["tags"]["proposal_identifier"] == "HLEAD"
    assert kwargs["tags"]["team"] == "growth"
    assert EVAL_SPEC_TAG not in kwargs["tags"]


def test_tokenized_registration_event_rejects_unauthenticated(
    client: TestClient, payload: dict[str, object]
) -> None:
    """Missing API credentials should be rejected by auth middleware."""
    response = client.post("/api/models/tokenized-registration-events", json=payload)
    assert response.status_code == 401


def test_tokenized_registration_event_rejects_insufficient_scope(
    client: TestClient, payload: dict[str, object]
) -> None:
    """Authenticated users still need write-capable scopes."""
    with patch(
        "src.middleware.auth.APIKeyAuthMiddleware.validate_with_auth_service",
        new=AsyncMock(return_value=_validation_result(scopes=["mlflow:read"])),
    ):
        response = client.post(
            "/api/models/tokenized-registration-events",
            json=payload,
            headers={"X-API-Key": "test-key"},
        )

    assert response.status_code == 403


def test_tokenized_registration_event_validation_errors(
    client: TestClient, payload: dict[str, object]
) -> None:
    """Endpoint validation should reject missing required fields."""
    with patch(
        "src.middleware.auth.APIKeyAuthMiddleware.validate_with_auth_service",
        new=AsyncMock(return_value=_validation_result()),
    ):
        response = client.post(
            "/api/models/tokenized-registration-events",
            json={"model_name": "Sales Lead Scoring"},
            headers={
                "Authorization": "Bearer test-key",
                "Content-Type": "application/json",
            },
        )

    assert response.status_code == 422


def test_tokenized_registration_event_rejects_non_object_api_schema(
    client: TestClient, payload: dict[str, object]
) -> None:
    """api_schema must be an object when present."""
    request_payload = dict(payload)
    request_payload["api_schema"] = "not-an-object"

    with patch(
        "src.middleware.auth.APIKeyAuthMiddleware.validate_with_auth_service",
        new=AsyncMock(return_value=_validation_result()),
    ):
        response = client.post(
            "/api/models/tokenized-registration-events",
            json=request_payload,
            headers={"Authorization": "Bearer test-key"},
        )

    assert response.status_code == 422


def test_tokenized_registration_event_schema_rejects_non_finite_values() -> None:
    """The request schema should reject Infinity/NaN numeric values."""
    with pytest.raises(ValidationError):
        TokenizedRegistrationEventRequest(
            model_name="Sales Lead Scoring",
            version="7",
            token_id="HLEAD",
            proposal_identifier="HLEAD",
            metric_name="accuracy",
            baseline_value=float("inf"),
            mlflow_run_id="run-123",
        )


@pytest.mark.parametrize(
    "field_name",
    ["eval_spec", "scorer_ref", "primary_metric", "benchmark_spec_id"],
)
def test_tokenized_registration_event_schema_rejects_blank_optional_metadata(
    field_name: str,
) -> None:
    """Optional registration metadata must not accept blank strings."""
    payload = {
        "model_name": "Sales Lead Scoring",
        "version": "7",
        "token_id": "HLEAD",
        "proposal_identifier": "HLEAD",
        "metric_name": "accuracy",
        "baseline_value": 0.10,
        "mlflow_run_id": "run-123",
        field_name: "   ",
    }

    with pytest.raises(ValidationError):
        TokenizedRegistrationEventRequest(**payload)


def test_tokenized_registration_event_schema_accepts_richer_metadata() -> None:
    """Optional registration metadata should round-trip after whitespace trimming."""
    request = TokenizedRegistrationEventRequest(
        model_name="Sales Lead Scoring",
        version="7",
        token_id="HLEAD",
        proposal_identifier="HLEAD",
        metric_name="accuracy",
        baseline_value=0.10,
        mlflow_run_id="run-123",
        eval_spec=" technical_task_router/v1 ",
        scorer_ref=" technical_task_router.success_under_budget/v1 ",
        primary_metric=" success_under_budget ",
        benchmark_spec_id=" technical_task_router.success_under_budget/v1 ",
    )

    assert request.eval_spec == "technical_task_router/v1"
    assert request.scorer_ref == "technical_task_router.success_under_budget/v1"
    assert request.primary_metric == "success_under_budget"
    assert request.benchmark_spec_id == "technical_task_router.success_under_budget/v1"


def test_tokenized_registration_event_passes_explicit_values(
    client: TestClient, payload: dict[str, object]
) -> None:
    """Explicit current_value and api_schema should pass through unchanged."""
    hooks = Mock()
    hooks.on_model_registered_with_baseline.return_value = True
    request_payload = dict(payload)
    request_payload["current_value"] = 0.23
    request_payload["model_uri"] = "models:/custom/7"
    request_payload["api_schema"] = {"inputSchema": {"type": "object"}}

    with (
        patch(
            "src.middleware.auth.APIKeyAuthMiddleware.validate_with_auth_service",
            new=AsyncMock(return_value=_validation_result()),
        ),
        patch("src.api.routes.models.get_registry_hooks", return_value=hooks),
    ):
        response = client.post(
            "/api/models/tokenized-registration-events",
            json=request_payload,
            headers={"Authorization": "Bearer test-key"},
        )

    assert response.status_code == 200
    _, kwargs = hooks.on_model_registered_with_baseline.call_args
    assert kwargs["current_value"] == 0.23
    assert kwargs["model_uri"] == "models:/custom/7"
    assert kwargs["api_schema"] == {"inputSchema": {"type": "object"}}


def test_tokenized_registration_event_task_router_metadata_flows_through(
    client: TestClient, payload: dict[str, object]
) -> None:
    """Task-router registrations should forward rich metadata in tags and hook kwargs."""
    hooks = Mock()
    hooks.on_model_registered_with_baseline.return_value = True
    mlflow_client = Mock()
    request_payload = dict(payload)
    request_payload.update(
        {
            "eval_spec": "technical_task_router/v1",
            "scorer_ref": "technical_task_router.success_under_budget/v1",
            "primary_metric": "success_under_budget",
            "benchmark_spec_id": "technical_task_router.success_under_budget/v1",
        }
    )

    with (
        patch(
            "src.middleware.auth.APIKeyAuthMiddleware.validate_with_auth_service",
            new=AsyncMock(return_value=_validation_result()),
        ),
        patch("src.api.routes.models.get_registry_hooks", return_value=hooks),
        patch("src.api.routes.models.mlflow") as mlflow_module,
    ):
        mlflow_module.tracking.MlflowClient.return_value = mlflow_client
        response = client.post(
            "/api/models/tokenized-registration-events",
            json=request_payload,
            headers={"Authorization": "Bearer test-key"},
        )

    assert response.status_code == 200
    _, kwargs = hooks.on_model_registered_with_baseline.call_args
    assert kwargs["eval_spec"] == "technical_task_router/v1"
    assert kwargs["scorer_ref"] == "technical_task_router.success_under_budget/v1"
    assert kwargs["primary_metric"] == "success_under_budget"
    assert kwargs["benchmark_spec_id"] == "technical_task_router.success_under_budget/v1"
    assert kwargs["tags"][EVAL_SPEC_TAG] == "technical_task_router/v1"
    assert kwargs["tags"][SCORER_REF_TAG] == "technical_task_router.success_under_budget/v1"
    assert kwargs["tags"][PRIMARY_METRIC_TAG] == "success_under_budget"
    assert kwargs["tags"][BENCHMARK_SPEC_ID_TAG] == "technical_task_router.success_under_budget/v1"
    mlflow_client.set_model_version_tag.assert_any_call(
        name="Sales Lead Scoring",
        version="7",
        key=EVAL_SPEC_TAG,
        value="technical_task_router/v1",
    )
    mlflow_client.set_tag.assert_any_call(
        "run-123",
        SCORER_REF_TAG,
        "technical_task_router.success_under_budget/v1",
    )


def test_tokenized_registration_event_does_not_derive_schema_server_side(
    client: TestClient, payload: dict[str, object]
) -> None:
    """Requests without api_schema should not trigger server-side MLflow schema lookup."""
    hooks = Mock()
    hooks.on_model_registered_with_baseline.return_value = True
    request_payload = dict(payload)
    request_payload["model_uri"] = "models:/custom/7"

    with (
        patch(
            "src.middleware.auth.APIKeyAuthMiddleware.validate_with_auth_service",
            new=AsyncMock(return_value=_validation_result()),
        ),
        patch("src.api.routes.models.get_registry_hooks", return_value=hooks),
    ):
        response = client.post(
            "/api/models/tokenized-registration-events",
            json=request_payload,
            headers={"Authorization": "Bearer test-key"},
        )

    assert response.status_code == 200
    _, kwargs = hooks.on_model_registered_with_baseline.call_args
    assert kwargs["model_uri"] is None
    assert kwargs["api_schema"] is None


def test_tokenized_registration_event_legacy_payload_skips_mlflow_metadata_mirroring(
    client: TestClient, payload: dict[str, object]
) -> None:
    """Legacy payloads should not attempt rich metadata tag writes."""
    hooks = Mock()
    hooks.on_model_registered_with_baseline.return_value = True

    with (
        patch(
            "src.middleware.auth.APIKeyAuthMiddleware.validate_with_auth_service",
            new=AsyncMock(return_value=_validation_result()),
        ),
        patch("src.api.routes.models.get_registry_hooks", return_value=hooks),
        patch("src.api.routes.models.mlflow") as mlflow_module,
    ):
        response = client.post(
            "/api/models/tokenized-registration-events",
            json=payload,
            headers={"Authorization": "Bearer test-key"},
        )

    assert response.status_code == 200
    mlflow_module.tracking.MlflowClient.assert_not_called()


def test_tokenized_registration_event_returns_502_on_hook_failure(
    client: TestClient, payload: dict[str, object]
) -> None:
    """False-y hook results should become safe upstream failures."""
    hooks = Mock()
    hooks.on_model_registered_with_baseline.return_value = False

    with (
        patch(
            "src.middleware.auth.APIKeyAuthMiddleware.validate_with_auth_service",
            new=AsyncMock(return_value=_validation_result()),
        ),
        patch("src.api.routes.models.get_registry_hooks", return_value=hooks),
    ):
        response = client.post(
            "/api/models/tokenized-registration-events",
            json=payload,
            headers={"Authorization": "Bearer test-key"},
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "Failed to emit model registration event"


def test_tokenized_registration_event_returns_502_on_hook_exception(
    client: TestClient, payload: dict[str, object]
) -> None:
    """Raised hook exceptions should stay opaque to callers."""
    hooks = Mock()
    hooks.on_model_registered_with_baseline.side_effect = RuntimeError("publisher unreachable")

    with (
        patch(
            "src.middleware.auth.APIKeyAuthMiddleware.validate_with_auth_service",
            new=AsyncMock(return_value=_validation_result()),
        ),
        patch("src.api.routes.models.get_registry_hooks", return_value=hooks),
    ):
        response = client.post(
            "/api/models/tokenized-registration-events",
            json=payload,
            headers={"Authorization": "Bearer test-key"},
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "Failed to emit model registration event"
    assert "publisher unreachable" not in response.text


def test_tokenized_registration_event_is_retry_safe(
    client: TestClient, payload: dict[str, object]
) -> None:
    """Replaying the same payload should remain successful when the hook succeeds."""
    hooks = Mock()
    hooks.on_model_registered_with_baseline.return_value = True

    with (
        patch(
            "src.middleware.auth.APIKeyAuthMiddleware.validate_with_auth_service",
            new=AsyncMock(return_value=_validation_result()),
        ),
        patch("src.api.routes.models.get_registry_hooks", return_value=hooks),
    ):
        first = client.post(
            "/api/models/tokenized-registration-events",
            json=payload,
            headers={"Authorization": "Bearer test-key"},
        )
        second = client.post(
            "/api/models/tokenized-registration-events",
            json=payload,
            headers={"Authorization": "Bearer test-key"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert hooks.on_model_registered_with_baseline.call_count == 2


def test_legacy_models_register_route_still_works(app: FastAPI) -> None:
    """The legacy baseline registration route must remain mounted and distinct."""
    client = TestClient(app)
    registration_data = {
        "model_name": "new_model",
        "model_type": "lead_scoring",
        "model_data": {"path": "s3://models/new_model.pkl"},
        "metadata": {"version": "1.0.0"},
    }

    with (
        patch(
            "src.middleware.auth.APIKeyAuthMiddleware.validate_with_auth_service",
            new=AsyncMock(return_value=_validation_result()),
        ),
        patch("src.api.routes.models._get_registry") as mock_get_registry,
    ):
        mock_registry = mock_get_registry.return_value
        mock_registry.register_baseline.return_value = {
            "model_id": "new_model/1",
            "model_name": "new_model",
            "version": "1",
            "registration_timestamp": "2024-01-01T00:00:00Z",
        }
        response = client.post(
            "/models/register",
            json=registration_data,
            headers={"Authorization": "Bearer test-key"},
        )

    assert response.status_code == 201
    assert response.json()["model_id"] == "new_model/1"
