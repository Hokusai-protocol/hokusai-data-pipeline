"""Unit coverage for the callable Technical Task Router pyfunc model.

Remote registry auth is supplied by ``MLFLOW_TRACKING_TOKEN`` in integration
paths; these unit tests use local file-backed MLflow.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import mlflow.pyfunc
import pandas as pd

from scripts.model_30.register_technical_task_router import validate_router_dataset_model_ids
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
    ]
    assert result.iloc[0]["selected_model"] == "claude-sonnet-4-6"
    assert result.iloc[0]["selected_models"] == ["claude-sonnet-4-6"]
    assert 0.0 <= result.iloc[0]["confidence"] <= 1.0
    assert result.iloc[0]["estimated_cost_usd"] > 0
    assert "nearest Wavemill router row" in result.iloc[0]["rationale"]


def test_registration_dataset_validation_accepts_public_model_ids() -> None:
    validate_router_dataset_model_ids(FIXTURE)


def test_registration_dataset_validation_rejects_fake_model_ids(tmp_path: Path) -> None:
    bad_dataset = tmp_path / "bad-router-dataset.csv"
    bad_dataset.write_text(
        "\n".join(
            [
                "available_planner_models,available_coder_models,available_reviewer_models,"
                "planner_model,coder_model,reviewer_model",
                '"[""gpt-5.4""]","[""deep-coder-v2""]","[""claude-sonnet-4-6""]",'
                "gpt-5.4,deep-coder-v2,deep",
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
    assert "reviewer_model='deep'" in message


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
