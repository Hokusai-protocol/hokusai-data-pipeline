"""Integration tests for benchmark spec API routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_benchmark_spec_service, get_current_user
from src.api.routes.benchmarks import router as benchmarks_router

AUTH_HEADER = {"Authorization": "Bearer admin-token"}


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(benchmarks_router)
    get_benchmark_spec_service.cache_clear()
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "admin",
        "token": "admin-token",
        "scopes": ["admin"],
    }
    return TestClient(app)


def _create_payload() -> dict:
    return {
        "model_id": "model-a",
        "dataset_id": "kaggle/mmlu",
        "dataset_version": "sha256:" + "c" * 64,
        "eval_split": "test",
        "metric_name": "accuracy",
        "metric_direction": "higher_is_better",
        "input_schema": {"dataset_metadata": {"min_examples": 1200}},
        "output_schema": {"fields": ["prediction"]},
        "tiebreak_rules": {"min_examples": 1200},
        "is_active": True,
    }


def test_create_and_get_benchmark_spec() -> None:
    client = build_client()

    create_resp = client.post("/api/v1/benchmarks", headers=AUTH_HEADER, json=_create_payload())
    assert create_resp.status_code == 201
    created = create_resp.json()

    get_resp = client.get(f"/api/v1/benchmarks/{created['spec_id']}", headers=AUTH_HEADER)
    assert get_resp.status_code == 200
    fetched = get_resp.json()

    assert fetched["spec_id"] == created["spec_id"]
    assert fetched["metric_name"] == "accuracy"


def test_list_benchmark_specs_by_model() -> None:
    client = build_client()

    payload = _create_payload()
    client.post("/api/v1/benchmarks", headers=AUTH_HEADER, json=payload)
    payload["dataset_version"] = "sha256:" + "d" * 64
    client.post("/api/v1/benchmarks", headers=AUTH_HEADER, json=payload)

    list_resp = client.get("/api/v1/benchmarks?model_id=model-a", headers=AUTH_HEADER)
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["count"] == 2
    assert len(body["items"]) == 2
