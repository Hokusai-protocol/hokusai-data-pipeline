"""Unit tests for model 30 MLflow adapter behavior.

These tests patch MLflow calls locally; deployed MLflow auth still comes from
shared env such as `MLFLOW_TRACKING_TOKEN`.
"""

from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.api.endpoints import model_30_adapter
from src.api.schemas.technical_task_router_inputs import TechnicalTaskRouterPredictions


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
            "available_models": ["gpt-5.4", "claude-sonnet-4-6"],
            "preferred_models": ["claude-sonnet-4-6"],
            "max_cost_usd": 0.5,
            "max_latency_seconds": 30,
            "objective": "highest_reliability",
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


def test_validate_nested_inputs_accepts_minimal_task() -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(_minimal_inputs())

    assert validated.task.description == "Implement password reset flow"
    assert validated.routing is None


def test_validate_nested_inputs_accepts_all_allowed_groups() -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(_full_inputs())

    assert validated.workflow is not None
    assert validated.metadata is not None
    assert validated.routing is not None
    assert validated.routing.objective.value == "highest_reliability"


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
                "allowed_models": ["gpt-5.4"],
                "selected_models": ["gpt-5.4"],
                "max_cost_usd": 0.5,
            }
        )

    assert "Extra inputs are not permitted" in str(excinfo.value)


def test_validate_nested_inputs_rejects_mixed_nested_and_flat_payload() -> None:
    with pytest.raises(Exception) as excinfo:
        model_30_adapter.validate_nested_model_30_inputs(
            {
                **_minimal_inputs(),
                "allowed_models": ["gpt-5.4"],
            }
        )

    assert "Extra inputs are not permitted" in str(excinfo.value)


@pytest.mark.parametrize(
    "obsolete_group",
    [
        {"prediction": {"expected_cost_usd": 0.45}},
        {"outcome": {"completed_successfully": True}},
        {"rubric": {"quality_score": 0.9}},
    ],
)
def test_validate_nested_inputs_rejects_historical_outcome_groups(
    obsolete_group: dict,
) -> None:
    with pytest.raises(Exception) as excinfo:
        model_30_adapter.validate_nested_model_30_inputs(
            {
                **_minimal_inputs(),
                **obsolete_group,
            }
        )

    assert "Extra inputs are not permitted" in str(excinfo.value)


def test_validate_nested_inputs_rejects_unknown_objective() -> None:
    with pytest.raises(Exception) as excinfo:
        model_30_adapter.validate_nested_model_30_inputs(
            {
                **_minimal_inputs(),
                "routing": {"objective": "balanced"},
            }
        )

    assert "lowest_cost" in str(excinfo.value)


def test_validate_nested_inputs_rejects_unknown_or_duplicate_stages() -> None:
    with pytest.raises(Exception) as unknown_exc:
        model_30_adapter.validate_nested_model_30_inputs(
            {
                **_minimal_inputs(),
                "workflow": {"stages": ["plan", "deploy"]},
            }
        )
    with pytest.raises(Exception) as duplicate_exc:
        model_30_adapter.validate_nested_model_30_inputs(
            {
                **_minimal_inputs(),
                "workflow": {"stages": ["plan", "plan"]},
            }
        )

    assert "review" in str(unknown_exc.value)
    assert "must not contain duplicates" in str(duplicate_exc.value)


def test_model_30_inputs_to_features_maps_nested_payload_to_signature_shape() -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(_full_inputs())

    features = model_30_adapter.model_30_inputs_to_features(validated)

    assert isinstance(features, pd.DataFrame)
    assert list(features.columns) == list(model_30_adapter.ROUTER_FEATURE_COLUMNS)
    row = features.iloc[0].to_dict()
    assert row["available_planner_models"] == ["claude-sonnet-4-6", "gpt-5.4"]
    assert row["available_coder_models"] == ["claude-sonnet-4-6", "gpt-5.4"]
    assert row["available_reviewer_models"] == ["claude-sonnet-4-6", "gpt-5.4"]
    assert row["complexity"] == "medium"
    assert row["files_touched_bucket"] == "6_15"
    assert row["max_cost_usd"] == 0.5
    assert row["task_type"] == "refactor"
    assert row["surface"] == "wavemill"


