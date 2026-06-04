"""Integration coverage for the local Model 27 MLflow serving path.

Production MLflow auth relies on environment wiring such as
`MLFLOW_TRACKING_TOKEN`; this test exercises a local saved pyfunc instead.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import mlflow
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_contributor_logger
from src.api.endpoints import model_serving
from src.api.endpoints.sales_lead_scoring_adapter import reset_model_27_cache
from src.middleware.auth import require_auth

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "test_fixtures" / "model_27_payload.json"
)


class FakeContributorLogger:
    @staticmethod
    def new_inference_log_id():
        return uuid4()

    def log_inference(self, **_: object) -> None:
        return None


class SalesLeadScoringSmokeModel(mlflow.pyfunc.PythonModel):
    """Minimal pyfunc that returns a stable probability for model 27 tests."""

    def predict(self, context, model_input):  # noqa: ANN001
        del context
        rows = len(model_input.index) if hasattr(model_input, "index") else 1
        return pd.DataFrame([{"probability": 0.84} for _ in range(rows)])


@pytest.fixture(autouse=True)
def restore_model_configs():
    original_entries = dict(model_serving.MODEL_CONFIGS)
    reset_model_27_cache()
    yield
    reset_model_27_cache()
    model_serving.MODEL_CONFIGS.clear()
    model_serving.MODEL_CONFIGS.update(original_entries)


@pytest.mark.live_mlflow
@pytest.mark.requires_mlflow
def test_model_27_prediction_round_trip_via_saved_pyfunc(tmp_path, monkeypatch) -> None:
    model_path = tmp_path / f"model-27-{uuid4().hex[:8]}"
    mlflow.pyfunc.save_model(path=str(model_path), python_model=SalesLeadScoringSmokeModel())
    model_uri = model_path.as_uri()
    monkeypatch.setenv("MODEL_27_MLFLOW_URI", model_uri)
    updated_entry = replace(
        model_serving.MODEL_CONFIGS["27"],
        model_uri=model_uri,
    )
    model_serving.MODEL_CONFIGS["27"] = updated_entry

    app = FastAPI()
    app.include_router(model_serving.router)
    app.dependency_overrides[require_auth] = lambda: {
        "user_id": "integration-user",
        "api_key_id": "integration-key",
        "scopes": ["model:read", "model:write"],
    }
    app.dependency_overrides[get_contributor_logger] = lambda: FakeContributorLogger()
    api_client = TestClient(app)

    payload = {"inputs": json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))}
    response = api_client.post("/api/v1/models/27/predict", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["predictions"]["lead_score"] == 84
    assert body["predictions"]["conversion_probability"] == 0.84
    assert body["predictions"]["recommendation"] == "Hot"
