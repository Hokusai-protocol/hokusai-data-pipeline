from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.api.endpoints import model_30_adapter
from src.api.utils.config import get_settings


@pytest.fixture(autouse=True)
def reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_PASSWORD", "test-password")
    get_settings.cache_clear()
    model_30_adapter.reset_model_30_cache()
    yield
    get_settings.cache_clear()


def _fixture_path() -> str:
    return str(Path("data/test_fixtures/model_30_minimal_payload.json"))


@pytest.mark.asyncio
async def test_warm_model_30_sets_warmed_state() -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = {"selected_model": "gpt-5.4"}

    with (
        patch.object(
            model_30_adapter.get_settings(), "model_30_warm_fixture_path", _fixture_path()
        ),
        patch(
            "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
            return_value=fake_model,
        ),
    ):
        state = await model_30_adapter.warm_model_30("models:/Technical Task Router/4", 5.0)

    assert state["warmed"] is True
    assert state["state"] == model_30_adapter.Model30WarmupState.WARMED.value
    assert state["warmed_at"] is not None
    assert state["duration_ms"] is not None


@pytest.mark.asyncio
async def test_warm_model_30_is_idempotent() -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = {"selected_model": "gpt-5.4"}

    with (
        patch.object(
            model_30_adapter.get_settings(), "model_30_warm_fixture_path", _fixture_path()
        ),
        patch(
            "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
            return_value=fake_model,
        ) as load_model,
    ):
        await model_30_adapter.warm_model_30("models:/Technical Task Router/4", 5.0)
        await model_30_adapter.warm_model_30("models:/Technical Task Router/4", 5.0)

    load_model.assert_called_once()


@pytest.mark.asyncio
async def test_warm_model_30_concurrent_calls_only_load_once() -> None:
    started = threading.Event()
    release = threading.Event()
    load_calls: list[str] = []

    def fake_load(uri: str) -> object:
        started.set()
        load_calls.append(uri)
        release.wait()
        return SimpleNamespace(predict=lambda _features: {"selected_model": "gpt-5.4"})

    async def unblock() -> None:
        await asyncio.to_thread(started.wait)
        release.set()

    with (
        patch.object(
            model_30_adapter.get_settings(), "model_30_warm_fixture_path", _fixture_path()
        ),
        patch("src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model", side_effect=fake_load),
    ):
        unblock_task = asyncio.create_task(unblock())
        await asyncio.gather(
            model_30_adapter.warm_model_30("models:/Technical Task Router/4", 5.0),
            model_30_adapter.warm_model_30("models:/Technical Task Router/4", 5.0),
        )
        await unblock_task

    assert load_calls == ["models:/Technical Task Router/4"]


@pytest.mark.asyncio
async def test_warm_model_30_failure_sets_failed_state() -> None:
    with (
        patch.object(
            model_30_adapter.get_settings(), "model_30_warm_fixture_path", _fixture_path()
        ),
        patch(
            "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
            side_effect=RuntimeError("registry unavailable"),
        ),
    ):
        state = await model_30_adapter.warm_model_30("models:/Technical Task Router/4", 5.0)

    assert state["warmed"] is False
    assert state["state"] == model_30_adapter.Model30WarmupState.FAILED.value
    assert state["last_error"] == "registry unavailable"


@pytest.mark.asyncio
async def test_warm_model_30_timeout_sets_failed_state() -> None:
    async def fake_wait_for(coro, *_args, **_kwargs):
        coro.close()
        raise asyncio.TimeoutError()

    with patch("src.api.endpoints.model_30_adapter.asyncio.wait_for", side_effect=fake_wait_for):
        state = await model_30_adapter.warm_model_30("models:/Technical Task Router/4", 0.01)

    assert state["state"] == model_30_adapter.Model30WarmupState.FAILED.value
    assert state["warmed"] is False


def test_get_model_30_warmup_state_before_warm() -> None:
    assert model_30_adapter.get_model_30_warmup_state() == {
        "warmed": False,
        "state": model_30_adapter.Model30WarmupState.NOT_STARTED.value,
        "warmed_at": None,
        "last_error": None,
        "duration_ms": None,
    }


def test_reset_model_30_cache_also_resets_warmup_state() -> None:
    model_30_adapter.set_model_30_warmup_state(
        model_30_adapter.Model30WarmupState.WARMED,
        warmed_at="2026-06-01T00:00:00+00:00",
        duration_ms=100,
    )

    model_30_adapter.reset_model_30_cache()

    assert model_30_adapter.get_model_30_warmup_state()["state"] == (
        model_30_adapter.Model30WarmupState.NOT_STARTED.value
    )
