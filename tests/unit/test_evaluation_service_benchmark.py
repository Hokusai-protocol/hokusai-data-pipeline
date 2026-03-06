"""Tests for BenchmarkSpec resolution in EvaluationService.create_evaluation()."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from src.api.schemas.evaluations import EvaluationRequest
from src.api.services.evaluation_service import EvaluationService
from src.api.services.governance.benchmark_specs import BenchmarkSpecService


class FakeRedis:
    """Minimal in-memory Redis substitute."""

    def __init__(self) -> None:
        self._kv: dict[str, str] = {}
        self._zsets: dict[str, dict[str, float]] = {}

    def get(self, key: str) -> str | None:
        return self._kv.get(key)

    def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        _ = ttl_seconds
        self._kv[key] = value

    def zadd(self, key: str, mapping: dict[str, float]) -> None:
        zset = self._zsets.setdefault(key, {})
        zset.update(mapping)

    def zrank(self, key: str, member: str) -> int | None:
        zset = self._zsets.get(key, {})
        if member not in zset:
            return None
        sorted_members = sorted(zset.items(), key=lambda item: item[1])
        for idx, (item_member, _) in enumerate(sorted_members):
            if item_member == member:
                return idx
        return None

    def zrem(self, key: str, member: str) -> None:
        zset = self._zsets.get(key, {})
        zset.pop(member, None)


BENCHMARK_DATASET_URI = "s3://hokusai-data/benchmarks/model_123/dataset.parquet"

ACTIVE_SPEC = {
    "spec_id": "spec-001",
    "provider": "hokusai",
    "model_id": "model_123",
    "dataset_id": BENCHMARK_DATASET_URI,
    "dataset_version": "v1",
    "eval_split": "test",
    "metric_name": "accuracy",
    "metric_direction": "higher_is_better",
    "tiebreak_rules": None,
    "input_schema": {},
    "output_schema": {},
    "eval_container_digest": None,
    "created_at": "2026-01-01T00:00:00+00:00",
    "is_active": True,
}


def _make_service(
    benchmark_spec_service: BenchmarkSpecService | None = None,
) -> EvaluationService:
    svc = EvaluationService(
        redis_client=FakeRedis(),
        benchmark_spec_service=benchmark_spec_service,
    )
    svc._validate_model_exists = lambda model_id: None
    return svc


def _make_payload(dataset_reference: str | None = None) -> EvaluationRequest:
    config: dict = {
        "eval_type": "openai",
        "parameters": {"dataset_size": 10, "max_tokens": 1000},
    }
    if dataset_reference is not None:
        config["dataset_reference"] = dataset_reference
    return EvaluationRequest(config=config)


class TestExplicitDatasetReference:
    """[REQ-F4] Explicit dataset_reference bypasses BenchmarkSpec."""

    def test_explicit_reference_used_as_is(self) -> None:
        mock_spec_svc = Mock(spec=BenchmarkSpecService)
        service = _make_service(benchmark_spec_service=mock_spec_svc)

        response = service.create_evaluation(
            model_id="model_123",
            payload=_make_payload("s3://custom-dataset.parquet"),
            idempotency_key="explicit-1",
        )

        assert response.status == "queued"
        mock_spec_svc.get_active_spec_for_model.assert_not_called()

    def test_explicit_reference_works_without_benchmark_spec(self) -> None:
        service = _make_service(benchmark_spec_service=None)

        response = service.create_evaluation(
            model_id="model_no_spec",
            payload=_make_payload("s3://custom-dataset.parquet"),
            idempotency_key="explicit-no-spec",
        )

        assert response.status == "queued"


class TestBenchmarkResolutionFromNone:
    """[REQ-F1] dataset_reference=None resolves from BenchmarkSpec."""

    def test_none_resolves_from_active_spec(self) -> None:
        mock_spec_svc = Mock(spec=BenchmarkSpecService)
        mock_spec_svc.get_active_spec_for_model.return_value = ACTIVE_SPEC
        service = _make_service(benchmark_spec_service=mock_spec_svc)

        response = service.create_evaluation(
            model_id="model_123",
            payload=_make_payload(None),
            idempotency_key="none-resolve-1",
        )

        assert response.status == "queued"
        mock_spec_svc.get_active_spec_for_model.assert_called_once_with("model_123")

    def test_omitted_resolves_from_active_spec(self) -> None:
        """dataset_reference omitted entirely (defaults to None)."""
        mock_spec_svc = Mock(spec=BenchmarkSpecService)
        mock_spec_svc.get_active_spec_for_model.return_value = ACTIVE_SPEC
        service = _make_service(benchmark_spec_service=mock_spec_svc)

        payload = EvaluationRequest(
            config={
                "eval_type": "openai",
                "parameters": {"dataset_size": 10, "max_tokens": 1000},
            }
        )

        response = service.create_evaluation(
            model_id="model_123",
            payload=payload,
            idempotency_key="omitted-resolve-1",
        )

        assert response.status == "queued"
        mock_spec_svc.get_active_spec_for_model.assert_called_once_with("model_123")


class TestBenchmarkSentinel:
    """[REQ-F2] Sentinel value 'benchmark' triggers BenchmarkSpec lookup."""

    def test_sentinel_benchmark_resolves_from_spec(self) -> None:
        mock_spec_svc = Mock(spec=BenchmarkSpecService)
        mock_spec_svc.get_active_spec_for_model.return_value = ACTIVE_SPEC
        service = _make_service(benchmark_spec_service=mock_spec_svc)

        response = service.create_evaluation(
            model_id="model_123",
            payload=_make_payload("benchmark"),
            idempotency_key="sentinel-1",
        )

        assert response.status == "queued"
        mock_spec_svc.get_active_spec_for_model.assert_called_once_with("model_123")

    def test_sentinel_benchmark_case_insensitive(self) -> None:
        mock_spec_svc = Mock(spec=BenchmarkSpecService)
        mock_spec_svc.get_active_spec_for_model.return_value = ACTIVE_SPEC
        service = _make_service(benchmark_spec_service=mock_spec_svc)

        response = service.create_evaluation(
            model_id="model_123",
            payload=_make_payload("BENCHMARK"),
            idempotency_key="sentinel-upper-1",
        )

        assert response.status == "queued"
        mock_spec_svc.get_active_spec_for_model.assert_called_once_with("model_123")

    def test_sentinel_with_whitespace(self) -> None:
        mock_spec_svc = Mock(spec=BenchmarkSpecService)
        mock_spec_svc.get_active_spec_for_model.return_value = ACTIVE_SPEC
        service = _make_service(benchmark_spec_service=mock_spec_svc)

        response = service.create_evaluation(
            model_id="model_123",
            payload=_make_payload("  benchmark  "),
            idempotency_key="sentinel-ws-1",
        )

        assert response.status == "queued"
        mock_spec_svc.get_active_spec_for_model.assert_called_once_with("model_123")


class TestNoBenchmarkSpecError:
    """[REQ-F3] Missing BenchmarkSpec returns clear 400 error."""

    def test_none_without_spec_returns_400(self) -> None:
        mock_spec_svc = Mock(spec=BenchmarkSpecService)
        mock_spec_svc.get_active_spec_for_model.return_value = None
        service = _make_service(benchmark_spec_service=mock_spec_svc)

        with pytest.raises(HTTPException) as exc_info:
            service.create_evaluation(
                model_id="model_456",
                payload=_make_payload(None),
                idempotency_key="no-spec-1",
            )

        assert exc_info.value.status_code == 400
        assert "dataset_reference" in exc_info.value.detail
        assert "BenchmarkSpec" in exc_info.value.detail
        assert "model_456" in exc_info.value.detail

    def test_sentinel_without_spec_returns_400(self) -> None:
        mock_spec_svc = Mock(spec=BenchmarkSpecService)
        mock_spec_svc.get_active_spec_for_model.return_value = None
        service = _make_service(benchmark_spec_service=mock_spec_svc)

        with pytest.raises(HTTPException) as exc_info:
            service.create_evaluation(
                model_id="model_456",
                payload=_make_payload("benchmark"),
                idempotency_key="no-spec-sentinel-1",
            )

        assert exc_info.value.status_code == 400

    def test_none_without_spec_service_returns_400(self) -> None:
        """No BenchmarkSpecService injected at all → same 400 error."""
        service = _make_service(benchmark_spec_service=None)

        with pytest.raises(HTTPException) as exc_info:
            service.create_evaluation(
                model_id="model_456",
                payload=_make_payload(None),
                idempotency_key="no-svc-1",
            )

        assert exc_info.value.status_code == 400
        assert "BenchmarkSpec" in exc_info.value.detail


class TestEmptyStringDatasetReference:
    """[REQ-F5] Empty string treated as missing."""

    def test_empty_string_resolves_from_spec(self) -> None:
        mock_spec_svc = Mock(spec=BenchmarkSpecService)
        mock_spec_svc.get_active_spec_for_model.return_value = ACTIVE_SPEC
        service = _make_service(benchmark_spec_service=mock_spec_svc)

        response = service.create_evaluation(
            model_id="model_123",
            payload=_make_payload(""),
            idempotency_key="empty-1",
        )

        assert response.status == "queued"
        mock_spec_svc.get_active_spec_for_model.assert_called_once_with("model_123")

    def test_empty_string_without_spec_returns_400(self) -> None:
        mock_spec_svc = Mock(spec=BenchmarkSpecService)
        mock_spec_svc.get_active_spec_for_model.return_value = None
        service = _make_service(benchmark_spec_service=mock_spec_svc)

        with pytest.raises(HTTPException) as exc_info:
            service.create_evaluation(
                model_id="model_456",
                payload=_make_payload(""),
                idempotency_key="empty-no-spec-1",
            )

        assert exc_info.value.status_code == 400
