"""Unit tests for evaluation schedule service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.api.services.governance.benchmark_specs import BenchmarkSpecService
from src.api.services.governance.evaluation_schedule import (
    EvaluationScheduleService,
    NoBenchmarkSpecError,
    ScheduleAlreadyExistsError,
)


def _make_service(has_benchmark: bool = True) -> EvaluationScheduleService:
    """Create a service with mocked benchmark spec service."""
    mock_benchmark = MagicMock(spec=BenchmarkSpecService)
    if has_benchmark:
        mock_benchmark.get_active_spec_for_model.return_value = {"spec_id": "some-spec"}
    else:
        mock_benchmark.get_active_spec_for_model.return_value = None
    return EvaluationScheduleService(benchmark_spec_service=mock_benchmark)


def test_create_and_get_schedule() -> None:
    service = _make_service()
    created = service.create_schedule(
        model_id="model-a",
        cron_expression="0 */6 * * *",
    )

    assert created["model_id"] == "model-a"
    assert created["cron_expression"] == "0 */6 * * *"
    assert created["enabled"] is True
    assert created["last_run_at"] is None
    assert created["next_run_at"] is None

    fetched = service.get_schedule("model-a")
    assert fetched is not None
    assert fetched["id"] == created["id"]


def test_create_with_enabled_false() -> None:
    service = _make_service()
    created = service.create_schedule(
        model_id="model-b",
        cron_expression="0 0 * * *",
        enabled=False,
    )
    assert created["enabled"] is False


def test_create_raises_when_no_benchmark_spec() -> None:
    service = _make_service(has_benchmark=False)
    with pytest.raises(NoBenchmarkSpecError, match="active BenchmarkSpec"):
        service.create_schedule(model_id="model-x", cron_expression="0 0 * * *")


def test_create_raises_when_schedule_exists() -> None:
    service = _make_service()
    service.create_schedule(model_id="model-dup", cron_expression="0 0 * * *")
    with pytest.raises(ScheduleAlreadyExistsError, match="already exists"):
        service.create_schedule(model_id="model-dup", cron_expression="0 6 * * *")


def test_get_nonexistent_returns_none() -> None:
    service = _make_service()
    assert service.get_schedule("nonexistent") is None


def test_update_schedule() -> None:
    service = _make_service()
    service.create_schedule(model_id="model-u", cron_expression="0 */6 * * *")

    updated = service.update_schedule("model-u", {"cron_expression": "0 0 * * *", "enabled": False})
    assert updated is not None
    assert updated["cron_expression"] == "0 0 * * *"
    assert updated["enabled"] is False


def test_update_partial() -> None:
    service = _make_service()
    service.create_schedule(model_id="model-p", cron_expression="0 */6 * * *")

    updated = service.update_schedule("model-p", {"enabled": False})
    assert updated is not None
    assert updated["enabled"] is False
    assert updated["cron_expression"] == "0 */6 * * *"


def test_update_nonexistent_returns_none() -> None:
    service = _make_service()
    assert service.update_schedule("nonexistent", {"enabled": False}) is None


def test_delete_schedule() -> None:
    service = _make_service()
    service.create_schedule(model_id="model-d", cron_expression="0 0 * * *")
    assert service.delete_schedule("model-d") is True
    assert service.get_schedule("model-d") is None


def test_delete_nonexistent_returns_false() -> None:
    service = _make_service()
    assert service.delete_schedule("nonexistent") is False