def test_model_30_inputs_to_features_honors_role_specific_available_models() -> None:
    payload = _full_inputs()
    payload["routing"]["available_planner_models"] = ["claude-sonnet-4-6"]
    payload["routing"]["available_coder_models"] = ["gpt-5.4"]
    payload["routing"]["available_reviewer_models"] = ["claude-haiku-4-5-20251001"]
    validated = model_30_adapter.validate_nested_model_30_inputs(payload)

    features = model_30_adapter.model_30_inputs_to_features(validated)
    row = features.iloc[0].to_dict()

    assert row["available_planner_models"] == ["claude-sonnet-4-6"]
    assert row["available_coder_models"] == ["gpt-5.4"]
    assert row["available_reviewer_models"] == ["claude-haiku-4-5-20251001"]


def test_model_30_inputs_to_features_does_not_require_post_routing_outcomes() -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(_minimal_inputs())

    features = model_30_adapter.model_30_inputs_to_features(validated)

    row = features.iloc[0].to_dict()
    assert row["description_length_bucket"] == "short"
    assert row["available_planner_models"] == []
    assert "selected_models" not in row


def test_router_features_minimal_fixture() -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(_minimal_inputs())

    features = model_30_adapter.map_nested_to_router_features(validated)

    assert tuple(features) == model_30_adapter.ROUTER_FEATURE_COLUMNS
    assert features["task_type"] == "feature"
    assert features["language"] is None
    assert features["complexity"] == "low"
    assert features["description_length_bucket"] == "short"
    assert features["files_touched_bucket"] == "1"
    assert features["available_planner_models"] == []
    assert features["available_coder_models"] == []
    assert features["available_reviewer_models"] == []
    assert features["is_greenfield"] is False
    assert features["is_migration"] is False
    assert features["cross_service"] is False
    assert features["ui_heavy"] is False


def test_router_features_curated_fixture() -> None:
    payload = _full_inputs()
    payload["task"]["description"] = (
        "Migrate legacy auth across services into a new React dashboard from scratch"
    )
    payload["routing"]["available_models"] = [
        "gpt-5.4",
        "claude-sonnet-4-6",
        "gpt-5.4",
    ]
    payload["context"]["file_count"] = 24
    payload["context"]["estimated_complexity"] = "high"
    validated = model_30_adapter.validate_nested_model_30_inputs(payload)

    features = model_30_adapter.map_nested_to_router_features(validated)

    assert features == {
        "task_type": "refactor",
        "language": "python",
        "framework": "fastapi",
        "repo_type": "monorepo",
        "domain": "payments",
        "complexity": "high",
        "description_length_bucket": "short",
        "files_touched_bucket": "16_plus",
        "available_planner_models": ["claude-sonnet-4-6", "gpt-5.4"],
        "available_coder_models": ["claude-sonnet-4-6", "gpt-5.4"],
        "available_reviewer_models": ["claude-sonnet-4-6", "gpt-5.4"],
        "max_cost_usd": 0.5,
        "prioritize_quality": True,
        "prioritize_speed": None,
        "risk_level": "medium",
        "requires_tests": True,
        "security_sensitive": True,
        "repo_size_bucket": "large",
        "surface": "wavemill",
        "workflow_stages": ["plan", "code", "review"],
        "routing_objective": "highest_reliability",
        "is_greenfield": True,
        "is_migration": True,
        "cross_service": True,
        "ui_heavy": True,
    }


@pytest.mark.parametrize("leakage_key", sorted(model_30_adapter._ROUTER_LEAKAGE_COLUMNS))
def test_router_features_no_leakage_keys(leakage_key: str) -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(_full_inputs())

    features = model_30_adapter.map_nested_to_router_features(validated)

    assert leakage_key not in features


