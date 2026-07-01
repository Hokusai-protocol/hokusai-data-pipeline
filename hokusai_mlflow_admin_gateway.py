"""Admin authentication gateway for the standalone MLflow server.

This module wraps MLflow's FastAPI app so direct traffic to the MLflow
container is protected even when a load balancer route bypasses the Hokusai
API proxy.
"""

import json
import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass

import httpx
from mlflow.server.fastapi_app import app as mlflow_app
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("hokusai.mlflow_admin_gateway")


def _split_env_list(value: str) -> list[str]:
    return [item.strip().strip("\"'") for item in value.split(",") if item.strip()]


def _normalize_email(email: str) -> str:
    return email.strip().strip("\"'").lower()


def _json_body(payload: dict[str, object]) -> bytes:
    return json.dumps(payload).encode("utf-8")


async def _send_json(
    send: Send,
    status: int,
    payload: dict[str, object],
    headers: Iterable[tuple[bytes, bytes]] = (),
) -> None:
    body = _json_body(payload)
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                *headers,
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


@dataclass
class ValidationResult:
    """Result returned by the Hokusai auth service."""

    is_valid: bool
    user_id: str | None = None
    email: str | None = None
    key_id: str | None = None
    scopes: list[str] | None = None
    roles: list[str] | None = None
    is_admin: bool = False
    error: str | None = None
    error_type: str | None = None


class MLflowAdminAuthMiddleware:
    """Require a validated admin API key before serving MLflow content."""

    def __init__(self: "MLflowAdminAuthMiddleware", app: ASGIApp) -> None:
        self.app = app
        self.enabled = os.getenv("MLFLOW_ADMIN_AUTH_ENABLED", "true").lower() == "true"
        self.auth_service_url = (
            os.getenv("HOKUSAI_AUTH_SERVICE_URL") or "https://auth.hokus.ai"
        ).rstrip("/")
        self.timeout = float(os.getenv("HOKUSAI_AUTH_SERVICE_TIMEOUT", "5.0"))
        self.service_id = os.getenv("HOKUSAI_AUTH_SERVICE_ID", "platform")
        self.health_paths = set(
            _split_env_list(os.getenv("MLFLOW_ADMIN_AUTH_HEALTH_PATHS", "/health,/mlflow/health"))
        )
        self.admin_emails = {
            _normalize_email(email)
            for email in _split_env_list(
                os.getenv("REGISTRY_ADMIN_USER_EMAILS")
                or os.getenv("REGISTRY_ADMIN_USER_EMAIL")
                or os.getenv("ADMIN_BLOG_USER_EMAILS")
                or os.getenv("ADMIN_BLOG_USER_EMAIL")
                or "me@timogilvie.com"
            )
        }
        self.admin_scopes = set(
            _split_env_list(
                os.getenv(
                    "REGISTRY_ADMIN_SCOPES",
                    "admin,mlflow:admin,registry:admin,model-registry:admin",
                )
            )
        )

    async def __call__(
        self: "MLflowAdminAuthMiddleware", scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self.health_paths:
            await _send_json(send, 200, {"status": "ok"})
            return
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        api_key = self._extract_api_key(scope)
        if not api_key:
            await _send_json(send, 401, {"detail": "API key required"})
            return

        validation = await self._validate_api_key(api_key, scope)
        if not validation.is_valid:
            if validation.error_type == "unavailable":
                await _send_json(
                    send,
                    503,
                    {"detail": validation.error or "Authentication service unavailable"},
                    headers=((b"retry-after", b"1"),),
                )
                return
            await _send_json(send, 401, {"detail": validation.error or "Invalid API key"})
            return

        if not self._is_registry_admin(validation):
            logger.warning(
                "MLflow admin access denied: user_id=%s key_id=%s path=%s scopes=%s roles=%s",
                validation.user_id,
                validation.key_id,
                path,
                validation.scopes,
                validation.roles,
            )
            await _send_json(
                send,
                403,
                {
                    "detail": "Admin access required for the model registry",
                    "error": "REGISTRY_ADMIN_REQUIRED",
                },
            )
            return

        await self.app(scope, receive, send)

    def _extract_api_key(self: "MLflowAdminAuthMiddleware", scope: Scope) -> str | None:
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        auth_header = headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        if auth_header.startswith("ApiKey "):
            return auth_header[7:]
        if headers.get("x-api-key"):
            return headers["x-api-key"]
        return None

    async def _validate_api_key(
        self: "MLflowAdminAuthMiddleware", api_key: str, scope: Scope
    ) -> ValidationResult:
        if not self.auth_service_url:
            logger.error("MLflow admin auth is enabled but HOKUSAI_AUTH_SERVICE_URL is unset")
            return ValidationResult(
                is_valid=False,
                error="Authentication service unavailable",
                error_type="unavailable",
            )

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        client_ip = self._client_ip(scope)
        body = {"service_id": self.service_id}
        if client_ip:
            body["client_ip"] = client_ip

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.auth_service_url}/api/v1/keys/validate",
                    headers=headers,
                    json=body,
                )
        except httpx.TimeoutException:
            logger.error("Auth service request timed out")
            return ValidationResult(
                is_valid=False,
                error="Authentication service timeout",
                error_type="unavailable",
            )
        except Exception as exc:
            logger.error("Auth service error: %s", exc)
            return ValidationResult(
                is_valid=False,
                error="Authentication service unavailable",
                error_type="unavailable",
            )

        if response.status_code == 200:
            data = response.json()
            user_data = data.get("user") if isinstance(data.get("user"), dict) else {}
            return ValidationResult(
                is_valid=True,
                user_id=data.get("user_id") or user_data.get("id"),
                email=data.get("email") or user_data.get("email"),
                key_id=data.get("key_id"),
                scopes=data.get("scopes", []),
                roles=data.get("roles") or user_data.get("roles") or [],
                is_admin=bool(data.get("is_admin") or user_data.get("is_admin")),
            )
        if response.status_code == 401:
            return ValidationResult(is_valid=False, error="Invalid or expired API key")
        if response.status_code == 429:
            return ValidationResult(
                is_valid=False,
                error="Rate limit exceeded",
                error_type="rate_limited",
            )
        logger.error(
            "Auth service returned %s while validating MLflow access", response.status_code
        )
        return ValidationResult(
            is_valid=False,
            error="Authentication service error",
            error_type="unavailable" if response.status_code >= 500 else None,
        )

    def _client_ip(self: "MLflowAdminAuthMiddleware", scope: Scope) -> str | None:
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        forwarded_for = headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded_for:
            return forwarded_for
        client = scope.get("client")
        if isinstance(client, tuple) and client:
            return str(client[0])
        return None

    def _is_registry_admin(self: "MLflowAdminAuthMiddleware", validation: ValidationResult) -> bool:
        if validation.is_admin:
            return True
        email = _normalize_email(validation.email or "")
        if email and email in self.admin_emails:
            return True
        granted_scopes = set(validation.scopes or []) | set(validation.roles or [])
        return bool(granted_scopes & self.admin_scopes)


app = MLflowAdminAuthMiddleware(mlflow_app)
