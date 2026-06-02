"""Unit coverage for the callable Technical Task Router pyfunc model.

Remote registry auth is supplied by ``MLFLOW_TRACKING_TOKEN`` in integration
paths; these unit tests use local file-backed MLflow.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import mlflow.pyfunc
import pandas as pd

from scripts.model_30.clean_router_dataset import clean_router_datasets
from scripts.model_30.register_technical_task_router import (
    register_model,
    validate_router_dataset_model_ids,
)
from src.models.technical_task_router import (
    ROUTER_DATASET_ARTIFACT,
    TechnicalTaskRouterModel,
)

FIXTURE = Path(__file__).with_name("technical_task_router_fixture.csv")
REAL_MLFLOW_LOAD_MODEL = mlflow.pyfunc.load_model


def _loaded_model(k_neighbors: int = 2) -> TechnicalTaskRouterModel:
    model = TechnicalTaskRouterModel(k_neighbors=k_neighbors)
    model.load_context(SimpleNamespace(artifacts={ROUTER_DATASET_ARTIFACT: str(FIXTURE)}))
    return model


def _feature_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "schema_version": "technical_task_router_inputs/v2",
                "task_descriptor": "{}",
                "task_description": "Refactor a FastAPI billing webhook with tests",
                "task_type": "refactor",
                "language": "python",
                "allowed_models": '["gpt-5.4","claude-sonnet-4-6"]',
                "preferred_models": '["claude-sonnet-4-6"]',
                "max_cost_usd": 1.0,
                "domain": "payments",
                "repo_size_bucket": "large",
                "requires_tests": True,
                "risk_level": "medium",
                "file_count": 6,
                "estimated_complexity": "medium",
                "expected_cost_usd": 0.5,
            }
        ]
    )


def test_load_context_loads_router_dataset_artifact() -> None:
    model = _loaded_model()

    result = model.predict(None, _feature_frame())

    assert list(result.columns) == [
        "selected_model",
        "selected_models",
        "confidence",
        "rationale",
        "estimated_cost_usd",
        "recommended_strategy",
        "alternatives",
        "tradeoffs",
        "nearest_neighbors",
    ]
    assert result.iloc[0]["selected_model"] == "claude-sonnet-4-6"
    assert result.iloc[0]["selected_models"] == ["claude-sonnet-4-6"]
    assert 0.0 <= result.iloc[0]["confidence"] <= 1.0
    assert result.iloc[0]["estimated_cost_usd"] > 0
    assert "nearest Wavemill router row" in result.iloc[0]["rationale"]
    assert result.iloc[0]["recommended_strategy"]["objective"] == "highest_reliability"
    assert result.iloc[0]["nearest_neighbors"]["count"] == 2


def test_strategy_router_respects_available_models_and_requested_stages() -> None:
    model = _loaded_model()
    features = _feature_frame()
    features.loc[0, "available_planner_models"] = '["gpt-5.4"]'
    features.loc[0, "available_coder_models"] = '["gpt-5.4"]'
    features.loc[0, "available_reviewer_models"] = '["claude-sonnet-4-6"]'
    features.loc[0, "workflow_stages"] = '["code"]'
    features.loc[0, "routing_objective"] = "lowest_cost"

    result = model.predict(None, features)
    strategy = result.iloc[0]["recommended_strategy"]

    assert strategy["objective"] == "lowest_cost"
    assert strategy["stages"] == ["code"]
    assert strategy["planner_model"] is None
    assert strategy["reviewer_model"] is None
    assert strategy["coder_model"] == "gpt-5.4"
    assert set(result.iloc[0]["selected_models"]) <= {"gpt-5.4"}
    assert strategy["estimated_cost_usd"] >= 0
    assert 0 <= strategy["estimated_success_under_budget"] <= 1
    assert 0 <= strategy["confidence"] <= 1
    assert set(result.iloc[0]["tradeoffs"]) == {
        "lowest_cost",
        "fastest_completion",
        "highest_reliability",
    }


def test_registration_dataset_validation_accepts_public_model_ids() -> None:
    summary = validate_router_dataset_model_ids(FIXTURE)

    assert summary.row_count == 3
    assert len(summary.sha256) == 64
    assert summary.selected_model_distribution == {
        "planner_model": {"claude-sonnet-4-6": 2, "gpt-5.4": 1},
        "coder_model": {"claude-sonnet-4-6": 2, "gpt-5.4": 1},
        "reviewer_model": {"claude-sonnet-4-6": 2, "gpt-5.4": 1},
    }


def test_registration_dataset_validation_rejects_fake_model_ids(tmp_path: Path) -> None:
    bad_dataset = tmp_path / "bad-router-dataset.csv"
    bad_dataset.write_text(
        "\n".join(
            [
                "available_planner_models,available_coder_models,available_reviewer_models,"
                "planner_model,coder_model,reviewer_model",
                '"[""gpt-5.4""]","[""deep-coder-v2""]","[""<synthetic>""]",'
                "gpt-5.4,fast-coder-v1,deep",
                "",
            ]
        ),
        encoding="utf-8",
    )

    try:
        validate_router_dataset_model_ids(bad_dataset)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected fake model ids to be rejected")

    assert "deep-coder-v2" in message
    assert "<synthetic>" in message
    assert "fast-coder-v1" in message
    assert "reviewer_model='deep'" in message


def test_registration_fails_before_mlflow_logging_for_invalid_model_ids(tmp_path: Path) -> None:
    bad_dataset = tmp_path / "bad-router-dataset.csv"
    bad_dataset.write_text(
        "\n".join(
            [
                "available_planner_models,available_coder_models,available_reviewer_models,"
                "planner_model,coder_model,reviewer_model",
                '"[""gpt-5.4""]","[""gpt-5.4""]","[""gpt-5.4""]",gpt-5.4,gpt-5.4,deep',
                "",
            ]
        ),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        router_dataset=str(bad_dataset),
        tracking_uri=None,
        experiment_name="unused",
        run_name="unused",
        k_neighbors=2,
        smoke=False,
    )

    with (
        patch("scripts.model_30.register_technical_task_router.mlflow.set_experiment") as set_exp,
        patch("scripts.model_30.register_technical_task_router.mlflow.start_run") as start_run,
    ):
        try:
            register_model(args)
        except ValueError as exc:
            message = str(exc)
        else:
            raise AssertionError("expected invalid dataset to fail registration")

    assert "reviewer_model='deep'" in message
    set_exp.assert_not_called()
    start_run.assert_not_called()


def test_registration_logs_dataset_provenance_to_mlflow() -> None:
    class RunContext:
        def __enter__(self: RunContext) -> SimpleNamespace:
            return SimpleNamespace(info=SimpleNamespace(run_id="run-123"))

        def __exit__(self: RunContext, *args: Any) -> None:
            return None

    args = SimpleNamespace(
        router_dataset=str(FIXTURE),
        tracking_uri=None,
        experiment_name="technical-task-router-test",
        run_name="test-run",
        k_neighbors=2,
        smoke=False,
    )
    model_info = SimpleNamespace(model_uri="runs:/run-123/model", registered_model_version="7")

    with (
        patch("scripts.model_30.register_technical_task_router.mlflow.set_experiment"),
        patch("scripts.model_30.register_technical_task_router.mlflow.start_run") as start_run,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_param") as log_param,
        patch("scripts.model_30.register_technical_task_router.mlflow.set_tag") as set_tag,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_dict") as log_dict,
        patch(
            "scripts.model_30.register_technical_task_router.mlflow.pyfunc.log_model",
            return_value=model_info,
        ),
    ):
        start_run.return_value = RunContext()
        result = register_model(args)

    assert result["registered_model_version"] == "7"
    logged_params = {call.args[0]: call.args[1] for call in log_param.call_args_list}
    logged_tags = {call.args[0]: call.args[1] for call in set_tag.call_args_list}
    assert logged_params["router_dataset_rows"] == 3
    assert str(logged_params["router_dataset_sha256"]).startswith("sha256:")
    assert "claude-sonnet-4-6" in logged_params["router_dataset_model_distribution"]
    assert logged_tags["hokusai.dataset.id"] == "wavemill-hokusai-router-dataset-v1"
    assert logged_tags["hokusai.dataset.num_samples"] == "3"
    log_dict.assert_called_once()


def test_registration_logs_holdout_evaluation_metrics_to_mlflow() -> None:
    class RunContext:
        def __enter__(self: RunContext) -> SimpleNamespace:
            return SimpleNamespace(info=SimpleNamespace(run_id="run-123"))

        def __exit__(self: RunContext, *args: Any) -> None:
            return None

    args = SimpleNamespace(
        router_dataset=str(FIXTURE),
        holdout_dataset=str(FIXTURE),
        evaluation_objectives="highest_reliability",
        tracking_uri=None,
        experiment_name="technical-task-router-test",
        run_name="test-run",
        k_neighbors=2,
        smoke=False,
    )
    model_info = SimpleNamespace(model_uri="runs:/run-123/model", registered_model_version="7")

    with (
        patch("scripts.model_30.register_technical_task_router.mlflow.set_experiment"),
        patch("scripts.model_30.register_technical_task_router.mlflow.start_run") as start_run,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_param"),
        patch("scripts.model_30.register_technical_task_router.mlflow.set_tag") as set_tag,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_metric") as log_metric,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_dict") as log_dict,
        patch(
            "scripts.model_30.register_technical_task_router.mlflow.pyfunc.log_model",
            return_value=model_info,
        ),
    ):
        start_run.return_value = RunContext()
        result = register_model(args)

    logged_metrics = {call.args[0]: call.args[1] for call in log_metric.call_args_list}
    logged_tags = {call.args[0]: call.args[1] for call in set_tag.call_args_list}
    assert result["evaluation_report"]["row_counts"]["evaluated_rows"] == 3
    assert "technical_task_router.benchmark_score_v1" in logged_metrics
    assert logged_tags["hokusai.model_30.holdout_rows"] == "3"
    assert logged_tags["hokusai.model_30.quarantined_rows"] == "0"
    assert log_dict.call_count == 2


def test_clean_router_dataset_merges_removes_available_fakes_and_drops_bad_labels(
    tmp_path: Path,
) -> None:
    dirty_dataset = tmp_path / "dirty-router-dataset.csv"
    clean_dataset = tmp_path / "clean-router-dataset.csv"
    report_path = tmp_path / "clean-router-dataset.report.json"
    dirty_dataset.write_text(
        "\n".join(
            [
                "available_planner_models,available_coder_models,available_reviewer_models,"
                "planner_model,coder_model,reviewer_model,task_type,completed_successfully,score",
                '"[""gpt-5.4"",""<synthetic>""]","[""gpt-5.4""]","[""gpt-5.4""]",'
                "gpt-5.4,gpt-5.4,gpt-5.4,feature,true,0.9",
                '"[""gpt-5.4""]","[""gpt-5.4""]","[""gpt-5.4""]",'
                "gpt-5.4,gpt-5.4,deep,feature,true,0.9",
                "",
            ]
        ),
        encoding="utf-8",
    )

    report = clean_router_datasets([dirty_dataset, dirty_dataset], clean_dataset, report_path)
    summary = validate_router_dataset_model_ids(clean_dataset)

    assert report["input_rows"] == 4
    assert report["output_rows"] == 1
    assert report["duplicate_rows_skipped"] == 1
    assert report["dropped_rows"] == 2
    assert report["removed_available_model_ids"] == {"<synthetic>": 2}
    assert report["drop_reasons"] == {"reviewer_model:invalid:deep": 2}
    assert summary.row_count == 1
    assert "<synthetic>" not in clean_dataset.read_text(encoding="utf-8")
    assert json.loads(report_path.read_text(encoding="utf-8"))["output_rows"] == 1


def test_predict_honors_unseen_allowed_model_when_history_has_no_match() -> None:
    model = _loaded_model()
    features = _feature_frame()
    features.loc[0, "allowed_models"] = '["gpt-5.5"]'
    features.loc[0, "preferred_models"] = '["gpt-5.5"]'

    result = model.predict(None, features)

    assert result.iloc[0]["selected_model"] == "gpt-5.5"
    assert result.iloc[0]["selected_models"] == ["gpt-5.5"]


def test_mlflow_pyfunc_save_load_and_predict_smoke(tmp_path: Path) -> None:
    model_path = tmp_path / "technical-task-router-model"
    mlflow.pyfunc.save_model(
        path=str(model_path),
        python_model=TechnicalTaskRouterModel(k_neighbors=2),
        artifacts={ROUTER_DATASET_ARTIFACT: str(FIXTURE)},
        input_example=_feature_frame(),
    )

    loaded = REAL_MLFLOW_LOAD_MODEL(str(model_path))
    result = loaded.predict(_feature_frame())

    assert result.iloc[0]["selected_model"] == "claude-sonnet-4-6"
    assert result.iloc[0]["selected_models"] == ["claude-sonnet-4-6"]