@pytest.mark.parametrize(
    ("length", "expected_bucket"),
    [
        (model_30_adapter._DESCRIPTION_SHORT_MAX - 1, "short"),
        (model_30_adapter._DESCRIPTION_SHORT_MAX, "short"),
        (model_30_adapter._DESCRIPTION_SHORT_MAX + 1, "medium"),
        (model_30_adapter._DESCRIPTION_MEDIUM_MAX - 1, "medium"),
        (model_30_adapter._DESCRIPTION_MEDIUM_MAX, "medium"),
        (model_30_adapter._DESCRIPTION_MEDIUM_MAX + 1, "long"),
    ],
)
def test_description_length_bucket_boundaries(length: int, expected_bucket: str) -> None:
    assert model_30_adapter._bucket_description_length(length) == expected_bucket


@pytest.mark.parametrize(
    ("file_count", "expected_bucket"),
    [
        (model_30_adapter._FILES_SMALL_MAX - 1, "2_5"),
        (model_30_adapter._FILES_SMALL_MAX, "2_5"),
        (model_30_adapter._FILES_SMALL_MAX + 1, "6_15"),
        (model_30_adapter._FILES_MEDIUM_MAX - 1, "6_15"),
        (model_30_adapter._FILES_MEDIUM_MAX, "6_15"),
        (model_30_adapter._FILES_MEDIUM_MAX + 1, "16_plus"),
    ],
)
def test_files_touched_bucket_boundaries(file_count: int, expected_bucket: str) -> None:
    assert model_30_adapter._bucket_files_touched(file_count) == expected_bucket


def test_boolean_flags_migration_description() -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(
        {
            "task": {
                "description": "Migrate legacy auth across services with service boundary fixes",
                "task_type": "migration",
            }
        }
    )

    features = model_30_adapter.map_nested_to_router_features(validated)

    assert features["is_migration"] is True
    assert features["cross_service"] is True
    assert features["is_greenfield"] is False
    assert features["ui_heavy"] is False


def test_boolean_flags_greenfield_description() -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(
        {
            "task": {
                "description": "Build a new React dashboard from scratch",
                "task_type": "feature",
            }
        }
    )

    features = model_30_adapter.map_nested_to_router_features(validated)

    assert features["is_greenfield"] is True
    assert features["ui_heavy"] is True
    assert features["is_migration"] is False
    assert features["cross_service"] is False


def test_boolean_flags_empty_description() -> None:
    flags = model_30_adapter._detect_boolean_flags("")

    assert flags == {
        "is_greenfield": False,
        "is_migration": False,
        "cross_service": False,
        "ui_heavy": False,
    }


def test_mapper_is_deterministic() -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(_full_inputs())

    first = model_30_adapter.map_nested_to_router_features(validated)
    second = model_30_adapter.map_nested_to_router_features(validated)

    assert first == second


def test_features_frame_maps_nested_payload_to_router_schema() -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(_full_inputs())

    features = model_30_adapter.model_30_inputs_to_features(validated)

    assert list(features.columns) == list(model_30_adapter.ROUTER_FEATURE_COLUMNS)
    assert set(features.iloc[0].to_dict()) == set(model_30_adapter.ROUTER_FEATURE_COLUMNS)


def test_v2_prediction_response_schema_accepts_strategy_tradeoff_payload() -> None:
    payload = {
        "recommended_strategy": {
            "objective": "highest_reliability",
            "planner_model": "claude-sonnet-4-6",
            "coder_model": "gpt-5.4",
            "reviewer_model": "claude-sonnet-4-6",
            "stages": ["plan", "code", "review"],
            "estimated_success_under_budget": 0.82,
            "estimated_cost_usd": 4.8,
            "estimated_duration_seconds": 1800,
            "confidence": 0.71,
        },
        "alternatives": [
            {
                "objective": "lowest_cost",
                "coder_model": "gpt-5.4",
                "stages": ["code"],
                "estimated_success_under_budget": 0.62,
                "estimated_cost_usd": 1.2,
                "estimated_duration_seconds": 900,
                "confidence": 0.54,
            }
        ],
        "tradeoffs": {
            "lowest_cost": {
                "objective": "lowest_cost",
                "coder_model": "gpt-5.4",
                "stages": ["code"],
                "estimated_success_under_budget": 0.62,
                "estimated_cost_usd": 1.2,
                "confidence": 0.54,
            },
            "fastest_completion": None,
            "highest_reliability": {
                "objective": "highest_reliability",
                "planner_model": "claude-sonnet-4-6",
                "coder_model": "gpt-5.4",
                "reviewer_model": "claude-sonnet-4-6",
                "stages": ["plan", "code", "review"],
                "estimated_success_under_budget": 0.82,
                "estimated_cost_usd": 4.8,
                "confidence": 0.71,
            },
        },
        "nearest_neighbors": {
            "count": 40,
            "success_under_budget_rate": 0.78,
            "mean_cost_usd": 4.4,
            "mean_duration_seconds": 1650,
        },
    }

    parsed = TechnicalTaskRouterPredictions.model_validate(payload)

    assert parsed.recommended_strategy.objective.value == "highest_reliability"
    assert parsed.nearest_neighbors.count == 40


