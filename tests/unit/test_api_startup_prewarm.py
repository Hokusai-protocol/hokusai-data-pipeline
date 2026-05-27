"""Unit tests for API startup MLflow pre-warm."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def api_main_module(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MLFLOW_SERVER_URL", "https://mlflow.test.local:5000")
    monkeypatch.setenv("MLFLOW_TRACKING_TOKEN", "test-token")
    monkeypatch.setenv("DB_PASSWORD", "test-password")
    sys.modules.pop("src.api.main", None)
    module = importlib.import_module("src.api.main")
    yield module
    sys.modules.pop("src.api.main", None)


def test_prewarm_registered_models_only_hits_mlflow_entries(api_main_module) -> None:
    model_configs = {
        "21": {"name": "HF model", "storage_type": "huggingface_private"},
        "30": {"name": "Technical Task Router", "storage_type": "mlflow"},
        "31": {
            "name": "Ignored display name",
            "storage_type": "mlflow",
            "registered_model_name": "Canonical MLflow Name",
        },
    }
    client = Mock()

    with (
        patch.object(api_main_module, "MODEL_CONFIGS", model_configs),
        patch.object(api_main_module.mlflow, "set_tracking_uri") as set_uri_mock,
        patch.object(api_main_module, "MlflowClient", return_value=client),
    ):
        api_main_module._prewarm_mlflow_registered_models()

    set_uri_mock.assert_called_once_with("https://mlflow.test.local:5000")
    assert client.get_registered_model.call_args_list == [
        (("Technical Task Router",), {}),
        (("Canonical MLflow Name",), {}),
    ]


def test_prewarm_failure_propagates(api_main_module) -> None:
    client = Mock()
    client.get_registered_model.side_effect = RuntimeError("registry down")

    with (
        patch.object(
            api_main_module,
            "MODEL_CONFIGS",
            {"30": {"name": "Technical Task Router", "storage_type": "mlflow"}},
        ),
        patch.object(api_main_module, "MlflowClient", return_value=client),
    ):
        with pytest.raises(RuntimeError, match="Technical Task Router"):
            api_main_module._prewarm_mlflow_registered_models()
