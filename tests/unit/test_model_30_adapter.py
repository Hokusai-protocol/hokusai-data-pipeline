"""Unit tests for model 30 MLflow adapter behavior.

These tests patch MLflow calls locally; deployed MLflow auth still comes from
shared env such as `MLFLOW_TRACKING_TOKEN`.
"""

from __future__ import annotations

import json
import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.api.endpoints import model_30_adapter


def _minimal_inputs() -> dict:
    return {
        "task": {
            "description": "Implement password reset flow",
            "task_type": "feature",
        }
    }


def _full_inputs() -> dict:
    return {
        "task": {
            "description": "Refactor billing webhook retry handling",
            "task_type": "refactor",
            "language": "python",
            "framework": "fastapi",
            "repo_type": "monorepo",
        },
        "routing": {
            "available_models": ["fast-coder-v1", "deep-coder-v2"],
            "preferred_models": ["deep-coder-v2"],
            "max_cost_usd": 0.5,
            "max_latency_seconds": 30,
            "prioritize_quality": True,
        },
        "context": {
            "domain": "payments",
            "repo_size_bucket": "large",
            "requires_tests": True,
            "risk_level": "medium",
            "file_count": 6,
            "estimated_complexity": "medium",
            "security_sensitive": True,
        },
        "workflow": {
            "surface": "wavemill",
            "stages": ["plan", "code", "review"],
            "execution_environment": "ci",
            "human_review_required": True,
        },
        "prediction": {
            "expected_duration_seconds": 1800,
            "expected_cost_usd": 0.45,
            "expected_success_probability": 0.8,
        },
        "outcome": {
            "completed_successfully": False,
            "actual_cost_usd": 0.0,
            "actual_time_seconds": 0.0,
            "retry_count": 0,
            "intervention_required": False,
            "selected_model": "deep-coder-v2",
        },
        "rubric": {
            "quality_score": 0.9,
            "correctness_score": 0.85,
            "human_rating": "strong",
            "benchmark_passed": True,
        },
        "metadata": {
            "external_task_id": "task-123",
            "run_id": "run-456",
            "integration_version": "2026.05",
            "idempotency_key": "idem-789",
        },
    }


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    model_30_adapter.reset_model_30_cache()
    model_30_adapter._MLFLOW_CLIENT_CONFIGURED = False


def test_validate_nested_inputs_accepts_minimal_task() -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(_minimal_inputs())

    assert validated.task.description == "Implement password reset flow"
    assert validated.routing is None


def test_validate_nested_inputs_accepts_all_allowed_groups() -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(_full_inputs())

    assert validated.workflow is not None
    assert validated.metadata is not None


def test_validate_nested_inputs_rejects_missing_task() -> None:
    with pytest.raises(Exception) as excinfo:
        model_30_adapter.validate_nested_model_30_inputs({"routing": {"max_cost_usd": 0.5}})

    assert "task" in str(excinfo.value)


def test_validate_nested_inputs_rejects_flat_benchmark_row() -> None:
    with pytest.raises(Exception) as excinfo:
        model_30_adapter.validate_nested_model_30_inputs(
            {
                "schema_version": "technical_task_router_row/v1",
                "task_descriptor": {"task_type": "feature"},
                "allowed_models": ["fast-coder-v1"],
                "selected_models": ["fast-coder-v1"],
                "max_cost_usd": 0.5,
            }
        )

    assert "Extra inputs are not permitted" in str(excinfo.value)


def test_validate_nested_inputs_rejects_mixed_nested_and_flat_payload() -> None:
    with pytest.raises(Exception) as excinfo:
        model_30_adapter.validate_nested_model_30_inputs(
            {
                **_minimal_inputs(),
                "allowed_models": ["fast-coder-v1"],
            }
        )

    assert "Extra inputs are not permitted" in str(excinfo.value)


def test_model_30_inputs_to_features_maps_nested_payload_to_signature_shape() -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(_full_inputs())

    features = model_30_adapter.model_30_inputs_to_features(validated)

    assert isinstance(features, pd.DataFrame)
    assert list(features["schema_version"]) == [model_30_adapter.MODEL_30_SCHEMA]
    row = features.iloc[0].to_dict()
    assert (
        json.loads(row["task_descriptor"])["description"]
        == "Refactor billing webhook retry handling"
    )
    assert json.loads(row["allowed_models"]) == ["fast-coder-v1", "deep-coder-v2"]
    assert row["max_cost_usd"] == 0.5
    assert row["task_type"] == "refactor"
    assert row["surface"] == "wavemill"


def test_model_30_inputs_to_features_does_not_require_post_routing_outcomes() -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(_minimal_inputs())

    features = model_30_adapter.model_30_inputs_to_features(validated)

    row = features.iloc[0].to_dict()
    assert row["task_description"] == "Implement password reset flow"
    assert row["allowed_models"] == json.dumps([])
    assert "selected_models" not in row


def test_normalize_output_handles_dataframe() -> None:
    raw = pd.DataFrame(
        [
            {
                "model": "deep-coder-v2",
                "score": 0.91,
                "reason": "best match",
                "cost": 0.42,
            }
        ]
    )

    normalized = model_30_adapter.normalize_model_30_output(
        raw,
        model_30_adapter.validate_nested_model_30_inputs(_minimal_inputs()),
    )

    assert normalized == {
        "selected_model": "deep-coder-v2",
        "selected_models": ["deep-coder-v2"],
        "confidence": 0.91,
        "rationale": "best match",
        "estimated_cost_usd": 0.42,
    }


