"""Background scheduler that polls for due evaluation schedules and triggers runs."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from croniter import croniter

from src.api.schemas.evaluations import EvaluationConfig, EvaluationRequest
from src.api.services.evaluation_service import EvaluationService
from src.api.services.governance.evaluation_schedule import EvaluationScheduleService
from src.models.evaluation_job import EvaluationJob
from src.services.evaluation_queue import EvaluationQueueManager

logger = logging.getLogger(__name__)


class EvaluationScheduler:
    """Polls EvaluationSchedule table for due schedules and triggers evaluations."""

    def __init__(
        self: EvaluationScheduler,
        schedule_service: EvaluationScheduleService,
        evaluation_service: EvaluationService,
        queue_manager: EvaluationQueueManager,
        poll_interval: int | None = None,
        max_concurrent: int | None = None,
    ) -> None:
        self._schedule_service = schedule_service
        self._evaluation_service = evaluation_service
        self._queue_manager = queue_manager
        self._poll_interval = poll_interval or int(
            os.getenv("SCHEDULER_POLL_INTERVAL_SECONDS", "60")
        )
        self._max_concurrent = max_concurrent or int(os.getenv("SCHEDULER_MAX_CONCURRENT", "5"))
        self._task: asyncio.Task[None] | None = None

    async def start(self: EvaluationScheduler) -> None:
        """Launch the poll loop as an asyncio background task."""
        logger.info(
            "Starting evaluation scheduler poll_interval=%s max_concurrent=%s",
            self._poll_interval,
            self._max_concurrent,
        )
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self: EvaluationScheduler) -> None:
        """Cancel the poll loop and wait for clean shutdown."""
        if self._task is None:
            return
        logger.info("Stopping evaluation scheduler")
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _poll_loop(self: EvaluationScheduler) -> None:
        """Infinite loop: fetch due schedules, process, sleep."""
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error in scheduler poll loop")
            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self: EvaluationScheduler) -> None:
        """Single poll iteration — fetch due schedules and process each."""
        schedules = await asyncio.to_thread(
            self._schedule_service.get_due_schedules,
            limit=self._max_concurrent,
        )
        if not schedules:
            return

        logger.info("Scheduler found %d due schedule(s)", len(schedules))
        for schedule in schedules:
            try:
                await self._process_schedule(schedule)
            except Exception:
                logger.exception(
                    "Failed to process schedule schedule_id=%s model_id=%s",
                    schedule.get("id"),
                    schedule.get("model_id"),
                )

    async def _process_schedule(self: EvaluationScheduler, schedule: dict[str, Any]) -> None:
        """Create an evaluation job for a single due schedule and advance timestamps."""
        schedule_id = schedule["id"]
        model_id = schedule["model_id"]

        logger.info(
            "Processing scheduled evaluation schedule_id=%s model_id=%s",
            schedule_id,
            model_id,
        )

        idempotency_key = f"sched-{schedule_id}-{uuid4()}"
        request = EvaluationRequest(
            config=EvaluationConfig(
                eval_type="benchmark",
                dataset_reference="benchmark",
            )
        )

        try:
            response = await asyncio.to_thread(
                self._evaluation_service.create_evaluation,
                model_id=model_id,
                payload=request,
                idempotency_key=idempotency_key,
                user_context={"user_id": "scheduler", "scopes": []},
            )
            logger.info(
                "Evaluation created schedule_id=%s model_id=%s job_id=%s",
                schedule_id,
                model_id,
                response.job_id,
            )
        except Exception:
            logger.exception(
                "Failed to create evaluation schedule_id=%s model_id=%s",
                schedule_id,
                model_id,
            )
            # Still advance next_run_at so we don't retry indefinitely
            now = datetime.now(timezone.utc)
            next_run = self._compute_next_run(schedule["cron_expression"], now)
            await asyncio.to_thread(
                self._schedule_service.update_schedule,
                model_id,
                {"last_run_at": now, "next_run_at": next_run},
            )
            return

        # Enqueue via the queue manager for robust processing
        job = EvaluationJob(
            model_id=model_id,
            eval_config={
                "eval_type": "benchmark",
                "dataset_reference": "benchmark",
                "job_id": str(response.job_id),
            },
        )
        try:
            await asyncio.to_thread(self._queue_manager.enqueue, job)
            logger.info(
                "Evaluation enqueued schedule_id=%s model_id=%s queue_job_id=%s",
                schedule_id,
                model_id,
                job.id,
            )
        except Exception:
            logger.exception(
                "Failed to enqueue evaluation schedule_id=%s model_id=%s",
                schedule_id,
                model_id,
            )

        # Advance timestamps regardless of enqueue success
        now = datetime.now(timezone.utc)
        next_run = self._compute_next_run(schedule["cron_expression"], now)
        await asyncio.to_thread(
            self._schedule_service.update_schedule,
            model_id,
            {"last_run_at": now, "next_run_at": next_run},
        )
        logger.info(
            "Schedule updated schedule_id=%s model_id=%s next_run_at=%s",
            schedule_id,
            model_id,
            next_run.isoformat(),
        )

    @staticmethod
    def _compute_next_run(cron_expression: str, now: datetime) -> datetime:
        """Compute the next run time after *now* using croniter.

        This handles missed runs by always computing from ``now``, so the
        schedule jumps forward to the next future occurrence instead of
        backfilling missed slots.
        """
        cron = croniter(cron_expression, now)
        return cron.get_next(datetime)