def test_normalize_output_handles_dataframe() -> None:
    raw = pd.DataFrame(
        [
            {
                "model": "claude-sonnet-4-6",
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
        "selected_model": "claude-sonnet-4-6",
        "selected_models": ["claude-sonnet-4-6"],
        "confidence": 0.91,
        "rationale": "best match",
        "estimated_cost_usd": 0.42,
    }


def test_normalize_output_handles_list_of_dicts() -> None:
    normalized = model_30_adapter.normalize_model_30_output(
        [{"selected_models": ["gpt-5.4"], "probability": 0.75}],
        model_30_adapter.validate_nested_model_30_inputs(_minimal_inputs()),
    )

    assert normalized["selected_model"] == "gpt-5.4"
    assert normalized["confidence"] == 0.75


def test_normalize_output_handles_single_dict() -> None:
    normalized = model_30_adapter.normalize_model_30_output(
        {"prediction": "gpt-5.4", "estimated_cost": 0.25},
        model_30_adapter.validate_nested_model_30_inputs(_minimal_inputs()),
    )

    assert normalized["selected_models"] == ["gpt-5.4"]
    assert normalized["estimated_cost_usd"] == 0.25


def test_normalize_output_handles_ndarray_or_scalar_model_id() -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(_minimal_inputs())

    array_normalized = model_30_adapter.normalize_model_30_output(
        np.array(["deepseek-reasoner"]),
        validated,
    )
    scalar_normalized = model_30_adapter.normalize_model_30_output("gpt-5.4", validated)

    assert array_normalized["selected_model"] == "deepseek-reasoner"
    assert scalar_normalized["selected_model"] == "gpt-5.4"


def test_normalize_output_rejects_empty_output() -> None:
    with pytest.raises(ValueError, match="empty"):
        model_30_adapter.normalize_model_30_output(
            [],
            model_30_adapter.validate_nested_model_30_inputs(_minimal_inputs()),
        )


def test_pyfunc_cache_loads_once_per_uri() -> None:
    fake_model = SimpleNamespace(predict=lambda _: {"selected_model": "gpt-5.4"})

    with patch(
        "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
        return_value=fake_model,
    ) as load_mock:
        model_30_adapter.call_mlflow_model_30("models:/Technical Task Router/4", {"row": 1})
        model_30_adapter.call_mlflow_model_30("models:/Technical Task Router/4", {"row": 2})

    load_mock.assert_called_once_with("models:/Technical Task Router/4")


def test_pyfunc_cache_loads_distinct_uris_separately() -> None:
    fake_model = SimpleNamespace(predict=lambda _: {"selected_model": "gpt-5.4"})

    with patch(
        "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
        return_value=fake_model,
    ) as load_mock:
        model_30_adapter.call_mlflow_model_30("models:/Technical Task Router/4", {"row": 1})
        model_30_adapter.call_mlflow_model_30("models:/Technical Task Router/3", {"row": 2})

    assert load_mock.call_count == 2


def test_pyfunc_cache_is_thread_safe_on_cold_start() -> None:
    fake_model = SimpleNamespace(predict=lambda _: {"selected_model": "gpt-5.4"})
    load_calls: list[str] = []
    results: list[str] = []
    start_event = threading.Event()

    def fake_load_model(uri: str) -> object:
        time.sleep(0.05)
        load_calls.append(uri)
        return fake_model

    def worker() -> None:
        start_event.wait()
        try:
            model_30_adapter.call_mlflow_model_30("models:/Technical Task Router/4", {"row": 1})
            results.append("loaded")
        except model_30_adapter.Model30LoadInProgressError:
            results.append("in_progress")

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

    assert load_calls == ["models:/Technical Task Router/4"]
    assert sorted(results) == ["in_progress", "in_progress", "loaded"]


def test_call_mlflow_model_30_calls_predict() -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = {"selected_model": "gpt-5.4"}

    with patch(
        "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
        return_value=fake_model,
    ):
        result = model_30_adapter.call_mlflow_model_30(
            "models:/Technical Task Router/4",
            {"row": 1},
        )

    fake_model.predict.assert_called_once_with({"row": 1})
    assert result == {"selected_model": "gpt-5.4"}


def test_call_mlflow_model_30_populates_timing_fields() -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = {"selected_model": "gpt-5.4"}
    timings: dict[str, float] = {}

    with patch(
        "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
        return_value=fake_model,
    ):
        model_30_adapter.call_mlflow_model_30(
            "models:/Technical Task Router/4",
            {"row": 1},
            timings,
        )

    assert "artifact_load_ms" in timings
    assert "inference_only_ms" in timings
    assert timings["artifact_load_ms"] >= 0.0
    assert timings["inference_only_ms"] >= 0.0


def test_call_mlflow_model_30_warm_path_keeps_artifact_load_small() -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = {"selected_model": "gpt-5.4"}
    timings: dict[str, float] = {}

    with patch(
        "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
        return_value=fake_model,
    ):
        model_30_adapter.call_mlflow_model_30("models:/Technical Task Router/4", {"row": 1})
        model_30_adapter.call_mlflow_model_30(
            "models:/Technical Task Router/4",
            {"row": 2},
            timings,
        )

    assert timings["artifact_load_ms"] < 5.0
    assert timings["inference_only_ms"] >= 0.0


def test_call_mlflow_model_30_does_not_mutate_mlflow_environment(monkeypatch) -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = {"selected_model": "gpt-5.4"}
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.delenv("MLFLOW_HTTP_REQUEST_BACKOFF_JITTER", raising=False)
    monkeypatch.delenv("MLFLOW_ARTIFACT_UPLOAD_DOWNLOAD_TIMEOUT", raising=False)

    with patch(
        "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
        return_value=fake_model,
    ):
        model_30_adapter.call_mlflow_model_30("models:/Technical Task Router/4", {"row": 1})

    assert "MLFLOW_TRACKING_URI" not in os.environ
    assert "MLFLOW_HTTP_REQUEST_BACKOFF_JITTER" not in os.environ
    assert "MLFLOW_ARTIFACT_UPLOAD_DOWNLOAD_TIMEOUT" not in os.environ


def test_call_mlflow_model_30_does_not_mutate_global_tracking_uri(monkeypatch) -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = {"selected_model": "gpt-5.4"}
    monkeypatch.setenv("MLFLOW_SERVER_URL", "https://mlflow.hokusai-development.local:5000")

    with (
        patch("src.api.endpoints.model_30_adapter.mlflow.set_tracking_uri") as set_uri_mock,
        patch(
            "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
            return_value=fake_model,
        ),
    ):
        model_30_adapter.call_mlflow_model_30("models:/Technical Task Router/4", {"row": 1})

    set_uri_mock.assert_not_called()


def test_call_mlflow_model_30_propagates_predict_errors() -> None:
    fake_model = MagicMock()
    fake_model.predict.side_effect = RuntimeError("boom")

    with patch(
        "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
        return_value=fake_model,
    ):
        with pytest.raises(RuntimeError, match="boom"):
            model_30_adapter.call_mlflow_model_30(
                "models:/Technical Task Router/4",
                {"row": 1},
            )
