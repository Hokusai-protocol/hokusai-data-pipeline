"""Unit tests for EvaluationScheduler."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from src.api.services.evaluation_scheduler import EvaluationScheduler


def _make_schedule(
    schedule_id: str = "sched-1",
    model_id: str = "model-abc",
    cron_expression: str = "0 0 * * *",
    enabled: bool = True,
    next_run_at: str = "2026-03-05T00:00:00+00:00",
) -> dict:
    return {
        "id": schedule_id,
        "model_id": model_id,
        "cron_expression": cron_expression,
        "enabled": enabled,
        "next_run_at": next_run_at,
        "last_run_at": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _mock_eval_response(job_id: str = "00000000-0000-0000-0000-000000000001") -> MagicMock:
    resp = MagicMock()
    resp.job_id = UUID(job_id)
    return resp


def _build_scheduler(
    schedules: list[dict] | None = None,
    create_eval_side_effect=None,
    poll_interval: int = 1,
    max_concurrent: int = 5,
) -> tuple[EvaluationScheduler, MagicMock, MagicMock, MagicMock]:
    schedule_service = MagicMock()
    schedule_service.get_due_schedules.return_value = schedules or []
    schedule_service.update_schedule.return_value = None

    eval_service = MagicMock()
    if create_eval_side_effect is not None:
        eval_service.create_evaluation.side_effect = create_eval_side_effect
    else:
        eval_service.create_evaluation.return_value = _mock_eval_response()

    queue_manager = MagicMock()
    queue_manager.enqueue.return_value = "queue-job-1"

    scheduler = EvaluationScheduler(
        schedule_service=schedule_service,
        evaluation_service=eval_service,
        queue_manager=queue_manager,
        poll_interval=poll_interval,
        max_concurrent=max_concurrent,
    )
    return scheduler, schedule_service, eval_service, queue_manager


@pytest.mark.asyncio
async def test_poll_finds_due_schedules_and_processes():
    """[REQ-F1] Scheduler fetches due schedules."""
    schedules = [
        _make_schedule("s1", "m1"),
        _make_schedule("s2", "m2"),
        _make_schedule("s3", "m3"),
    ]
    scheduler, sched_svc, eval_svc, queue_mgr = _build_scheduler(schedules)

    await scheduler._poll_once()

    sched_svc.get_due_schedules.assert_called_once_with(limit=5)
    assert eval_svc.create_evaluation.call_count == 3
    assert queue_mgr.enqueue.call_count == 3
    assert sched_svc.update_schedule.call_count == 3


@pytest.mark.asyncio
async def test_no_due_schedules():
    """[REQ-F1] Empty result causes no evaluations."""
    scheduler, sched_svc, eval_svc, queue_mgr = _build_scheduler([])

    await scheduler._poll_once()

    sched_svc.get_due_schedules.assert_called_once_with(limit=5)
    eval_svc.create_evaluation.assert_not_called()
    queue_mgr.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_evaluation_created_with_benchmark():
    """[REQ-F2] Evaluation uses dataset_reference='benchmark'."""
    scheduler, _, eval_svc, _ = _build_scheduler([_make_schedule()])

    await scheduler._poll_once()

    call_kwargs = eval_svc.create_evaluation.call_args
    payload = call_kwargs.kwargs["payload"]
    assert payload.config.dataset_reference == "benchmark"
    assert payload.config.eval_type == "benchmark"
    assert call_kwargs.kwargs["model_id"] == "model-abc"


@pytest.mark.asyncio
async def test_job_is_enqueued():
    """[REQ-F3] Created job is enqueued via queue manager."""
    scheduler, _, _, queue_mgr = _build_scheduler([_make_schedule()])

    await scheduler._poll_once()

    queue_mgr.enqueue.assert_called_once()
    job = queue_mgr.enqueue.call_args[0][0]
    assert job.model_id == "model-abc"


@pytest.mark.asyncio
async def test_timestamps_updated():
    """[REQ-F4] last_run_at set to now, next_run_at advanced."""
    schedule = _make_schedule(cron_expression="0 0 * * *")
    scheduler, sched_svc, _, _ = _build_scheduler([schedule])

    await scheduler._poll_once()

    update_call = sched_svc.update_schedule.call_args
    changes = update_call[0][1]
    # last_run_at should be close to now
    assert isinstance(changes["last_run_at"], datetime)
    assert changes["last_run_at"].tzinfo is not None
    # next_run_at should be a future datetime (next midnight after now)
    assert isinstance(changes["next_run_at"], datetime)
    assert changes["next_run_at"] > changes["last_run_at"]


@pytest.mark.asyncio
async def test_missed_runs_advance_to_future():
    """[REQ-F5] Missed runs produce exactly one evaluation, next_run_at jumps forward."""
    schedule = _make_schedule(
        cron_expression="0 0 * * *",
        next_run_at="2026-02-01T00:00:00+00:00",
    )
    scheduler, sched_svc, eval_svc, _ = _build_scheduler([schedule])

    await scheduler._poll_once()

    # Only one evaluation created (no backfill)
    assert eval_svc.create_evaluation.call_count == 1

    changes = sched_svc.update_schedule.call_args[0][1]
    now = datetime.now(timezone.utc)
    # next_run_at should be in the future (not back-filled)
    assert changes["next_run_at"] > now


@pytest.mark.asyncio
async def test_concurrency_limit_respected():
    """[REQ-F6] get_due_schedules called with limit=max_concurrent."""
    scheduler, sched_svc, _, _ = _build_scheduler([], max_concurrent=3)

    await scheduler._poll_once()

    sched_svc.get_due_schedules.assert_called_once_with(limit=3)


@pytest.mark.asyncio
async def test_error_isolation():
    """[REQ-F7] Failure in one schedule does not block others."""
    schedules = [
        _make_schedule("s1", "m1"),
        _make_schedule("s2", "m2"),
        _make_schedule("s3", "m3"),
    ]

    responses = [
        _mock_eval_response(),
        RuntimeError("model not found"),
        _mock_eval_response(),
    ]

    def create_side_effect(**kwargs):
        resp = responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    scheduler, sched_svc, eval_svc, queue_mgr = _build_scheduler(
        schedules, create_eval_side_effect=create_side_effect
    )

    await scheduler._poll_once()

    # All 3 create_evaluation calls attempted
    assert eval_svc.create_evaluation.call_count == 3
    # 2 successful enqueues (s1 and s3), s2 failed before enqueue
    assert queue_mgr.enqueue.call_count == 2
    # All 3 schedules updated (timestamps advanced even on failure)
    assert sched_svc.update_schedule.call_count == 3


@pytest.mark.asyncio
async def test_start_and_stop_lifecycle():
    """[REQ-F8] Scheduler starts and stops cleanly."""
    scheduler, sched_svc, _, _ = _build_scheduler([])

    await scheduler.start()
    assert scheduler._task is not None
    assert not scheduler._task.done()

    await scheduler.stop()
    assert scheduler._task is None


@pytest.mark.asyncio
async def test_stop_without_start_is_noop():
    """[REQ-F8] Calling stop() without start() does not raise."""
    scheduler, _, _, _ = _build_scheduler([])
    await scheduler.stop()  # Should not raise


@pytest.mark.asyncio
async def test_compute_next_run():
    """croniter correctly computes next occurrence."""
    now = datetime(2026, 3, 6, 10, 30, 0, tzinfo=timezone.utc)
    # Every day at midnight
    result = EvaluationScheduler._compute_next_run("0 0 * * *", now)
    assert result == datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_compute_next_run_hourly():
    """croniter handles hourly cron correctly."""
    now = datetime(2026, 3, 6, 10, 30, 0, tzinfo=timezone.utc)
    result = EvaluationScheduler._compute_next_run("0 * * * *", now)
    assert result == datetime(2026, 3, 6, 11, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_enqueue_failure_still_updates_timestamps():
    """Enqueue failure should not prevent timestamp update."""
    schedule = _make_schedule()
    scheduler, sched_svc, _, queue_mgr = _build_scheduler([schedule])
    queue_mgr.enqueue.side_effect = RuntimeError("Redis down")

    await scheduler._poll_once()

    # Timestamps still updated despite enqueue failure
    sched_svc.update_schedule.assert_called_once()


@pytest.mark.asyncio
async def test_poll_loop_continues_after_error():
    """Poll loop does not crash on unexpected errors."""
    scheduler, sched_svc, _, _ = _build_scheduler([])
    call_count = 0

    original_poll = scheduler._poll_once

    async def failing_poll():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("unexpected")
        # Second call succeeds, then we stop
        await original_poll()

    scheduler._poll_once = failing_poll
    scheduler._poll_interval = 0.01

    await scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert call_count >= 2
