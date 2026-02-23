"""Unit tests for token mint hook stub behavior and auditing."""

from __future__ import annotations

import json
from unittest.mock import Mock
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from src.api.services.token_mint_hook import TokenMintHook


def _json_logs(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in caplog.records:
        rows.append(json.loads(record.getMessage()))
    return rows


def test_mint_dry_run_returns_audit_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO")
    hook = TokenMintHook(dry_run=True)

    result = hook.mint(
        model_id="model-a",
        token_id="token-a",
        delta_value=1.5,
        idempotency_key="idem-123",
        metadata={"source": "usage_logger"},
    )

    assert result.status == "dry_run"
    assert UUID(result.audit_ref)
    logs = _json_logs(caplog)
    assert any(item["action"] == "token_mint_request" for item in logs)
    assert any(item["action"] == "token_mint_outcome" for item in logs)
    outcome_log = next(item for item in logs if item["action"] == "token_mint_outcome")
    assert outcome_log["status"] == "dry_run"
    assert outcome_log["idempotency_key"] == "idem-123"


def test_audit_ref_is_unique_per_call() -> None:
    hook = TokenMintHook(dry_run=True)

    first = hook.mint("model-a", "token-a", 1.0)
    second = hook.mint("model-a", "token-a", 1.0)

    assert first.audit_ref != second.audit_ref
    assert UUID(first.audit_ref)
    assert UUID(second.audit_ref)


def test_invalid_inputs_raise_validation_error_before_http_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hook = TokenMintHook(mint_endpoint="https://mint.service.local", dry_run=False)
    post_mock = Mock()
    monkeypatch.setattr("src.api.services.token_mint_hook.httpx.post", post_mock)

    with pytest.raises(ValidationError):
        hook.mint(model_id="", token_id="token-a", delta_value=1.0)

    with pytest.raises(ValidationError):
        hook.mint(model_id="model-a", token_id="", delta_value=1.0)

    with pytest.raises(ValidationError):
        hook.mint(model_id="model-a", token_id="token-a", delta_value=-1.0)

    post_mock.assert_not_called()


def test_http_call_made_when_endpoint_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    hook = TokenMintHook(mint_endpoint="https://mint.service.local", dry_run=False)

    response = Mock()
    response.status_code = 201
    response.text = '{"status": "ok"}'
    post_mock = Mock(return_value=response)
    monkeypatch.setattr("src.api.services.token_mint_hook.httpx.post", post_mock)

    result = hook.mint(
        model_id="model-a",
        token_id="token-a",
        delta_value=2.0,
        idempotency_key="idem-abc",
        metadata={"reason": "outcome"},
    )

    assert result.status == "success"
    assert post_mock.call_count == 1
    call_kwargs = post_mock.call_args.kwargs
    assert call_kwargs["timeout"] == 10.0
    assert call_kwargs["json"]["model_id"] == "model-a"
    assert call_kwargs["json"]["token_id"] == "token-a"
    assert call_kwargs["json"]["delta_value"] == 2.0
    assert call_kwargs["json"]["idempotency_key"] == "idem-abc"
    assert call_kwargs["json"]["metadata"] == {"reason": "outcome"}


def test_timeout_returns_failed_status(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    hook = TokenMintHook(
        mint_endpoint="https://mint.service.local",
        dry_run=False,
        timeout=0.01,
        retry_attempts=2,
    )

    timeout_error = httpx.TimeoutException("request timed out")
    post_mock = Mock(side_effect=timeout_error)
    monkeypatch.setattr("src.api.services.token_mint_hook.httpx.post", post_mock)

    result = hook.mint("model-a", "token-a", 1.0)

    assert result.status == "failed"
    assert result.error is not None
    assert "timed out" in result.error
    assert post_mock.call_count == 2
    logs = _json_logs(caplog)
    retry_logs = [item for item in logs if item["action"] == "token_mint_retry"]
    assert len(retry_logs) == 2


def test_skipped_when_endpoint_missing_and_dry_run_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hook = TokenMintHook(mint_endpoint=None, dry_run=False)
    post_mock = Mock()
    monkeypatch.setattr("src.api.services.token_mint_hook.httpx.post", post_mock)

    result = hook.mint("model-a", "token-a", 0.5)

    assert result.status == "skipped"
    post_mock.assert_not_called()
