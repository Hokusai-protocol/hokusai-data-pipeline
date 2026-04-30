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
    EvalSpec,
    GuardrailSpec,
    MetricDirection,
    MetricSpec,
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
            EvalSpec,
            GuardrailSpec,
            MetricDirection,
            MetricSpec,
        )

        assert BenchmarkProvider is not None
        assert BenchmarkSpecCreate is not None
        assert BenchmarkSpecListResponse is not None
        assert BenchmarkSpecResponse is not None
        assert BenchmarkSpecUpdate is not None
        assert MetricDirection is not None
        assert EvalSpec is not None
        assert MetricSpec is not None
        assert GuardrailSpec is not None


# --- EvalSpec schemas ---


def _full_eval_spec_payload() -> dict:
    return {
        "primary_metric": {"name": "accuracy", "direction": "higher_is_better"},
        "secondary_metrics": [{"name": "f1", "direction": "higher_is_better", "unit": "macro"}],
        "guardrails": [{"name": "latency_p99", "direction": "lower_is_better", "threshold": 200.0}],
        "measurement_policy": {"window": "7d"},
        "unit_of_analysis": "row",
        "min_examples": 100,
        "label_policy": {"strategy": "majority_vote"},
        "coverage_policy": {"min_coverage": 0.95},
    }


class TestMetricSpec:
    def test_valid_metric_spec(self):
        ms = MetricSpec(name="accuracy", direction="higher_is_better")
        assert ms.name == "accuracy"
        assert ms.threshold is None
        assert ms.unit is None

    def test_metric_spec_with_optional_fields(self):
        ms = MetricSpec(name="rmse", direction="lower_is_better", threshold=0.1, unit="mse")
        assert ms.threshold == 0.1
        assert ms.unit == "mse"

    def test_metric_spec_invalid_direction(self):
        with pytest.raises(ValidationError):
            MetricSpec(name="accuracy", direction="maximize")

    def test_mlflow_name_auto_populated_from_name(self):
        ms = MetricSpec(name="workflow:success_rate_under_budget", direction="higher_is_better")
        assert ms.mlflow_name == "workflow_success_rate_under_budget"

    def test_mlflow_name_safe_name_equals_name(self):
        ms = MetricSpec(name="accuracy", direction="higher_is_better")
        assert ms.mlflow_name == "accuracy"

    def test_mlflow_name_explicit_override_accepted(self):
        ms = MetricSpec(name="x", direction="higher_is_better", mlflow_name="custom_key")
        assert ms.mlflow_name == "custom_key"

    def test_mlflow_name_rejects_colon(self):
        with pytest.raises(ValidationError) as exc_info:
            MetricSpec(name="x", direction="higher_is_better", mlflow_name="bad:key")
        assert "colon" in str(exc_info.value).lower() or ":" in str(exc_info.value)

    def test_mlflow_name_empty_string_treated_as_omitted(self):
        ms = MetricSpec(name="my:metric", direction="higher_is_better", mlflow_name="")
        assert ms.mlflow_name == "my_metric"

    def test_mlflow_name_included_in_model_dump(self):
        ms = MetricSpec(name="workflow:sr", direction="higher_is_better")
        dumped = ms.model_dump()
        assert dumped["mlflow_name"] == "workflow_sr"


class TestGuardrailSpec:
    def test_valid_guardrail(self):
        g = GuardrailSpec(name="latency", direction="lower_is_better", threshold=500.0)
        assert g.blocking is True

    def test_guardrail_non_blocking(self):
        g = GuardrailSpec(
            name="latency", direction="lower_is_better", threshold=500.0, blocking=False
        )
        assert g.blocking is False

    def test_guardrail_missing_threshold_rejected(self):
        with pytest.raises(ValidationError):
            GuardrailSpec(name="latency", direction="lower_is_better")

    def test_guardrail_mlflow_name_auto_populated(self):
        g = GuardrailSpec(name="latency:p99", direction="lower_is_better", threshold=200.0)
        assert g.mlflow_name == "latency_p99"

    def test_guardrail_mlflow_name_rejects_colon(self):
        with pytest.raises(ValidationError):
            GuardrailSpec(
                name="x", direction="lower_is_better", threshold=1.0, mlflow_name="bad:key"
            )


class TestEvalSpec:
    def test_eval_spec_optional_on_create(self):
        spec = BenchmarkSpecCreate(**_valid_create_payload())
        assert spec.eval_spec is None

    def test_eval_spec_full_payload(self):
        payload = {**_valid_create_payload(), "eval_spec": _full_eval_spec_payload()}
        spec = BenchmarkSpecCreate(**payload)
        assert spec.eval_spec is not None
        assert spec.eval_spec.primary_metric.name == "accuracy"
        assert len(spec.eval_spec.secondary_metrics) == 1
        assert len(spec.eval_spec.guardrails) == 1
        assert spec.eval_spec.unit_of_analysis == "row"
        assert spec.eval_spec.min_examples == 100

    def test_eval_spec_requires_primary_metric_when_provided(self):
        with pytest.raises(ValidationError):
            EvalSpec(secondary_metrics=[])

    def test_eval_spec_min_examples_must_be_positive(self):
        with pytest.raises(ValidationError):
            EvalSpec(
                primary_metric={"name": "accuracy", "direction": "higher_is_better"},
                min_examples=0,
            )

    def test_eval_spec_metric_direction_invalid_rejected(self):
        with pytest.raises(ValidationError):
            EvalSpec(
                primary_metric={"name": "accuracy", "direction": "bad_direction"},
            )

    def test_eval_spec_response_round_trip(self):
        uid = str(uuid4())
        eval_spec_dict = {
            "primary_metric": {"name": "accuracy", "direction": "higher_is_better"},
            "secondary_metrics": [],
            "guardrails": [],
        }
        payload = {
            **_valid_response_payload(),
            "spec_id": uid,
            "eval_spec": eval_spec_dict,
        }
        resp = BenchmarkSpecResponse(**payload)
        assert resp.eval_spec is not None
        assert resp.eval_spec.primary_metric.name == "accuracy"

    def test_eval_spec_none_on_response(self):
        payload = _valid_response_payload()
        resp = BenchmarkSpecResponse(**payload)
        assert resp.eval_spec is None

    def test_eval_spec_on_update_schema(self):
        update = BenchmarkSpecUpdate(
            eval_spec={
                "primary_metric": {"name": "f1", "direction": "higher_is_better"},
            }
        )
        assert update.eval_spec is not None
        assert update.eval_spec.primary_metric.name == "f1"

    def test_eval_spec_round_trip_carries_mlflow_name(self):
        es = EvalSpec(
            primary_metric={"name": "workflow:sr", "direction": "higher_is_better"},
            secondary_metrics=[{"name": "a:b", "direction": "lower_is_better"}],
            guardrails=[
                {"name": "latency:p99", "direction": "lower_is_better", "threshold": 200.0}
            ],
        )
        dumped = es.model_dump()
        assert dumped["primary_metric"]["mlflow_name"] == "workflow_sr"
        assert dumped["secondary_metrics"][0]["mlflow_name"] == "a_b"
        assert dumped["guardrails"][0]["mlflow_name"] == "latency_p99"
