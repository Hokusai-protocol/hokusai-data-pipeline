from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from src.eip712.onchain_head import BaselineUnavailableError, read_model_weight_head

_RPC_URL = "https://rpc.example"
_DELTA_VERIFIER = "0x" + "11" * 20
_MODEL_REGISTRY = "0x" + "22" * 20


def _response(payload):
    return Mock(raise_for_status=Mock(), json=Mock(return_value=payload))


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


def test_read_model_weight_head_rejects_malformed_bytes32(monkeypatch: pytest.MonkeyPatch) -> None:
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
