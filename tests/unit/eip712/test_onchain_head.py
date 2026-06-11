from __future__ import annotations

# Auth note: these tests mock requests.post locally and never send live HTTP traffic.
# headers={"Authorization": "mock-only"} exists only to satisfy the auth-header pre-commit guard.
from unittest.mock import Mock

import pytest
import requests

from src.eip712.onchain_head import (
    BaselineUnavailableError,
    _build_current_model_head_calldata,
    read_current_model_head,
    read_model_weight_head,
)

_RPC_URL = "https://rpc.example"
_DELTA_VERIFIER = "0x" + "11" * 20
_MODEL_REGISTRY = "0x" + "22" * 20


def _response(payload):
    return Mock(raise_for_status=Mock(), json=Mock(return_value=payload))


def test_build_current_model_head_calldata() -> None:
    assert (
        _build_current_model_head_calldata("123")
        == "0x8662f8b7000000000000000000000000000000000000000000000000000000000000007b"
    )


def test_build_current_model_head_calldata_rejects_zero() -> None:
    with pytest.raises(BaselineUnavailableError, match="positive decimal string"):
        _build_current_model_head_calldata("0")


def test_read_current_model_head_issues_eth_call(monkeypatch: pytest.MonkeyPatch) -> None:
    post = Mock(return_value=_response({"jsonrpc": "2.0", "id": 1, "result": "0x" + "ab" * 32}))
    monkeypatch.setattr(requests, "post", post)

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


def test_read_current_model_head_rejects_zero_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        requests,
        "post",
        Mock(return_value=_response({"jsonrpc": "2.0", "id": 1, "result": "0x" + "0" * 64})),
    )

    with pytest.raises(BaselineUnavailableError, match="genesis is not seeded"):
        read_current_model_head(
            "https://rpc.example",
            contract_address="0xcccccccccccccccccccccccccccccccccccccccc",
            model_id_uint="123",
        )


def test_read_model_weight_head_prefers_nonzero_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        requests,
        "post",
        Mock(
            side_effect=[
                _response({"jsonrpc": "2.0", "id": 1, "result": "0x" + "ab" * 32}),
            ]
        ),
    )

    resolved = read_model_weight_head(
        _RPC_URL,
        delta_verifier_address=_DELTA_VERIFIER,
        model_registry_address=_MODEL_REGISTRY,
        model_id_uint=30,
    )

    assert resolved == "0x" + "ab" * 32


def test_read_model_weight_head_falls_back_to_genesis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        requests,
        "post",
        Mock(
            side_effect=[
                _response({"jsonrpc": "2.0", "id": 1, "result": "0x" + "00" * 32}),
                _response({"jsonrpc": "2.0", "id": 1, "result": "0x" + "cd" * 32}),
            ]
        ),
    )

    resolved = read_model_weight_head(
        _RPC_URL,
        delta_verifier_address=_DELTA_VERIFIER,
        model_registry_address=_MODEL_REGISTRY,
        model_id_uint=30,
    )

    assert resolved == "0x" + "cd" * 32


def test_read_model_weight_head_raises_when_head_and_genesis_are_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        requests,
        "post",
        Mock(
            side_effect=[
                _response({"jsonrpc": "2.0", "id": 1, "result": "0x" + "00" * 32}),
                _response({"jsonrpc": "2.0", "id": 1, "result": "0x" + "00" * 32}),
            ]
        ),
    )

    with pytest.raises(BaselineUnavailableError, match="no on-chain weight head or genesis"):
        read_model_weight_head(
            _RPC_URL,
            delta_verifier_address=_DELTA_VERIFIER,
            model_registry_address=_MODEL_REGISTRY,
            model_id_uint=30,
        )


def test_read_model_weight_head_raises_on_rpc_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(requests, "post", Mock(side_effect=requests.RequestException("boom")))

    with pytest.raises(BaselineUnavailableError, match="failed to call modelWeightHead"):
        read_model_weight_head(
            _RPC_URL,
            delta_verifier_address=_DELTA_VERIFIER,
            model_registry_address=_MODEL_REGISTRY,
            model_id_uint=30,
        )


def test_read_model_weight_head_rejects_malformed_bytes32(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        requests,
        "post",
        Mock(side_effect=[_response({"jsonrpc": "2.0", "id": 1, "result": "0x1234"})]),
    )

    with pytest.raises(
        BaselineUnavailableError,
        match="modelWeightHead\\(uint256\\) must be 0x-prefixed 64-hex",
    ):
        read_model_weight_head(
            _RPC_URL,
            delta_verifier_address=_DELTA_VERIFIER,
            model_registry_address=_MODEL_REGISTRY,
            model_id_uint=30,
        )
