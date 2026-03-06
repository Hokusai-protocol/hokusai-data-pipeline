"""Unit tests for EvaluationSchedule Pydantic schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.api.schemas.evaluation_schedule import (
    EvaluationScheduleCreate,
    EvaluationScheduleResponse,
    EvaluationScheduleUpdate,
)


class TestEvaluationScheduleCreate:
    def test_valid_cron_expression(self):
        schema = EvaluationScheduleCreate(cron_expression="0 */6 * * *")
        assert schema.cron_expression == "0 */6 * * *"
        assert schema.enabled is True

    def test_valid_with_enabled_false(self):
        schema = EvaluationScheduleCreate(cron_expression="0 0 * * 1", enabled=False)
        assert schema.enabled is False

    def test_daily_shorthand_accepted(self):
        schema = EvaluationScheduleCreate(cron_expression="@daily")
        assert schema.cron_expression == "@daily"

    def test_invalid_cron_rejected(self):
        with pytest.raises(ValidationError, match="Invalid cron expression"):
            EvaluationScheduleCreate(cron_expression="not a cron")

    def test_empty_cron_rejected(self):
        with pytest.raises(ValidationError):
            EvaluationScheduleCreate(cron_expression="")

    def test_missing_cron_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            EvaluationScheduleCreate()
        errors = exc_info.value.errors()
        missing = {e["loc"][0] for e in errors}
        assert "cron_expression" in missing


class TestEvaluationScheduleUpdate:
    def test_empty_update(self):
        update = EvaluationScheduleUpdate()
        assert update.cron_expression is None
        assert update.enabled is None
        assert update.next_run_at is None

    def test_partial_update_enabled(self):
        update = EvaluationScheduleUpdate(enabled=False)
        assert update.enabled is False
        assert update.cron_expression is None

    def test_partial_update_cron(self):
        update = EvaluationScheduleUpdate(cron_expression="30 2 * * *")
        assert update.cron_expression == "30 2 * * *"

    def test_invalid_cron_rejected(self):
        with pytest.raises(ValidationError, match="Invalid cron expression"):
            EvaluationScheduleUpdate(cron_expression="bad cron")

    def test_update_with_next_run_at(self):
        now = datetime.now(timezone.utc)
        update = EvaluationScheduleUpdate(next_run_at=now)
        assert update.next_run_at == now


class TestEvaluationScheduleResponse:
    def test_full_response(self):
        now = datetime.now(timezone.utc)
        uid = uuid4()
        resp = EvaluationScheduleResponse(
            id=uid,
            model_id="model-123",
            cron_expression="0 */6 * * *",
            enabled=True,
            last_run_at=None,
            next_run_at=None,
            created_at=now,
            updated_at=now,
        )
        assert resp.id == uid
        assert resp.model_id == "model-123"
        assert resp.enabled is True

    def test_response_uuid_parsing(self):
        uid = uuid4()
        now = datetime.now(timezone.utc)
        resp = EvaluationScheduleResponse(
            id=str(uid),
            model_id="m",
            cron_expression="@daily",
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        assert resp.id == uid

    def test_response_with_timestamps(self):
        now = datetime.now(timezone.utc)
        resp = EvaluationScheduleResponse(
            id=uuid4(),
            model_id="m",
            cron_expression="@daily",
            enabled=True,
            last_run_at=now,
            next_run_at=now,
            created_at=now,
            updated_at=now,
        )
        assert resp.last_run_at == now
        assert resp.next_run_at == now


class TestSchemaExports:
    def test_importable_from_schemas_package(self):
        from src.api.schemas import (
            EvaluationScheduleCreate,
            EvaluationScheduleResponse,
            EvaluationScheduleUpdate,
        )

        assert EvaluationScheduleCreate is not None
        assert EvaluationScheduleResponse is not None
        assert EvaluationScheduleUpdate is not None
