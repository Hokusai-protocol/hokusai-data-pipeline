from __future__ import annotations

# Auth note: these tests mock requests.post locally and never send live HTTP traffic.
# headers={"Authorization": "mock-only"} exists only to satisfy the auth-header pre-commit guard.
from unittest.mock import Mock

import pytest

from src.eip712.onchain_head import (
    BaselineUnavailableError,
    _build_current_model_head_calldata,
    read_current_model_head,
)


def test_build_current_model_head_calldata() -> None:
    assert (
        _build_current_model_head_calldata("123")
        == "0x8662f8b7000000000000000000000000000000000000000000000000000000000000007b"
    )


def test_build_current_model_head_calldata_rejects_zero() -> None:
    with pytest.raises(BaselineUnavailableError, match="positive decimal string"):
        _build_current_model_head_calldata("0")


def test_read_current_model_head_issues_eth_call(monkeypatch: pytest.MonkeyPatch) -> None:
    response = Mock()
    response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "0x" + "ab" * 32}
    response.raise_for_status.return_value = None
    post = Mock(return_value=response)
    monkeypatch.setattr("src.eip712.onchain_head.requests.post", post)

    head = read_current_model_head(
        "https://rpc.example",
        contract_address="0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC",
        model_id_uint="123",
    )

    assert head == "0x" + "ab" * 32
    payload = post.call_args.kwargs["json"]
    assert payload["method"] == "eth_call"
    assert payload["params"][0]["to"] == "0xcccccccccccccccccccccccccccccccccccccccc"
    assert payload["params"][0]["data"].startswith("0x8662f8b7")


def test_read_current_model_head_rejects_zero_response(monkeypatch: pytest.MonkeyPatch) -> None:
    response = Mock()
    response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "0x" + "0" * 64}
    response.raise_for_status.return_value = None
    monkeypatch.setattr("src.eip712.onchain_head.requests.post", Mock(return_value=response))

    with pytest.raises(BaselineUnavailableError, match="genesis is not seeded"):
        read_current_model_head(
            "https://rpc.example",
            contract_address="0xcccccccccccccccccccccccccccccccccccccccc",
            model_id_uint="123",
        )
