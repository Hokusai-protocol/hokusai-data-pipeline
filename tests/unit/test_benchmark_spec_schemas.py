"""Unit tests for BenchmarkSpec Pydantic schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.api.schemas.benchmark_spec import (
    BenchmarkProvider,
    BenchmarkSpecCreate,
    BenchmarkSpecListResponse,
    BenchmarkSpecResponse,
    BenchmarkSpecUpdate,
    MetricDirection,
)


def _valid_create_payload() -> dict:
    return {
        "model_id": "model-abc",
        "provider": "hokusai",
        "dataset_reference": "s3://bucket/dataset.csv",
        "eval_split": "test",
        "target_column": "label",
        "input_columns": ["feature_a", "feature_b"],
        "metric_name": "accuracy",
        "metric_direction": "higher_is_better",
    }


def _valid_response_payload() -> dict:
    return {
        **_valid_create_payload(),
        "spec_id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
        "is_active": True,
    }


# --- BenchmarkSpecCreate ---


class TestBenchmarkSpecCreate:
    def test_valid_full_payload(self):
        payload = {**_valid_create_payload(), "dataset_version": "v2", "metadata": {"key": "val"}}
        spec = BenchmarkSpecCreate(**payload)
        assert spec.model_id == "model-abc"
        assert spec.provider == BenchmarkProvider.hokusai
        assert spec.dataset_version == "v2"
        assert spec.metadata == {"key": "val"}

    def test_valid_required_only(self):
        spec = BenchmarkSpecCreate(**_valid_create_payload())
        assert spec.dataset_version is None
        assert spec.metadata is None

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            BenchmarkSpecCreate()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert missing_fields == {
            "model_id",
            "provider",
            "dataset_reference",
            "eval_split",
            "target_column",
            "input_columns",
            "metric_name",
            "metric_direction",
        }

    def test_missing_single_required_field(self):
        payload = _valid_create_payload()
        del payload["model_id"]
        with pytest.raises(ValidationError) as exc_info:
            BenchmarkSpecCreate(**payload)
        assert any(e["loc"] == ("model_id",) for e in exc_info.value.errors())

    def test_empty_input_columns_accepted(self):
        payload = _valid_create_payload()
        payload["input_columns"] = []
        spec = BenchmarkSpecCreate(**payload)
        assert spec.input_columns == []

    def test_input_columns_wrong_type(self):
        payload = _valid_create_payload()
        payload["input_columns"] = "not_a_list"
        with pytest.raises(ValidationError):
            BenchmarkSpecCreate(**payload)

    def test_empty_metadata_accepted(self):
        payload = {**_valid_create_payload(), "metadata": {}}
        spec = BenchmarkSpecCreate(**payload)
        assert spec.metadata == {}


# --- Enum validation ---


class TestEnumValidation:
    def test_provider_hokusai(self):
        payload = _valid_create_payload()
        payload["provider"] = "hokusai"
        spec = BenchmarkSpecCreate(**payload)
        assert spec.provider == BenchmarkProvider.hokusai

    def test_provider_kaggle(self):
        payload = _valid_create_payload()
        payload["provider"] = "kaggle"
        spec = BenchmarkSpecCreate(**payload)
        assert spec.provider == BenchmarkProvider.kaggle

    def test_provider_invalid(self):
        payload = _valid_create_payload()
        payload["provider"] = "aws"
        with pytest.raises(ValidationError):
            BenchmarkSpecCreate(**payload)

    def test_provider_empty_string(self):
        payload = _valid_create_payload()
        payload["provider"] = ""
        with pytest.raises(ValidationError):
            BenchmarkSpecCreate(**payload)

    def test_provider_case_sensitive(self):
        payload = _valid_create_payload()
        payload["provider"] = "HOKUSAI"
        with pytest.raises(ValidationError):
            BenchmarkSpecCreate(**payload)

    def test_metric_direction_higher(self):
        payload = _valid_create_payload()
        payload["metric_direction"] = "higher_is_better"
        spec = BenchmarkSpecCreate(**payload)
        assert spec.metric_direction == MetricDirection.higher_is_better

    def test_metric_direction_lower(self):
        payload = _valid_create_payload()
        payload["metric_direction"] = "lower_is_better"
        spec = BenchmarkSpecCreate(**payload)
        assert spec.metric_direction == MetricDirection.lower_is_better

    def test_metric_direction_invalid(self):
        payload = _valid_create_payload()
        payload["metric_direction"] = "maximize"
        with pytest.raises(ValidationError):
            BenchmarkSpecCreate(**payload)

    def test_metric_direction_empty(self):
        payload = _valid_create_payload()
        payload["metric_direction"] = ""
        with pytest.raises(ValidationError):
            BenchmarkSpecCreate(**payload)


# --- BenchmarkSpecUpdate ---


class TestBenchmarkSpecUpdate:
    def test_empty_update(self):
        update = BenchmarkSpecUpdate()
        assert update.model_id is None
        assert update.provider is None
        assert update.metric_direction is None

    def test_partial_update(self):
        update = BenchmarkSpecUpdate(metric_name="accuracy")
        assert update.metric_name == "accuracy"
        assert update.model_id is None

    def test_update_validates_enum(self):
        with pytest.raises(ValidationError):
            BenchmarkSpecUpdate(provider="invalid")


# --- BenchmarkSpecResponse ---


class TestBenchmarkSpecResponse:
    def test_full_response(self):
        payload = _valid_response_payload()
        resp = BenchmarkSpecResponse(**payload)
        assert resp.spec_id is not None
        assert resp.is_active is True
        assert resp.updated_at is None

    def test_response_uuid_parsing(self):
        uid = uuid4()
        payload = _valid_response_payload()
        payload["spec_id"] = str(uid)
        resp = BenchmarkSpecResponse(**payload)
        assert resp.spec_id == uid

    def test_response_datetime_parsing(self):
        now = datetime.now(timezone.utc)
        payload = _valid_response_payload()
        payload["created_at"] = now.isoformat()
        resp = BenchmarkSpecResponse(**payload)
        assert resp.created_at == now

    def test_response_with_updated_at(self):
        now = datetime.now(timezone.utc)
        payload = _valid_response_payload()
        payload["updated_at"] = now.isoformat()
        resp = BenchmarkSpecResponse(**payload)
        assert resp.updated_at == now


# --- BenchmarkSpecListResponse ---


class TestBenchmarkSpecListResponse:
    def test_empty_list(self):
        resp = BenchmarkSpecListResponse(items=[], total=0, page=1, page_size=20)
        assert resp.items == []
        assert resp.total == 0

    def test_list_with_items(self):
        item_payload = _valid_response_payload()
        resp = BenchmarkSpecListResponse(
            items=[BenchmarkSpecResponse(**item_payload)],
            total=1,
            page=1,
            page_size=20,
        )
        assert len(resp.items) == 1
        assert resp.total == 1


# --- Import from __init__ ---


class TestSchemaExports:
    def test_importable_from_schemas_package(self):
        from src.api.schemas import (
            BenchmarkProvider,
            BenchmarkSpecCreate,
            BenchmarkSpecListResponse,
            BenchmarkSpecResponse,
            BenchmarkSpecUpdate,
            MetricDirection,
        )

        assert BenchmarkProvider is not None
        assert BenchmarkSpecCreate is not None
        assert BenchmarkSpecListResponse is not None
        assert BenchmarkSpecResponse is not None
        assert BenchmarkSpecUpdate is not None
        assert MetricDirection is not None