def test_normalize_output_handles_list_of_dicts() -> None:
    normalized = model_30_adapter.normalize_model_30_output(
        [{"selected_models": ["fast-coder-v1"], "probability": 0.75}],
        model_30_adapter.validate_nested_model_30_inputs(_minimal_inputs()),
    )

    assert normalized["selected_model"] == "fast-coder-v1"
    assert normalized["confidence"] == 0.75


def test_normalize_output_handles_single_dict() -> None:
    normalized = model_30_adapter.normalize_model_30_output(
        {"prediction": "fast-coder-v1", "estimated_cost": 0.25},
        model_30_adapter.validate_nested_model_30_inputs(_minimal_inputs()),
    )

    assert normalized["selected_models"] == ["fast-coder-v1"]
    assert normalized["estimated_cost_usd"] == 0.25


def test_normalize_output_handles_ndarray_or_scalar_model_id() -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(_minimal_inputs())

    array_normalized = model_30_adapter.normalize_model_30_output(
        np.array(["db-specialist-v1"]),
        validated,
    )
    scalar_normalized = model_30_adapter.normalize_model_30_output("fast-coder-v1", validated)

    assert array_normalized["selected_model"] == "db-specialist-v1"
    assert scalar_normalized["selected_model"] == "fast-coder-v1"


def test_normalize_output_rejects_empty_output() -> None:
    with pytest.raises(ValueError, match="empty"):
        model_30_adapter.normalize_model_30_output(
            [],
            model_30_adapter.validate_nested_model_30_inputs(_minimal_inputs()),
        )


def test_pyfunc_cache_loads_once_per_uri() -> None:
    fake_model = SimpleNamespace(predict=lambda _: {"selected_model": "fast-coder-v1"})

    with patch(
        "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
        return_value=fake_model,
    ) as load_mock:
        model_30_adapter.call_mlflow_model_30("models:/Technical Task Router/1", {"row": 1})
        model_30_adapter.call_mlflow_model_30("models:/Technical Task Router/1", {"row": 2})

    load_mock.assert_called_once_with("models:/Technical Task Router/1")


def test_pyfunc_cache_loads_distinct_uris_separately() -> None:
    fake_model = SimpleNamespace(predict=lambda _: {"selected_model": "fast-coder-v1"})

    with patch(
        "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
        return_value=fake_model,
    ) as load_mock:
        model_30_adapter.call_mlflow_model_30("models:/Technical Task Router/1", {"row": 1})
        model_30_adapter.call_mlflow_model_30("models:/Technical Task Router/2", {"row": 2})

    assert load_mock.call_count == 2


def test_pyfunc_cache_is_thread_safe_on_cold_start() -> None:
    fake_model = SimpleNamespace(predict=lambda _: {"selected_model": "fast-coder-v1"})
    load_calls: list[str] = []
    start_event = threading.Event()

    def fake_load_model(uri: str) -> object:
        time.sleep(0.05)
        load_calls.append(uri)
        return fake_model

    def worker() -> None:
        start_event.wait()
        model_30_adapter.call_mlflow_model_30("models:/Technical Task Router/1", {"row": 1})

    with patch(
        "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
        side_effect=fake_load_model,
    ):
        threads = [threading.Thread(target=worker) for _ in range(3)]
        for thread in threads:
            thread.start()
        start_event.set()
        for thread in threads:
            thread.join()

    assert load_calls == ["models:/Technical Task Router/1"]


def test_call_mlflow_model_30_calls_predict() -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = {"selected_model": "fast-coder-v1"}

    with patch(
        "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
        return_value=fake_model,
    ):
        result = model_30_adapter.call_mlflow_model_30(
            "models:/Technical Task Router/1",
            {"row": 1},
        )

    fake_model.predict.assert_called_once_with({"row": 1})
    assert result == {"selected_model": "fast-coder-v1"}


def test_call_mlflow_model_30_configures_sdk_from_deployment_env(monkeypatch) -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = {"selected_model": "fast-coder-v1"}
    monkeypatch.setenv("MLFLOW_SERVER_URL", "https://mlflow.hokusai-development.local:5000")
    monkeypatch.setenv("MLFLOW_CLIENT_CERT_PATH", "/tmp/api-certs/client.crt")
    monkeypatch.setenv("MLFLOW_CLIENT_KEY_PATH", "/tmp/api-certs/client.key")
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.delenv("MLFLOW_TRACKING_CLIENT_CERT_PATH", raising=False)
    monkeypatch.delenv("MLFLOW_TRACKING_CLIENT_KEY_PATH", raising=False)

    with (
        patch("src.api.endpoints.model_30_adapter.mlflow.set_tracking_uri") as set_uri_mock,
        patch(
            "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
            return_value=fake_model,
        ),
    ):
        model_30_adapter.call_mlflow_model_30("models:/Technical Task Router/1", {"row": 1})

    set_uri_mock.assert_called_once_with("https://mlflow.hokusai-development.local:5000")
    assert os.environ["MLFLOW_TRACKING_URI"] == "https://mlflow.hokusai-development.local:5000"
    assert os.environ["MLFLOW_TRACKING_CLIENT_CERT_PATH"] == "/tmp/api-certs/client.crt"
    assert os.environ["MLFLOW_TRACKING_CLIENT_KEY_PATH"] == "/tmp/api-certs/client.key"
    assert os.environ["MLFLOW_TRACKING_INSECURE_TLS"] == "true"


def test_call_mlflow_model_30_propagates_predict_errors() -> None:
    fake_model = MagicMock()
    fake_model.predict.side_effect = RuntimeError("boom")

    with patch(
        "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
        return_value=fake_model,
    ):
        with pytest.raises(RuntimeError, match="boom"):
            model_30_adapter.call_mlflow_model_30(
                "models:/Technical Task Router/1",
                {"row": 1},
            )
