import httpx
import pytest
from starlette.testclient import TestClient
from starlette.types import Receive, Scope, Send

from hokusai_mlflow_admin_gateway import MLflowAdminAuthMiddleware


async def ok_app(scope: Scope, receive: Receive, send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 204,
            "headers": [(b"content-length", b"0")],
        }
    )
    await send({"type": "http.response.body", "body": b""})


class FakeAuthClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self) -> "FakeAuthClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, *args: object, **kwargs: object) -> httpx.Response:
        return self.response


@pytest.fixture(autouse=True)
def gateway_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLFLOW_ADMIN_AUTH_ENABLED", "true")
    monkeypatch.setenv("HOKUSAI_AUTH_SERVICE_URL", "http://auth.test")
    monkeypatch.setenv("REGISTRY_ADMIN_USER_EMAILS", "admin@hokus.ai")


def test_mlflow_gateway_requires_api_key_for_ui() -> None:
    client = TestClient(MLflowAdminAuthMiddleware(ok_app))

    response = client.get("/mlflow/")

    assert response.status_code == 401
    assert response.json() == {"detail": "API key required"}


def test_mlflow_gateway_allows_health_without_api_key() -> None:
    client = TestClient(MLflowAdminAuthMiddleware(ok_app))

    response = client.get("/mlflow/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    root_health_response = client.get("/health")

    assert root_health_response.status_code == 200
    assert root_health_response.json() == {"status": "ok"}


def test_mlflow_gateway_rejects_non_admin_key(monkeypatch: pytest.MonkeyPatch) -> None:
    auth_response = httpx.Response(
        200,
        json={
            "user_id": "user-1",
            "email": "user@hokus.ai",
            "key_id": "key-1",
            "scopes": ["mlflow:read"],
        },
    )
    monkeypatch.setattr(
        "hokusai_mlflow_admin_gateway.httpx.AsyncClient",
        lambda *args, **kwargs: FakeAuthClient(auth_response),
    )
    client = TestClient(MLflowAdminAuthMiddleware(ok_app))

    response = client.get("/mlflow/", headers={"Authorization": "Bearer hk_test"})

    assert response.status_code == 403
    assert response.json()["error"] == "REGISTRY_ADMIN_REQUIRED"


def test_mlflow_gateway_allows_admin_email(monkeypatch: pytest.MonkeyPatch) -> None:
    auth_response = httpx.Response(
        200,
        json={
            "user_id": "admin-1",
            "email": "admin@hokus.ai",
            "key_id": "key-admin",
            "scopes": ["mlflow:read"],
        },
    )
    monkeypatch.setattr(
        "hokusai_mlflow_admin_gateway.httpx.AsyncClient",
        lambda *args, **kwargs: FakeAuthClient(auth_response),
    )
    client = TestClient(MLflowAdminAuthMiddleware(ok_app))

    response = client.get("/mlflow/", headers={"Authorization": "Bearer hk_admin"})

    assert response.status_code == 204
