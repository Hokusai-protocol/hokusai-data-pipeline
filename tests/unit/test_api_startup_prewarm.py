"""Unit tests for API startup MLflow pre-warm."""

from __future__ import annotations

import asyncio
import importlib
import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.api.endpoints.model_registry import ModelRegistryEntry


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
        "21": ModelRegistryEntry(
            name="HF model",
            storage_type="huggingface_private",
            model_type="sklearn",
            is_private=True,
            inference_method="local",
            max_batch_size=1,
        ),
        "30": ModelRegistryEntry(
            name="Technical Task Router",
            storage_type="mlflow",
            model_type="router",
            is_private=False,
            inference_method="mlflow_pyfunc",
            max_batch_size=1,
        ),
        "31": ModelRegistryEntry(
            name="Ignored display name",
            storage_type="mlflow",
            model_type="router",
            is_private=False,
            inference_method="mlflow_pyfunc",
            max_batch_size=1,
            registered_model_name="Canonical MLflow Name",
        ),
    }
    client = Mock()

    with (
        patch.object(api_main_module, "MODEL_CONFIGS", model_configs),
        patch.object(api_main_module, "MlflowClient", return_value=client) as client_class_mock,
    ):
        api_main_module._prewarm_mlflow_registered_models()

    client_class_mock.assert_called_once_with(tracking_uri="https://mlflow.test.local:5000")
    assert client.get_registered_model.call_args_list == [
        (("Technical Task Router",), {}),
        (("Canonical MLflow Name",), {}),
    ]
    # REQ-F8: pre-warm must not trigger artifact downloads
    client.download_artifacts.assert_not_called()


def test_prewarm_failure_propagates(api_main_module) -> None:
    client = Mock()
    client.get_registered_model.side_effect = RuntimeError("registry down")

    with (
        patch.object(
            api_main_module,
            "MODEL_CONFIGS",
            {
                "30": ModelRegistryEntry(
                    name="Technical Task Router",
                    storage_type="mlflow",
                    model_type="router",
                    is_private=False,
                    inference_method="mlflow_pyfunc",
                    max_batch_size=1,
                )
            },
        ),
        patch.object(api_main_module, "MlflowClient", return_value=client),
    ):
        with pytest.raises(RuntimeError, match="Technical Task Router"):
            api_main_module._prewarm_mlflow_registered_models()


def test_startup_event_configures_mtls_then_tracking_uri_then_prewarm(api_main_module) -> None:
    call_order: list[str] = []
    fake_task = object()

    def capture_task(coro):
        call_order.append("startup_warm")
        coro.close()
        return fake_task

    with (
        patch(
            "src.utils.mlflow_config.configure_internal_mtls",
            side_effect=lambda: call_order.append("mtls"),
        ),
        patch.object(
            api_main_module.mlflow,
            "set_tracking_uri",
            side_effect=lambda uri: call_order.append(f"set_uri:{uri}"),
        ),
        patch.object(
            api_main_module,
            "_prewarm_mlflow_registered_models",
            side_effect=lambda: call_order.append("prewarm"),
        ),
        patch.object(
            api_main_module,
            "_startup_warm_model_30",
            new=AsyncMock(),
        ),
        patch.object(
            api_main_module.asyncio,
            "create_task",
            side_effect=capture_task,
        ),
    ):
        asyncio.run(api_main_module.startup_event())

    assert call_order == [
        "mtls",
        "set_uri:https://mlflow.test.local:5000",
        "prewarm",
        "startup_warm",
    ]
    assert api_main_module.app.state.model_30_warmup_task is fake_task


def test_startup_creates_warmup_task_when_enabled(api_main_module) -> None:
    fake_task = object()

    def capture_task(coro):
        coro.close()
        return fake_task

    with (
        patch.object(api_main_module.settings, "model_30_prewarm_enabled", True),
        patch.object(api_main_module, "_prewarm_mlflow_registered_models"),
        patch.object(api_main_module, "_startup_warm_model_30", new=AsyncMock()),
        patch.object(
            api_main_module.asyncio, "create_task", side_effect=capture_task
        ) as create_task,
    ):
        asyncio.run(api_main_module.startup_event())

    create_task.assert_called_once()
    assert api_main_module.app.state.model_30_warmup_task is fake_task


def test_startup_skips_warmup_when_prewarm_disabled(api_main_module) -> None:
    with (
        patch.object(api_main_module.settings, "model_30_prewarm_enabled", False),
        patch.object(api_main_module, "_prewarm_mlflow_registered_models"),
        patch.object(api_main_module.asyncio, "create_task") as create_task,
    ):
        asyncio.run(api_main_module.startup_event())

    create_task.assert_not_called()
