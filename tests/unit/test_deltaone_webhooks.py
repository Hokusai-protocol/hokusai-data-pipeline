"""Unit tests for DeltaOne webhook security/config/delivery helpers."""

import json
from unittest.mock import Mock, patch

from src.evaluation.webhook_config import DELTAONE_EVENT_TYPE, load_deltaone_webhook_endpoints
from src.evaluation.webhook_delivery import (
    WebhookEndpoint,
    redact_webhook_url,
    send_webhook_with_retry,
)
from src.evaluation.webhook_security import generate_nonce, sign_payload, verify_signature


def test_sign_payload_is_deterministic() -> None:
    payload = b'{"model":"foo"}'
    signature_a = sign_payload(payload, "whsec_test", "1700000000", "nonce-1")
    signature_b = sign_payload(payload, "whsec_test", "1700000000", "nonce-1")

    assert signature_a == signature_b
    assert signature_a.startswith("sha256=")


def test_verify_signature() -> None:
    payload = b'{"model":"foo"}'
    signature = sign_payload(payload, "whsec_test", "1700000000", "nonce-1")

    assert verify_signature(payload, "whsec_test", "1700000000", "nonce-1", signature) is True
    assert verify_signature(payload, "wrong", "1700000000", "nonce-1", signature) is False


def test_generate_nonce_is_unique() -> None:
    nonce_1 = generate_nonce()
    nonce_2 = generate_nonce()

    assert nonce_1 != nonce_2


def test_load_deltaone_webhook_endpoints_from_env(monkeypatch) -> None:
    config = [
        {
            "url": "https://a.example.com/webhook",
            "secret": "whsec_a",
            "event_types": [DELTAONE_EVENT_TYPE],
            "active": True,
        },
        {
            "url": "https://b.example.com/webhook",
            "secret": "whsec_b",
            "event_types": ["other.event"],
            "active": True,
        },
        {
            "url": "https://c.example.com/webhook",
            "secret": "whsec_c",
            "event_types": [DELTAONE_EVENT_TYPE],
            "active": False,
        },
    ]
    monkeypatch.setenv("DELTAONE_WEBHOOK_ENDPOINTS", json.dumps(config))

    endpoints = load_deltaone_webhook_endpoints()

    assert len(endpoints) == 1
    assert endpoints[0].url == "https://a.example.com/webhook"


def test_load_deltaone_webhook_endpoints_legacy_fallback(monkeypatch) -> None:
    monkeypatch.delenv("DELTAONE_WEBHOOK_ENDPOINTS", raising=False)
    endpoints = load_deltaone_webhook_endpoints(
        legacy_webhook_url="https://legacy.example.com/webhook",
        legacy_secret="whsec_legacy",
    )

    assert len(endpoints) == 1
    assert endpoints[0].secret == "whsec_legacy"


def test_redact_webhook_url() -> None:
    assert redact_webhook_url("https://example.com/path?q=1") == "https://example.com"


@patch("src.evaluation.webhook_delivery.random.uniform", return_value=1.0)
@patch("src.evaluation.webhook_delivery.time.time", return_value=1700000000)
@patch("src.evaluation.webhook_delivery.generate_nonce", return_value="nonce-1")
@patch("src.evaluation.webhook_delivery.requests.post")
def test_send_webhook_with_retry_success(mock_post, _mock_nonce, _mock_time, _mock_uniform) -> None:
    endpoint = WebhookEndpoint(
        url="https://example.com/webhook",
        secret="whsec_test",
        event_types=(DELTAONE_EVENT_TYPE,),
        active=True,
    )
    mock_post.side_effect = [Mock(status_code=500), Mock(status_code=200)]
    sleep = Mock()

    result = send_webhook_with_retry(
        endpoint,
        DELTAONE_EVENT_TYPE,
        {"model": "test"},
        max_retries=3,
        sleep=sleep,
    )

    assert result.success is True
    assert result.attempts == 2
    assert mock_post.call_count == 2
    sleep.assert_called_once_with(1.0)

    headers = mock_post.call_args.kwargs["headers"]
    assert headers["X-Hokusai-Timestamp"] == "1700000000"
    assert headers["X-Hokusai-Nonce"] == "nonce-1"
    assert headers["X-Hokusai-Signature"].startswith("sha256=")


@patch("src.evaluation.webhook_delivery.random.uniform", return_value=1.0)
@patch("src.evaluation.webhook_delivery.time.time", return_value=1700000000)
@patch("src.evaluation.webhook_delivery.generate_nonce", return_value="nonce-2")
@patch("src.evaluation.webhook_delivery.requests.post")
def test_send_webhook_with_retry_all_fail(
    mock_post,
    _mock_nonce,
    _mock_time,
    _mock_uniform,
) -> None:
    endpoint = WebhookEndpoint(
        url="https://example.com/webhook",
        secret="whsec_test",
        event_types=(DELTAONE_EVENT_TYPE,),
        active=True,
    )
    mock_post.return_value = Mock(status_code=503)
    sleep = Mock()

    result = send_webhook_with_retry(
        endpoint,
        DELTAONE_EVENT_TYPE,
        {"model": "test"},
        max_retries=3,
        sleep=sleep,
    )

    assert result.success is False
    assert result.attempts == 3
    assert mock_post.call_count == 3
    assert sleep.call_count == 2
