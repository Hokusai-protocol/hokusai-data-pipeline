"""Tests for evaluation service business logic."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import HTTPException

from src.api.schemas.evaluations import EvaluationRequest
from src.api.services.evaluation_service import EvaluationService


class FakeRedis:
    """Minimal in-memory Redis substitute for evaluation service tests."""

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


@pytest.fixture
def service() -> EvaluationService:
    fake_redis = FakeRedis()
    evaluation_service = EvaluationService(redis_client=fake_redis)
    evaluation_service._validate_model_exists = lambda model_id: None
    return evaluation_service


@pytest.fixture
def request_payload() -> EvaluationRequest:
    return EvaluationRequest(
        config={
            "eval_type": "openai",
            "dataset_reference": "datasets/bench-v1",
            "parameters": {"dataset_size": 10, "max_tokens": 1000},
        }
    )


def test_create_evaluation_creates_job(
    service: EvaluationService,
    request_payload: EvaluationRequest,
):
    """Create request stores queued job with cost/position metadata."""
    response = service.create_evaluation(
        model_id="my-model",
        payload=request_payload,
        idempotency_key="idem-1",
    )

    assert response.status == "queued"
    assert response.queue_position == 1
    assert response.estimated_cost > 0


def test_create_evaluation_is_idempotent(
    service: EvaluationService,
    request_payload: EvaluationRequest,
):
    first = service.create_evaluation(
        model_id="my-model",
        payload=request_payload,
        idempotency_key="same-key",
    )
    second = service.create_evaluation(
        model_id="my-model",
        payload=request_payload,
        idempotency_key="same-key",
    )

    assert first.job_id == second.job_id
    assert first.created_at == second.created_at


def test_create_evaluation_rejects_excessive_cost(
    service: EvaluationService,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("EVALUATION_MAX_COST_USD", "0.0001")
    expensive_service = EvaluationService(redis_client=service.redis)
    expensive_service._validate_model_exists = lambda model_id: None
    payload = EvaluationRequest(
        config={
            "eval_type": "openai",
            "dataset_reference": "datasets/bench-v1",
            "parameters": {"dataset_size": 100000, "max_tokens": 4000},
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        expensive_service.create_evaluation("my-model", payload, "expensive-1")

    assert exc_info.value.status_code == 402


def test_get_status_not_found(service: EvaluationService):
    with pytest.raises(HTTPException) as exc_info:
        service.get_status("0f4b6b95-6f57-4f80-a53d-cc26f00c232e")

    assert exc_info.value.status_code == 404


def test_manifest_requires_completed_job(
    service: EvaluationService,
    request_payload: EvaluationRequest,
):
    created = service.create_evaluation("my-model", request_payload, "manifest-pending")

    with pytest.raises(HTTPException) as exc_info:
        service.get_manifest(str(created.job_id))

    assert exc_info.value.status_code == 409


def test_execute_job_stores_manifest(
    service: EvaluationService,
    request_payload: EvaluationRequest,
):
    created = service.create_evaluation("my-model", request_payload, "manifest-ready")

    service.execute_evaluation_job(str(created.job_id))

    status_response = service.get_status(str(created.job_id))
    manifest_response = service.get_manifest(str(created.job_id))

    assert status_response.status == "completed"
    assert status_response.progress_percentage == 100
    assert manifest_response.job_id == created.job_id
    assert manifest_response.model_id == "my-model"
    assert manifest_response.eval_type == "openai"


def test_model_not_found_returns_404(
    request_payload: EvaluationRequest,
):
    service = EvaluationService(redis_client=FakeRedis())

    def _raise_not_found(_: str) -> None:
        raise HTTPException(status_code=404, detail="Model not found")

    service._validate_model_exists = _raise_not_found

    with pytest.raises(HTTPException) as exc_info:
        service.create_evaluation("missing-model", request_payload, "missing-model-idem")

    assert exc_info.value.status_code == 404


def test_redis_payload_uses_expected_job_namespace(
    service: EvaluationService,
    request_payload: EvaluationRequest,
):
    created = service.create_evaluation("my-model", request_payload, "namespace-key")
    raw = service.redis.get(f"eval:job:{created.job_id}")
    parsed: dict[str, Any] = json.loads(raw) if raw else {}

    assert parsed["job_id"] == str(created.job_id)
    assert parsed["status"] == "queued"
