"""Minimal JSON-RPC helpers for on-chain mint baseline and weight lineage reads."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import requests
from eth_utils import keccak

_BYTES32_RE = re.compile(r"^0x[0-9a-f]{64}$")
_ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")
_UINT_RE = re.compile(r"^[1-9]\d*$")


class BaselineUnavailableError(RuntimeError):
    """Raised when the canonical on-chain lineage head cannot be resolved safely."""


def read_onchain_head(rpc_url: str, *, timeout: float = 5.0) -> str:
    """Return the latest block hash as a lowercase 0x-prefixed 64-hex string."""
    payload = _post_json_rpc(
        rpc_url,
        method="eth_getBlockByNumber",
        params=["latest", False],
        timeout=timeout,
        error_context="read on-chain head",
    )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise BaselineUnavailableError("RPC response missing latest block result object")

    return _extract_block_hash(result)


def read_current_model_head(
    rpc_url: str,
    *,
    contract_address: str,
    model_id_uint: str,
    timeout: float = 5.0,
) -> str:
    """Return DeltaVerifier.currentModelHead(modelId) as a lowercase 0x-prefixed bytes32."""
    normalized_contract = _normalize_address(contract_address, field="contract_address")
    calldata = _build_current_model_head_calldata(model_id_uint)
    payload = _post_json_rpc(
        rpc_url,
        method="eth_call",
        params=[{"to": normalized_contract, "data": calldata}, "latest"],
        timeout=timeout,
        error_context=f"read currentModelHead({model_id_uint})",
    )
    result = payload.get("result")
    if not isinstance(result, str):
        raise BaselineUnavailableError("RPC response missing eth_call result")

    normalized = _normalize_bytes32(result, field="currentModelHead")
    if _is_zero_bytes32(normalized):
        raise BaselineUnavailableError(
            f"currentModelHead({model_id_uint}) returned zero; model genesis is not seeded"
        )
    return normalized


def read_model_weight_head(
    rpc_url: str,
    *,
    delta_verifier_address: str,
    model_registry_address: str,
    model_id_uint: int,
    timeout: float = 5.0,
) -> str:
    """Return the authoritative on-chain weight lineage head for ``model_id_uint``."""
    delta_verifier = _normalize_address(delta_verifier_address, field="delta_verifier_address")
    model_registry = _normalize_address(model_registry_address, field="model_registry_address")
    encoded_model_id = _encode_uint256(model_id_uint)

    head = _eth_call_bytes32(
        rpc_url,
        to=delta_verifier,
        function_signature="modelWeightHead(uint256)",
        encoded_args=(encoded_model_id,),
        timeout=timeout,
    )
    if not _is_zero_bytes32(head):
        return head

    genesis = _eth_call_bytes32(
        rpc_url,
        to=model_registry,
        function_signature="weightGenesis(uint256)",
        encoded_args=(encoded_model_id,),
        timeout=timeout,
    )
    if _is_zero_bytes32(genesis):
        raise BaselineUnavailableError(
            f"no on-chain weight head or genesis configured for model_id_uint={model_id_uint}"
        )
    return genesis


def _post_json_rpc(
    rpc_url: str,
    *,
    method: str,
    params: list[Any],
    timeout: float,
    error_context: str,
) -> dict[str, Any]:
    """Execute a JSON-RPC request and return the decoded payload."""
    try:
        response = requests.post(
            rpc_url,
            headers={"Content-Type": "application/json"},
            json={
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": 1,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise BaselineUnavailableError(f"failed to {error_context}: {exc}") from exc

    if not isinstance(payload, dict):
        raise BaselineUnavailableError(
            f"malformed JSON-RPC payload while attempting to {error_context}"
        )
    error = payload.get("error")
    if error is not None:
        raise BaselineUnavailableError(f"RPC error while attempting to {error_context}: {error}")
    return payload


def _eth_call_bytes32(
    rpc_url: str,
    *,
    to: str,
    function_signature: str,
    encoded_args: Sequence[str],
    timeout: float,
) -> str:
    data = _encode_call_data(function_signature, encoded_args)
    payload = _post_json_rpc(
        rpc_url,
        method="eth_call",
        params=[{"to": to, "data": data}, "latest"],
        timeout=timeout,
        error_context=f"call {function_signature} on {to}",
    )
    result = payload.get("result")
    if not isinstance(result, str):
        raise BaselineUnavailableError(
            f"eth_call {function_signature} returned non-string result: {type(result).__name__}"
        )
    return _normalize_bytes32(result, field=function_signature)


def _extract_block_hash(result: dict[str, Any]) -> str:
    block_hash = result.get("hash")
    if not isinstance(block_hash, str):
        raise BaselineUnavailableError("latest block response missing hash")
    normalized = block_hash.lower()
    if not _BYTES32_RE.match(normalized):
        raise BaselineUnavailableError(
            f"latest block hash must be 0x-prefixed 64-hex, got {block_hash!r}"
        )
    return normalized


def _build_current_model_head_calldata(model_id_uint: str) -> str:
    if not _UINT_RE.match(model_id_uint):
        raise BaselineUnavailableError(
            f"model_id_uint must be a positive decimal string, got {model_id_uint!r}"
        )
    return _encode_call_data("currentModelHead(uint256)", (_encode_uint256(int(model_id_uint)),))


def _normalize_bytes32(value: str, *, field: str) -> str:
    normalized = value.lower()
    if not _BYTES32_RE.match(normalized):
        raise BaselineUnavailableError(f"{field} must be 0x-prefixed 64-hex, got {value!r}")
    return normalized


def _normalize_address(value: str, *, field: str) -> str:
    normalized = value.strip().lower()
    if not _ADDRESS_RE.match(normalized):
        raise BaselineUnavailableError(f"{field} must be a 0x-prefixed 40-hex address")
    return normalized


def _encode_uint256(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BaselineUnavailableError(
            f"model_id_uint must be a non-negative integer, got {value!r}"
        )
    return f"{value:064x}"


def _encode_call_data(function_signature: str, encoded_args: Sequence[str]) -> str:
    selector = keccak(text=function_signature)[:4].hex()
    return f"0x{selector}{''.join(encoded_args)}"


def _is_zero_bytes32(value: str) -> bool:
    return value == "0x" + ("0" * 64)
